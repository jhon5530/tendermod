import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# Máximo de llamadas LLM concurrentes (respetar rate limits de OpenAI).
_MAX_WORKERS = 5


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

    def _fetch_chapter_requirements(chapter: dict) -> list[GeneralRequirement]:
        """Extrae requerimientos de un capítulo (ejecutable en paralelo)."""
        title = chapter["title"]
        chapter_text = extract_page_range(pdf_path, chapter["start_page"], chapter["end_page"])
        n_chars = len(chapter_text)

        logger.info(
            "[get_general_requirements] Capítulo '%s' (pág %d–%d, ~%d tokens)",
            title, chapter["start_page"] + 1, chapter["end_page"], n_chars // 4,
        )

        sub_blocks = (
            [chapter_text[i: i + _MAX_BLOCK_CHARS] for i in range(0, n_chars, _MAX_BLOCK_CHARS)]
            if n_chars > _MAX_BLOCK_CHARS
            else [chapter_text]
        )

        results: list[GeneralRequirement] = []
        for block in sub_blocks:
            try:
                partial = run_llm_requirements_from_chapter(block, title)
                results.extend(partial.requisitos)
            except Exception as exc:
                logger.error(
                    "[get_general_requirements] Error en capítulo '%s': %s", title, exc
                )
        logger.info(
            "[get_general_requirements] '%s': %d requerimientos extraídos", title, len(results)
        )
        return results

    def _merge_results(raw_lists: list[list[GeneralRequirement]]) -> GeneralRequirementList:
        """Deduplica y asigna IDs secuenciales."""
        seen: set[tuple] = set()
        merged: list[GeneralRequirement] = []
        next_id = 1
        for req_list in raw_lists:
            for req in req_list:
                key = (req.seccion, req.descripcion[:60].lower())
                if key not in seen:
                    seen.add(key)
                    req.id = next_id
                    next_id += 1
                    merged.append(req)
        return GeneralRequirementList(requisitos=merged)

    # ── Procesamiento paralelo de capítulos relevantes ──────────────────────
    logger.info(
        "[get_general_requirements] Procesando %d capítulos en paralelo (max %d workers)",
        len(relevant_chapters), _MAX_WORKERS,
    )
    raw_results: list[list[GeneralRequirement]] = [[] for _ in relevant_chapters]
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_to_idx = {
            pool.submit(_fetch_chapter_requirements, ch): i
            for i, ch in enumerate(relevant_chapters)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                raw_results[idx] = future.result()
            except Exception as exc:
                logger.error(
                    "[get_general_requirements] Hilo %d falló: %s", idx, exc
                )

    result = _merge_results(raw_results)

    # Re-intento si la cobertura es baja: procesar capítulos descartados
    if len(result.requisitos) < 10:
        logger.warning(
            "[get_general_requirements] Solo %d requisitos — re-intentando con capítulos no seleccionados",
            len(result.requisitos),
        )
        remaining = [ch for ch in chapters if ch not in relevant_chapters]
        extra: list[list[GeneralRequirement]] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = []
            for ch in remaining[:5]:
                if len(extract_page_range(pdf_path, ch["start_page"], ch["end_page"])) >= 500:
                    futures.append(pool.submit(_fetch_chapter_requirements, ch))
            for future in as_completed(futures):
                try:
                    extra.append(future.result())
                except Exception as exc:
                    logger.error("[get_general_requirements] Re-intento falló: %s", exc)

        # Merge extra sobre el resultado existente
        seen_keys = {(r.seccion, r.descripcion[:60].lower()) for r in result.requisitos}
        next_id = len(result.requisitos) + 1
        for req_list in extra:
            for req in req_list:
                key = (req.seccion, req.descripcion[:60].lower())
                if key not in seen_keys:
                    seen_keys.add(key)
                    req.id = next_id
                    next_id += 1
                    result.requisitos.append(req)

    logger.info(
        "[get_general_requirements] %d capítulos relevantes → %d requerimientos únicos",
        len(relevant_chapters), len(result.requisitos),
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
