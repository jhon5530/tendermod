import logging
from pathlib import Path

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
    filter_relevant_chapters,
    get_chapter_ranges,
)
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore

logger = logging.getLogger(__name__)

# Límite de caracteres por bloque enviado al LLM (~90K tokens × 4 chars/token).
_MAX_BLOCK_CHARS = 360_000


def _get_pdf_path() -> str:
    """Retorna el path del primer PDF encontrado en data/."""
    data_dir = Path(CHROMA_PERSIST_DIR).parent  # data/chroma → data/
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def get_general_requirements(k: int = 3) -> GeneralRequirementList:
    """
    Extrae requerimientos generales del pliego por capítulos completos.

    Flujo:
    1. Detectar capítulos del PDF (TOC nativo → LLM → heurística).
    2. Filtrar capítulos relevantes por keywords en el título.
    3. Por cada capítulo, extraer texto completo y llamar al LLM.
    4. Merge con deduplicación por (seccion, descripcion[:60]).
    5. Si se extraen < 10 ítems, re-intentar con capítulos descartados.
    """
    pdf_path = _get_pdf_path()

    chapters = get_chapter_ranges(pdf_path, use_llm=True)
    relevant_chapters = filter_relevant_chapters(chapters)

    if not relevant_chapters:
        logger.warning("[get_general_requirements] No se detectaron capítulos relevantes")
        return GeneralRequirementList(requisitos=[])

    all_requisitos: list[GeneralRequirement] = []
    seen: set[tuple] = set()
    next_id = 1

    def _process_chapter(chapter: dict) -> None:
        nonlocal next_id
        title = chapter["title"]
        chapter_text = extract_page_range(pdf_path, chapter["start_page"], chapter["end_page"])
        n_chars = len(chapter_text)

        logger.info(
            "[get_general_requirements] Capítulo '%s' (pág %d–%d, ~%d tokens)",
            title, chapter["start_page"] + 1, chapter["end_page"], n_chars // 4,
        )

        if n_chars > _MAX_BLOCK_CHARS:
            sub_blocks = [
                chapter_text[i: i + _MAX_BLOCK_CHARS]
                for i in range(0, n_chars, _MAX_BLOCK_CHARS)
            ]
            logger.info(
                "[get_general_requirements] Capítulo grande → %d sub-bloques", len(sub_blocks)
            )
        else:
            sub_blocks = [chapter_text]

        chapter_count = 0
        for block in sub_blocks:
            try:
                partial = run_llm_requirements_from_chapter(block, title)
            except Exception as exc:
                logger.error(
                    "[get_general_requirements] Error en capítulo '%s': %s", title, exc
                )
                continue

            for req in partial.requisitos:
                key = (req.seccion, req.descripcion[:60].lower())
                if key not in seen:
                    seen.add(key)
                    req.id = next_id
                    next_id += 1
                    all_requisitos.append(req)
                    chapter_count += 1

        logger.info(
            "[get_general_requirements] '%s': %d requerimientos (total: %d)",
            title, chapter_count, len(all_requisitos),
        )

    for chapter in relevant_chapters:
        _process_chapter(chapter)

    # Re-intento si la cobertura es baja: procesar capítulos descartados
    if len(all_requisitos) < 10:
        logger.warning(
            "[get_general_requirements] Solo %d requisitos — re-intentando con capítulos no seleccionados",
            len(all_requisitos),
        )
        remaining = [ch for ch in chapters if ch not in relevant_chapters]
        for chapter in remaining[:5]:
            chapter_text = extract_page_range(pdf_path, chapter["start_page"], chapter["end_page"])
            if len(chapter_text) < 500:
                continue
            _process_chapter(chapter)

    logger.info(
        "[get_general_requirements] %d capítulos relevantes → %d requerimientos únicos",
        len(relevant_chapters), len(all_requisitos),
    )
    return GeneralRequirementList(requisitos=all_requisitos)


def ask_pliego(question: str, k: int = 8) -> str:
    """Responde preguntas en lenguaje natural sobre el pliego usando ChromaDB/RAG."""
    docs = load_docs()
    chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k)

    context_for_query = build_context(retriever, chunks, question, k=k)

    user_message = qna_user_message_pliego_qa
    user_message = user_message.replace("{context}", context_for_query)
    user_message = user_message.replace("{question}", question)

    return run_llm_indices(PLIEGO_QA_SYSTEM_PROMPT, user_message)
