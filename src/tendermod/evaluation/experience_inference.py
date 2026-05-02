import logging
from pathlib import Path

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import run_llm_indices
from tendermod.evaluation.prompts import qna_system_message_experience, qna_user_message_experience
from tendermod.evaluation.schemas import ExperienceResponse
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever, create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore

logger = logging.getLogger(__name__)

_EXPERIENCE_KEYWORDS = [
    "experiencia", "unspsc", "smmlv", "segmento", "habilitante", "contrato",
]
_MAX_EXPERIENCE_CHARS = 360_000  # ~90K tokens × 4 chars/token


def _get_pdf_path() -> str:
    data_dir = Path(CHROMA_PERSIST_DIR).parent
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def get_experience(user_input: str, k: int):
    """
    Extrae ExperienceResponse usando capítulos completos del PDF.
    Detecta automáticamente modo MULTI_CONDICION para pliegos con múltiples segmentos.
    Fallback a RAG si la detección de capítulos falla.
    """
    from tendermod.ingestion.chapter_extractor import (
        get_chapter_ranges, filter_relevant_chapters, extract_page_range,
    )
    from tendermod.evaluation.llm_client import run_llm_experience_from_chapters

    try:
        pdf_path = _get_pdf_path()
        chapters = get_chapter_ranges(pdf_path, use_llm=True)

        # Capítulos con keywords de experiencia en el título
        exp_chapters = [
            ch for ch in chapters
            if any(kw in ch["title"].lower() for kw in _EXPERIENCE_KEYWORDS)
        ]
        # Fallback: si no hay capítulos con keywords de experiencia, usar todos los relevantes
        if not exp_chapters:
            exp_chapters = filter_relevant_chapters(chapters)

        if exp_chapters:
            combined_text = ""
            for ch in exp_chapters:
                text = extract_page_range(pdf_path, ch["start_page"], ch["end_page"])
                combined_text += f"\n\n=== {ch['title']} ===\n{text}"
                if len(combined_text) > _MAX_EXPERIENCE_CHARS:
                    logger.warning("[get_experience] Contexto truncado a %d chars", _MAX_EXPERIENCE_CHARS)
                    combined_text = combined_text[:_MAX_EXPERIENCE_CHARS]
                    break

            if combined_text.strip():
                logger.info(
                    "[get_experience] Extrayendo desde %d capítulos (%d chars)",
                    len(exp_chapters), len(combined_text),
                )
                result = run_llm_experience_from_chapters(combined_text)
                logger.info(
                    "[get_experience] Modo=%s, sub_requisitos=%d, codigos=%d",
                    result.modo_evaluacion, len(result.sub_requisitos), len(result.listado_codigos),
                )
                return result, combined_text

    except Exception as exc:
        logger.error("[get_experience] Error en extracción por capítulos: %s — usando RAG", exc)

    # --- Fallback: extracción RAG original ---
    return _get_experience_rag(user_input, k)


def _get_experience_rag(user_input: str, k: int):
    """Extracción de experiencia usando RAG (ChromaDB). Fallback del flujo principal."""
    docs, _ = load_docs()
    chunks = chunk_docs(docs)

    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorStore, k)

    context_for_query = build_context(retriever, chunks, user_input, k=k)

    # Segunda búsqueda dirigida para capturar sub-requisitos de experiencia específica
    specific_query = "experiencia específica al menos un contrato"
    context_specific = build_context(retriever, chunks, specific_query, k=5)
    if context_specific:
        existing_fragments = set(
            fragment.strip()
            for fragment in context_for_query.split(". ")
            if fragment.strip()
        )
        new_fragments = [
            fragment
            for fragment in context_specific.split(". ")
            if fragment.strip() and fragment.strip() not in existing_fragments
        ]
        if new_fragments:
            context_for_query = (
                context_for_query
                + "\n\n--- Sección de Experiencia Específica ---\n"
                + ". ".join(new_fragments)
            )

    user_message = qna_user_message_experience
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)

    llm_response = run_llm_indices(qna_system_message_experience, user_message)

    if "sorry" in llm_response.lower():
        logger.warning("[_get_experience_rag] No se encontró contexto de experiencia")
        return None, ""

    try:
        parsed_response = ExperienceResponse.model_validate_json(llm_response)
    except Exception as e:
        logger.error("[_get_experience_rag] Error parseando respuesta: %s", e)
        return None, ""

    return parsed_response, context_for_query


def get_general_info(user_input: str, k: int):
    docs, _ = load_docs()
    chunks = chunk_docs(docs)

    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever(vectorStore, k)

    context_for_query = build_context(retriever, chunks, user_input, k=k)
    return context_for_query
