"""
Extrae texto del PDF por rangos de página para extracción de requerimientos sin RAG.

Estrategia de detección de límites de capítulo (en orden de prioridad):
1. TOC nativo de PyMuPDF (doc.get_toc()) — instantáneo, sin costo LLM.
2. LLM sobre primeras 25 páginas — cuando el PDF no tiene outline nativo.
3. Detección visual por tipografía — analiza tamaño y negrita de spans para
   identificar headers sin depender de numeración ni TOC.
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
    "verificacion", "verificación",
    "documentos",
    "requerimiento",
    "propuesta", "oferta",
    "seleccion", "selección",
    "adjudicacion", "adjudicación",
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


def get_chapter_ranges_llm(pdf_path: str, n_pages_scan: int = 25) -> list[dict]:
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


def get_chapter_ranges_visual(pdf_path: str) -> list[dict]:
    """
    Detecta capítulos usando atributos tipográficos (tamaño y negrita) de cada span.
    Funciona para cualquier PDF sin TOC ni numeración estándar.

    Algoritmo:
    1. Determinar el tamaño de cuerpo del documento (tamaño más frecuente por chars).
    2. Identificar como header spans con tamaño >= cuerpo+1.5pt, negrita, o MAYÚSCULAS.
    3. El primer header significativo de cada página es el título de sección.
    4. Cada página con header marca el inicio de un nuevo capítulo.
    """
    doc = fitz.open(pdf_path)
    n_pages = len(doc)

    # ── Paso 1: tamaño de cuerpo ──────────────────────────────────────────────
    size_weight: dict[int, int] = {}
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    size = round(span["size"])
                    if text and 7 <= size <= 18:
                        size_weight[size] = size_weight.get(size, 0) + len(text)

    if not size_weight:
        doc.close()
        logger.warning("[chapter_extractor] Visual: no se encontraron spans de texto útiles")
        return _fallback_single_block(pdf_path, n_pages)

    body_size = max(size_weight, key=size_weight.get)
    header_min_size = body_size + 1.5

    logger.info(
        "[chapter_extractor] Visual: cuerpo=%.0fpt, umbral header=%.1fpt",
        body_size, header_min_size,
    )

    # ── Paso 2: detectar el primer header significativo de cada página ────────
    boundaries: list[dict] = []

    for page_num, page in enumerate(doc):
        page_h = page.rect.height
        top_skip = page_h * 0.08     # ignorar encabezado de página (8% superior)
        bottom_skip = page_h * 0.92  # ignorar pie de página (8% inferior)

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            block_y = block.get("bbox", [0, 0, 0, 0])[1]
            if block_y < top_skip or block_y > bottom_skip:
                continue

            header_lines: list[str] = []
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = " ".join(s["text"] for s in spans).strip()
                if len(text) < 5:
                    continue

                size = spans[0]["size"]
                is_bold = bool(spans[0]["flags"] & 16)
                is_caps = text.isupper() and len(text) > 6

                is_header = (
                    size >= header_min_size
                    or (is_bold and size >= body_size - 0.5 and len(text) <= 100)
                    or (is_caps and size >= body_size - 0.5)
                )

                if is_header:
                    header_lines.append(text)
                elif header_lines:
                    break  # fin del bloque de header

            if header_lines:
                title = " ".join(header_lines[:3])[:120].strip()
                boundaries.append({"title": title, "start_page": page_num})
                break  # un solo header por página

    doc.close()

    if not boundaries:
        logger.warning("[chapter_extractor] Visual: no se detectaron headers tipográficos")
        return _fallback_single_block(pdf_path, n_pages)

    # ── Paso 3: deduplicar headers repetidos en páginas contiguas ────────────
    deduped: list[dict] = [boundaries[0]]
    for b in boundaries[1:]:
        prev = deduped[-1]
        same_title = b["title"][:40].lower() == prev["title"][:40].lower()
        adjacent = b["start_page"] <= prev["start_page"] + 2
        if same_title and adjacent:
            continue
        deduped.append(b)

    # ── Paso 4: construir rangos de capítulo ──────────────────────────────────
    chapters = []
    for i, b in enumerate(deduped):
        end = deduped[i + 1]["start_page"] if i + 1 < len(deduped) else n_pages
        chapters.append({
            "title": b["title"],
            "start_page": b["start_page"],
            "end_page": end,
        })

    logger.info(
        "[chapter_extractor] Visual: %d capítulos detectados en %s",
        len(chapters), pdf_path,
    )
    return chapters


def _fallback_single_block(pdf_path: str, n_pages: int) -> list[dict]:
    """Último recurso: tratar el PDF completo como un solo bloque."""
    logger.warning(
        "[chapter_extractor] Sin estructura detectable en %s — bloque único", pdf_path
    )
    return [{"title": "Documento completo", "start_page": 0, "end_page": n_pages}]


def validate_chapter_ranges(chapters: list[dict], n_total_pages: int) -> list[dict]:
    """Clamp, ordena y elimina solapamientos entre rangos de capítulo.

    Cuando dos entradas del TOC comparten la misma página física (ej. "2.4 EXPERIENCIA
    GENERAL" y "2.5 CRITERIOS" ambas en página 32), la resolución de solapamientos deja
    la primera con rango 0. En ese caso extendemos el capítulo precedente para que
    absorba esa página, preservando el contenido que de otro modo se perdería.
    """
    valid = []
    for ch in chapters:
        start = max(0, min(ch.get("start_page", 0), n_total_pages - 1))
        end = max(start + 1, min(ch.get("end_page", n_total_pages), n_total_pages))
        valid.append({**ch, "start_page": start, "end_page": end})

    valid.sort(key=lambda c: c["start_page"])

    for i in range(len(valid) - 1):
        if valid[i]["end_page"] > valid[i + 1]["start_page"]:
            valid[i]["end_page"] = valid[i + 1]["start_page"]

    # Capítulos que quedaron con 0 páginas tras la resolución de solapamientos
    # (ocurre cuando varios TOC entries apuntan a la misma página física).
    # Extender el capítulo anterior en 1 página para preservar ese contenido.
    result = []
    for ch in valid:
        if ch["start_page"] >= ch["end_page"]:
            if result and result[-1]["end_page"] == ch["start_page"]:
                result[-1]["end_page"] = min(ch["start_page"] + 1, n_total_pages)
        else:
            result.append(ch)

    return result


_COVERAGE_THRESHOLD = 0.40  # Si el LLM cubre < 40% del doc, complementar con visual.


def get_chapter_ranges(pdf_path: str, use_llm: bool = True) -> list[dict]:
    """
    Punto de entrada unificado. Intentos en orden:
    1. TOC nativo (gratuito, instantáneo).
    2. LLM sobre primeras 25 páginas (si use_llm=True).
       Si el LLM cubre < 40% del documento, se complementa con detección visual
       para las páginas no cubiertas (PDFs largos sin índice al inicio).
    3. Detección visual por tipografía (tamaño/negrita de spans).
    """
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    chapters = get_chapter_ranges_native(pdf_path)
    if not chapters and use_llm:
        try:
            chapters = get_chapter_ranges_llm(pdf_path)

            # Verificar cobertura: si el LLM sólo detectó capítulos en la primera
            # fracción del documento, complementar con detección visual para el resto.
            if chapters:
                validated_llm = validate_chapter_ranges(chapters, n_pages)
                last_covered = max(ch["end_page"] for ch in validated_llm) if validated_llm else 0
                coverage = last_covered / n_pages if n_pages else 1.0
                if coverage < _COVERAGE_THRESHOLD:
                    logger.warning(
                        "[chapter_extractor] LLM cubrió sólo %.0f%% del doc (%d/%d págs) — "
                        "complementando con detección visual desde pág %d",
                        100 * coverage, last_covered, n_pages, last_covered + 1,
                    )
                    visual = get_chapter_ranges_visual(pdf_path)
                    extra = [ch for ch in visual if ch["start_page"] >= last_covered]
                    logger.info(
                        "[chapter_extractor] Visual aportó %d capítulos adicionales (págs %d–%d)",
                        len(extra),
                        extra[0]["start_page"] + 1 if extra else last_covered + 1,
                        extra[-1]["end_page"] if extra else last_covered + 1,
                    )
                    return validate_chapter_ranges(validated_llm + extra, n_pages)

        except Exception as exc:
            logger.warning(
                "[chapter_extractor] LLM falló: %s — usando detección visual", exc
            )

    if not chapters:
        chapters = get_chapter_ranges_visual(pdf_path)

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
    if len(chapters) != len(relevant):
        discarded_titles = [ch["title"] for ch in chapters if ch not in relevant]
        logger.info("[chapter_extractor] Capítulos descartados por keywords: %s", discarded_titles)
    return relevant
