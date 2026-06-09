import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import (
    run_llm_requirements_from_chapter,
    run_llm_indices,
)
from tendermod.evaluation.prompts import (
    PLIEGO_QA_SYSTEM_PROMPT,
    qna_user_message_pliego_qa,
)
from tendermod.evaluation.schemas import GeneralRequirement, GeneralRequirementList
from tendermod.ingestion.chapter_extractor import (
    extract_page_range,
    get_chapter_ranges,
)
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore

logger = logging.getLogger(__name__)

# Límite de caracteres por bloque enviado al LLM.
# 20K chars (~5K tokens) necesarios para que el modelo mantenga atención en sub-componentes
# de puntaje (filas de tabla, criterios con puntaje propio) dentro de secciones largas.
_MAX_BLOCK_CHARS = 20_000
# Máximo de llamadas LLM concurrentes (respetar rate limits de OpenAI).
_MAX_WORKERS = 5

# Keywords en el título del capítulo que indican obligaciones contractuales post-adjudicación.
_OBLIGATION_CHAPTER_KEYWORDS = [
    "OBLIGACION", "CLAUSULA", "SUPERVISION", "SEGUIMIENTO",
    "ANS", "EJECUCION DEL CONTRATO", "DEBER",
    "OBLIGACIONES ESPECIALES", "OBLIGACIONES GENERALES", "COMPROMISOS",
]

# Keywords en el título del capítulo que indican requisitos de idioma/lenguaje de la oferta.
_LANGUAGE_CHAPTER_KEYWORDS = [
    "IDIOMA", "LENGUAJE", "LANGUAGE", "LINGUA",
]


_NUMERAL_RE = re.compile(r"\d+(\.\d+)+")


def _normalize(text: str) -> str:
    """Normaliza espacios y minúsculas para comparación de citas literales."""
    return re.sub(r"\s+", " ", text).lower().strip()


def _compute_confidence(req) -> float:
    """
    Heurística 0.0-1.0 para el campo confidence de GeneralRequirement.
    - Sección con numeral (ej: '2.23.1'): +0.3
    - Sección sin numeral pero presente: +0.1
    - extracto_pliego no vacío (>20 chars): +0.2
    - citation_verified=True: +0.2
    """
    score = 0.3
    if req.seccion and req.seccion not in ("N/A", "None", ""):
        score += 0.3 if _NUMERAL_RE.search(req.seccion) else 0.1
    if req.extracto_pliego and len(req.extracto_pliego.strip()) > 20:
        score += 0.2
    if req.citation_verified is True:
        score += 0.2
    return round(min(score, 1.0), 2)


def _is_obligation_chapter(title: str) -> bool:
    upper = title.upper()
    return any(kw in upper for kw in _OBLIGATION_CHAPTER_KEYWORDS)


def _is_language_chapter(title: str) -> bool:
    upper = title.upper()
    return any(kw in upper for kw in _LANGUAGE_CHAPTER_KEYWORDS)


def _get_pdf_path() -> str:
    """Retorna el path del primer PDF encontrado en data/."""
    data_dir = Path(CHROMA_PERSIST_DIR).parent  # data/chroma → data/
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def _build_blocks(pdf_path: str, chapters: list[dict]) -> list[dict]:
    """
    Fusiona capítulos consecutivos en bloques de <= _MAX_BLOCK_CHARS chars,
    nunca cortando a mitad de un capítulo. Garantiza cobertura total del PDF.
    """
    blocks: list[dict] = []
    current_text = ""
    current_title = ""

    for ch in chapters:
        section_marker = (
            f"\n\n[=== SECCIÓN: {ch['title'][:80]} | "
            f"Páginas {ch['start_page'] + 1}–{ch['end_page']} ===]\n"
        )
        ch_text = section_marker + extract_page_range(pdf_path, ch["start_page"], ch["end_page"])
        if len(current_text) + len(ch_text) > _MAX_BLOCK_CHARS and current_text:
            blocks.append({
                "text": current_text,
                "title": current_title,
                "is_obligation": _is_obligation_chapter(current_title),
                "is_language": _is_language_chapter(current_title),
            })
            current_text = ch_text
            current_title = ch["title"]
        else:
            if not current_title:
                current_title = ch["title"]
            current_text += ch_text

    if current_text:
        blocks.append({
            "text": current_text,
            "title": current_title,
            "is_obligation": _is_obligation_chapter(current_title),
            "is_language": _is_language_chapter(current_title),
        })

    return blocks


