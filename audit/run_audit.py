#!/usr/bin/env python3
"""
Framework de auditoría tendermod vs Gold Standard Claude Cowork.

Uso:
  # Procesar todos los PDFs con Gold Standard disponible
  python audit/run_audit.py --all

  # Procesar un PDF específico
  python audit/run_audit.py --pdf "GOLD EXAMPLES/ANE - PLIEGO DE CONDICIONES.pdf"

  # Solo conteos (sin embeddings — más rápido y sin costo extra de API)
  python audit/run_audit.py --all --no-semantic

El Gold Standard Excel debe tener el mismo nombre base que el PDF:
  "GOLD EXAMPLES/ANE - PLIEGO DE CONDICIONES.pdf"
  "GOLD EXAMPLES/ANE - PLIEGO DE CONDICIONES.xlsx"  ← Gold Standard
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project src is importable when running from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("audit")

_GOLD_DIR = _PROJECT_ROOT / "GOLD EXAMPLES"
_OUTPUT_DIR = _PROJECT_ROOT / "audit"


def _find_pairs(gold_dir: Path) -> list[tuple[Path, Path]]:
    """Return list of (pdf_path, xlsx_path) pairs where both files exist."""
    pairs: list[tuple[Path, Path]] = []
    for pdf in sorted(gold_dir.glob("*.pdf")):
        xlsx = pdf.with_suffix(".xlsx")
        if xlsx.exists():
            pairs.append((pdf, xlsx))
        else:
            logger.warning("Sin Gold Standard para: %s (esperado: %s)", pdf.name, xlsx.name)
    return pairs


def run_single(pdf_path: Path, xlsx_path: Path, semantic: bool) -> object:
    """Run extraction + comparison for one PDF. Returns ComparisonResult."""
    from audit.gold_parser import parse_gold_standard
    from audit.tendermod_runner import run_extraction
    from audit.comparator import compare

    logger.info("=" * 60)
    logger.info("PDF: %s", pdf_path.name)
    logger.info("Gold Standard: %s", xlsx_path.name)
    logger.info("Semántico: %s", semantic)
    logger.info("=" * 60)

    logger.info("[1/3] Parseando Gold Standard...")
    gold = parse_gold_standard(xlsx_path, pdf_path.name)
    logger.info(
        "  Gold: %d reqs, %d indicadores, %d segmentos experiencia",
        len(gold.requirements), len(gold.indicators), len(gold.experience),
    )

    logger.info("[2/3] Ejecutando extracción tendermod (ingest + requirements + indicators + experience)...")
    tm_result = run_extraction(pdf_path)
    tm_reqs = tm_result.requirements.requisitos if tm_result.requirements else []
    tm_inds = tm_result.indicators.answer if tm_result.indicators else []
    logger.info(
        "  TM: %d reqs, %d indicadores — tiempo total: %.1fs",
        len(tm_reqs), len(tm_inds), tm_result.time_total,
    )
    if tm_result.errors:
        logger.warning("  Errores: %s", tm_result.errors)

    logger.info("[3/3] Comparando...")
    comparison = compare(gold, tm_result, semantic=semantic)
    if semantic:
        logger.info(
            "  Recall: %.1f%% | Precision: %.1f%% | F1: %.1f%%",
            comparison.recall * 100, comparison.precision * 100, comparison.f1 * 100,
        )
    logger.info("  Gaps (Gold no capturado): %d", len(comparison.gold_unmatched))
    logger.info("  Ruido (TM sin match Gold): %d", len(comparison.tm_unmatched))

    # attach errors list for reporter
    comparison._errors = tm_result.errors

    return comparison


def main():
    parser = argparse.ArgumentParser(
        description="Auditoría tendermod vs Gold Standard Claude Cowork"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Procesar todos los PDFs con Gold Standard en GOLD EXAMPLES/")
    group.add_argument("--pdf", type=str, help="Path al PDF específico a procesar")
    parser.add_argument(
        "--no-semantic", action="store_true",
        help="Omitir matching semántico (solo conteos, más rápido y sin costo API extra)"
    )
    args = parser.parse_args()

    semantic = not args.no_semantic

    if args.all:
        pairs = _find_pairs(_GOLD_DIR)
        if not pairs:
            logger.error(
                "No se encontraron pares PDF+Excel en '%s'. "
                "Agrega archivos .xlsx con el mismo nombre base que los PDFs.",
                _GOLD_DIR,
            )
            sys.exit(1)
    else:
        pdf_path = Path(args.pdf)
        if not pdf_path.is_absolute():
            pdf_path = _PROJECT_ROOT / pdf_path
        xlsx_path = pdf_path.with_suffix(".xlsx")
        if not pdf_path.exists():
            logger.error("PDF no encontrado: %s", pdf_path)
            sys.exit(1)
        if not xlsx_path.exists():
            logger.error("Gold Standard no encontrado: %s", xlsx_path)
            sys.exit(1)
        pairs = [(pdf_path, xlsx_path)]

    logger.info("PDFs a procesar: %d", len(pairs))

    results = []
    for pdf_path, xlsx_path in pairs:
        try:
            comparison = run_single(pdf_path, xlsx_path, semantic=semantic)
            results.append(comparison)
        except Exception as exc:
            logger.error("Error procesando %s: %s", pdf_path.name, exc, exc_info=True)

    if not results:
        logger.error("Ningún PDF procesado correctamente.")
        sys.exit(1)

    logger.info("Generando reportes...")
    from audit.reporter import generate_report
    md_path, xlsx_out = generate_report(results, _OUTPUT_DIR)
    logger.info("Informe Markdown: %s", md_path)
    logger.info("Resultados Excel: %s", xlsx_out)
    logger.info("Auditoría completada.")


if __name__ == "__main__":
    main()
