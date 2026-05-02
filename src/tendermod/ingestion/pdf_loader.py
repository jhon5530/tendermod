import logging
from glob import glob
from pathlib import Path

import fitz
import pymupdf4llm
from langchain_core.documents import Document

from tendermod.config.settings import ROOT_DIR

logger = logging.getLogger(__name__)

_MIN_TEXT_CHARS = 50  # Páginas con menos chars → tratadas como imagen escaneada


def _is_scanned(pdf_path: str) -> bool:
    """Detecta si un PDF es predominantemente escaneado (sin capa de texto digital)."""
    doc = fitz.open(pdf_path)
    if not doc:
        return False
    scanned = sum(1 for p in doc if len(p.get_text().strip()) < _MIN_TEXT_CHARS)
    return scanned > len(doc) * 0.5


def load_docs(ocr_language: str = "spa") -> tuple[list[Document], bool]:
    """
    Carga PDFs usando pymupdf4llm → Markdown estructurado con headers y tablas.
    Para PDFs escaneados activa OCR con Tesseract (idioma español).
    Retorna (documentos, ocr_aplicado).
    """
    all_documents: list[Document] = []
    ocr_applied = False
    pdf_files = glob(str(ROOT_DIR / "data" / "*.pdf"))
    logger.info("[load_docs] PDFs encontrados: %s", pdf_files)

    for pdf_path in pdf_files:
        scanned = _is_scanned(pdf_path)

        kwargs = {"show_progress": False, "page_chunks": True}
        if scanned:
            kwargs["ocr_languages"] = ocr_language
            logger.info("[load_docs] PDF escaneado detectado — activando OCR (%s)", pdf_path)

        page_chunks: list[dict] = pymupdf4llm.to_markdown(pdf_path, **kwargs)

        if scanned:
            ocr_applied = True
            logger.info(
                "[load_docs] OCR completado: %s (%d páginas)",
                Path(pdf_path).name, len(page_chunks),
            )

        for chunk in page_chunks:
            text = chunk.get("text", "").strip()
            page_num = chunk.get("metadata", {}).get("page_number", 1) - 1  # 0-based
            all_documents.append(Document(
                page_content=text,
                metadata={"source": pdf_path, "page": page_num},
            ))

    return all_documents, ocr_applied