def _merge_results(raw_lists: list[list[GeneralRequirement]]) -> GeneralRequirementList:
    """Deduplica y asigna IDs secuenciales."""
    seen: set[tuple] = set()
    merged: list[GeneralRequirement] = []
    next_id = 1
    for req_list in raw_lists:
        for req in req_list:
            key = (req.tipo, req.seccion, req.descripcion[:80].lower())
            if key not in seen:
                seen.add(key)
                req.id = next_id
                next_id += 1
                merged.append(req)
    return GeneralRequirementList(requisitos=merged)


def get_general_requirements(k: int = 3) -> GeneralRequirementList:
    """
    Extrae requerimientos generales del pliego escaneando el documento completo.

    Flujo:
    1. Detectar capítulos del PDF (TOC nativo → LLM → visual tipográfico).
    2. Fusionar capítulos consecutivos en bloques de ≤20K chars sin cortar a mitad
       de sección (_build_blocks). Se procesan TODOS los capítulos sin filtro de keywords.
    3. Procesar bloques en paralelo con el LLM.
    4. Merge con deduplicación por (seccion, descripcion[:60]).
    """
    pdf_path = _get_pdf_path()

    doc = fitz.open(pdf_path)
    n_pdf_pages = len(doc)
    doc.close()

    chapters = get_chapter_ranges(pdf_path, use_llm=True)

    if not chapters:
        logger.warning("[get_general_requirements] Sin capítulos detectados — fallback bloque único")
        chapters = [{"title": "Documento completo", "start_page": 0, "end_page": n_pdf_pages}]

    blocks = _build_blocks(pdf_path, chapters)

    logger.info(
        "[get_general_requirements] %d capítulos → %d bloques en paralelo (max %d workers)",
        len(chapters), len(blocks), _MAX_WORKERS,
    )

    raw_results: list[list[GeneralRequirement]] = [[] for _ in blocks]
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_to_idx = {
            pool.submit(
                run_llm_requirements_from_chapter,
                b["text"], b["title"],
                is_obligation=b["is_obligation"],
            ): i
            for i, b in enumerate(blocks)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                partial = future.result()
                if blocks[idx]["is_obligation"]:
                    for req in partial.requisitos:
                        req.tipo = "OBLIGACION"
                elif blocks[idx]["is_language"]:
                    for req in partial.requisitos:
                        req.tipo = "IDIOMA"
                        req.categoria = "IDIOMA"

                # Validación de cita + heurística de confianza
                normalized_block = _normalize(blocks[idx]["text"])
                for req in partial.requisitos:
                    extracto = req.extracto_pliego.strip()
                    if extracto and len(extracto) > 15:
                        probe = _normalize(extracto)[:60]
                        req.citation_verified = probe in normalized_block
                    req.confidence = _compute_confidence(req)

                raw_results[idx] = partial.requisitos
                logger.info(
                    "[get_general_requirements] Bloque %d/%d '%s': %d requisitos",
                    idx + 1, len(blocks), blocks[idx]["title"][:40], len(raw_results[idx]),
                )
            except Exception as exc:
                logger.error(
                    "[get_general_requirements] Bloque %d falló: %s", idx + 1, exc
                )

    result = _merge_results(raw_results)
    logger.info(
        "[get_general_requirements] %d bloques → %d requerimientos únicos",
        len(blocks), len(result.requisitos),
    )
    return result


def ask_pliego(question: str, k: int = 8) -> str:
    """Responde preguntas en lenguaje natural sobre el pliego usando ChromaDB/RAG."""
    docs, _ = load_docs()
    chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k)

    context_for_query = build_context(retriever, chunks, question, k=k)

    user_message = qna_user_message_pliego_qa
    user_message = user_message.replace("{context}", context_for_query)
    user_message = user_message.replace("{question}", question)

    return run_llm_indices(PLIEGO_QA_SYSTEM_PROMPT, user_message)
