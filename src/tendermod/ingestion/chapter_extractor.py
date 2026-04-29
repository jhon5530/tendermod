"""
Extrae texto del PDF por rangos de página para extracción de requerimientos sin RAG.

Estrategia de detección de límites de capítulo (en orden de prioridad):
1. TOC nativo de PyMuPDF (doc.get_toc()) — instantáneo, sin costo LLM.
2. LLM sobre primeras páginas — cuando el PDF no tiene outline nativo (ej. FNA test9.pdf).
3. Heurística de texto — fallback final sin costo adicional.
"""
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

REQUIREMENT_KEYWORDS = [
    "habilitante", "requisito", "rechazo", "causal", "garantía", "garantia",
    "póliza", "poliza", "evaluación", "evaluacion", "puntaje", "capacidad",
    "experiencia", "jurídico", "juridico", "técnico", "tecnico", "financiero",
    "documental", "formulario", "formato", "anexo", "criterio", "condición",
    "condicion", "inhabilidad", "inhabilidades",
]

_SECTION_HEADER_PATTERN = re.compile(
    r"^(?:CAP[IÍ]TULO\s+\d+|\d+(?:\.\d+){0,3})\s+\S",
    re.MULTILINE | re.IGNORECASE,
)


def extract_page_range(pdf_path: str, start_page: int, end_page: int) -> str:
    """Extrae el texto de las páginas [start_page, end_page) — índice 0-based."""
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(start_page, min(end_page, len(doc))):
        pages.append(doc[i].get_text())
    doc.close()
    return "\n".join(pages)


def extract_full_text(pdf_path: str) -> str:
    """Extrae el texto completo del PDF."""
    doc = fitz.open(pdf_path)
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return "\n".join(pages)


def get_chapter_ranges_native(pdf_path: str) -> list[dict]:
    """
    Obtiene rangos de capítulo usando el TOC nativo del PDF (PyMuPDF outline).
    Retorna [] si el PDF no tiene outline nativo.
    """
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()  # [(level, title, page_1based), ...]
    n_pages = len(doc)
    doc.close()

    if not toc:
        logger.info("[chapter_extractor] TOC nativo vacío en %s", pdf_path)
        return []

    entries = [{"title": t, "start": p - 1} for _, t, p in toc]
    chapters = []
    for i, entry in enumerate(entries):
        end = entries[i + 1]["start"] if i + 1 < len(entries) else n_pages
        chapters.append({
            "title": entry["title"],
            "start_page": max(0, entry["start"]),
            "end_page": end,
        })

    logger.info("[chapter_extractor] TOC nativo: %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def get_chapter_ranges_llm(pdf_path: str, n_pages_scan: int = 10) -> list[dict]:
    """
    Detecta capítulos enviando las primeras n_pages_scan páginas al LLM.
    Usado cuando el TOC nativo está vacío (ej. FNA test9.pdf).
    """
    doc = fitz.open(pdf_path)
    n_total = len(doc)
    first_pages_text = "\n".join(
        f"[Página {i + 1}]\n{doc[i].get_text()}"
        for i in range(min(n_pages_scan, n_total))
    )
    doc.close()

    from tendermod.evaluation.llm_client import run_llm_chapter_detection
    chapters_raw = run_llm_chapter_detection(first_pages_text, n_total)

    chapters = []
    for ch in chapters_raw:
        start = max(0, ch.get("start_page", 1) - 1)
        end = min(n_total, ch.get("end_page", n_total))
        chapters.append({
            "title": ch.get("title", ""),
            "start_page": start,
            "end_page": end,
        })

    logger.info("[chapter_extractor] LLM detectó %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def get_chapter_ranges_heuristic(pdf_path: str) -> list[dict]:
    """
    Detecta capítulos por heurística: busca líneas que comiencen con numerales
    o la palabra CAPÍTULO. Fallback de último recurso.
    """
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    boundaries = []
    for i in range(n_pages):
        text = doc[i].get_text()
        match = _SECTION_HEADER_PATTERN.search(text)
        if match:
            title = match.group(0).strip()[:80]
            boundaries.append({"title": title, "start_page": i})
    doc.close()

    if not boundaries:
        logger.warning(
            "[chapter_extractor] Heurística no detectó estructura en %s — bloque único", pdf_path
        )
        return [{"title": "Documento completo", "start_page": 0, "end_page": n_pages}]

    chapters = []
    for i, b in enumerate(boundaries):
        end = boundaries[i + 1]["start_page"] if i + 1 < len(boundaries) else n_pages
        chapters.append({
            "title": b["title"],
            "start_page": b["start_page"],
            "end_page": end,
        })
    logger.info("[chapter_extractor] Heurística: %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def validate_chapter_ranges(chapters: list[dict], n_total_pages: int) -> list[dict]:
    """Clamp, ordena y elimina solapamientos entre rangos de capítulo."""
    valid = []
    for ch in chapters:
        start = max(0, min(ch.get("start_page", 0), n_total_pages - 1))
        end = max(start + 1, min(ch.get("end_page", n_total_pages), n_total_pages))
        valid.append({**ch, "start_page": start, "end_page": end})

    valid.sort(key=lambda c: c["start_page"])

    for i in range(len(valid) - 1):
        if valid[i]["end_page"] > valid[i + 1]["start_page"]:
            valid[i]["end_page"] = valid[i + 1]["start_page"]

    return [ch for ch in valid if ch["start_page"] < ch["end_page"]]


def get_chapter_ranges(pdf_path: str, use_llm: bool = True) -> list[dict]:
    """
    Punto de entrada unificado. Intentos en orden:
    1. TOC nativo (gratuito, instantáneo).
    2. LLM sobre primeras páginas (si use_llm=True).
    3. Heurística de texto (siempre disponible).
    """
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    chapters = get_chapter_ranges_native(pdf_path)
    if not chapters and use_llm:
        try:
            chapters = get_chapter_ranges_llm(pdf_path)
        except Exception as exc:
            logger.warning(
                "[chapter_extractor] LLM fallback falló: %s — usando heurística", exc
            )

    if not chapters:
        chapters = get_chapter_ranges_heuristic(pdf_path)

    return validate_chapter_ranges(chapters, n_pages)


def filter_relevant_chapters(chapters: list[dict]) -> list[dict]:
    """
    Filtra capítulos que probablemente contengan requerimientos,
    usando REQUIREMENT_KEYWORDS en el título.
    Si ningún título matchea, incluye todos (títulos atípicos).
    """
    relevant = [
        ch for ch in chapters
        if any(kw in ch["title"].lower() for kw in REQUIREMENT_KEYWORDS)
    ]
    if not relevant:
        logger.warning(
            "[chapter_extractor] Ningún capítulo con keywords — incluyendo todos (%d)",
            len(chapters),
        )
        return chapters
    logger.info(
        "[chapter_extractor] %d/%d capítulos relevantes seleccionados",
        len(relevant), len(chapters),
    )
    return relevant
