import logging
from pathlib import Path

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import run_llm_indices
from tendermod.evaluation.prompts import qna_general_info, qna_system_message_indices, qna_user_message_indices
from tendermod.evaluation.schemas import MultipleIndicatorResponse
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever
from tendermod.retrieval.vectorstore import read_vectorstore

logger = logging.getLogger(__name__)

_INDICATOR_KEYWORDS = [
    "financiero", "financiera", "indicador", "capacidad",
    "liquidez", "endeudamiento", "cobertura", "capital de trabajo",
]
_MAX_INDICATOR_CHARS = 40_000


def _get_pdf_path() -> str:
    data_dir = Path(CHROMA_PERSIST_DIR).parent
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def get_indicators(user_input: str, k) -> tuple:
    """
    Extrae indicadores financieros del pliego.
    Intenta primero por capítulos completos del PDF (determinístico), fallback a RAG.
    """
    from tendermod.ingestion.chapter_extractor import get_chapter_ranges, extract_page_range

    try:
        pdf_path = _get_pdf_path()
        chapters = get_chapter_ranges(pdf_path, use_llm=True)

        ind_chapters = [
            ch for ch in chapters
            if any(kw in ch["title"].lower() for kw in _INDICATOR_KEYWORDS)
        ]

        if ind_chapters:
            first_page = ind_chapters[0]["start_page"]
            last_page = ind_chapters[-1]["end_page"]
            combined_text = extract_page_range(pdf_path, first_page, last_page)
            if len(combined_text) > _MAX_INDICATOR_CHARS:
                logger.warning("[get_indicators] Contexto truncado a %d chars", _MAX_INDICATOR_CHARS)
                combined_text = combined_text[:_MAX_INDICATOR_CHARS]

            if combined_text.strip():
                logger.info(
                    "[get_indicators] Extrayendo desde %d capítulos (págs %d–%d, %d chars)",
                    len(ind_chapters), first_page + 1, last_page, len(combined_text),
                )
                user_message = qna_user_message_indices
                user_message = user_message.replace('{context}', combined_text)
                user_message = user_message.replace('{question}', user_input)
                llm_response = run_llm_indices(qna_system_message_indices, user_message)

                try:
                    parsed = MultipleIndicatorResponse.model_validate_json(llm_response)
                    logger.info("[get_indicators] Capítulos: %d indicadores extraídos", len(parsed.answer))
                    return parsed, combined_text
                except Exception as e:
                    logger.warning("[get_indicators] Error parseando respuesta de capítulos: %s", e)

    except Exception as exc:
        logger.warning("[get_indicators] Error en extracción por capítulos: %s — usando RAG", exc)

    return _get_indicators_rag(user_input, k)


def _get_indicators_rag(user_input: str, k) -> tuple:
    """Extracción de indicadores usando RAG (ChromaDB). Fallback del flujo principal."""
    docs, _ = load_docs()
    chunks = chunk_docs(docs)

    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever(vectorStore, k)
    context_for_query = build_context(retriever, chunks, user_input, k=k)

    user_message = qna_user_message_indices
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)
    llm_response = run_llm_indices(qna_system_message_indices, user_message)

    try:
        parsed_response = MultipleIndicatorResponse.model_validate_json(llm_response)
        return parsed_response, context_for_query
    except Exception as e:
        logger.error("[_get_indicators_rag] Error parseando respuesta: %s", e)
        return None, ""


def get_general_info(user_input: str, k):
    docs, _ = load_docs()
    chunks = chunk_docs(docs)

    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever(vectorStore, k)
    context_for_query = build_context(retriever, chunks, user_input, k=k)

    user_message = qna_user_message_indices
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)
    llm_response = run_llm_indices(qna_general_info, user_message)

    return llm_response
