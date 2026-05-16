"""
Run tendermod extraction pipeline on a given PDF, standalone (no Django/Celery).

The ingestion pipeline requires the PDF to be at data/*.pdf. This module
swaps the current PDF in data/ with the target, runs extraction, then restores.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_INDICATOR_QUERY = "indicadores financieros capacidad organizacional liquidez endeudamiento cobertura"
_EXPERIENCE_QUERY = "experiencia específica contratos UNSPSC objeto acreditado"


@dataclass
class ExtractionResult:
    pdf_name: str
    requirements: object = None       # GeneralRequirementList | None
    indicators: object = None         # MultipleIndicatorResponse | None
    experience: object = None         # ExperienceResponse | None
    time_ingest: float = 0.0
    time_requirements: float = 0.0
    time_indicators: float = 0.0
    time_experience: float = 0.0
    time_total: float = 0.0
    errors: list[str] = field(default_factory=list)


def _swap_pdf_in(pdf_path: Path, data_dir: Path, backup_dir: Path) -> list[Path]:
    """Move existing PDFs from data/ to backup_dir; copy target PDF to data/."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed_up: list[Path] = []
    for existing in data_dir.glob("*.pdf"):
        dest = backup_dir / existing.name
        shutil.move(str(existing), str(dest))
        backed_up.append(dest)
        logger.debug("Backup: %s → %s", existing.name, dest)

    shutil.copy2(str(pdf_path), str(data_dir / pdf_path.name))
    logger.debug("Copied %s → data/", pdf_path.name)
    return backed_up


def _restore_pdf(data_dir: Path, backup_dir: Path, backed_up: list[Path], audit_pdf_name: str):
    """Remove audit PDF from data/ and restore originals from backup."""
    audit_pdf = data_dir / audit_pdf_name
    if audit_pdf.exists():
        audit_pdf.unlink()

    for src in backed_up:
        dest = data_dir / src.name
        shutil.move(str(src), str(dest))
        logger.debug("Restored: %s", dest.name)

    # clean backup dir if empty
    try:
        backup_dir.rmdir()
    except OSError:
        pass


def run_extraction(pdf_path: Path) -> ExtractionResult:
    """
    Run full tendermod extraction on pdf_path.
    Temporarily copies the PDF to data/, runs ingest + extract, then restores.
    """
    from tendermod.config.settings import ROOT_DIR, CHROMA_PERSIST_DIR  # noqa: F401

    result = ExtractionResult(pdf_name=pdf_path.name)
    data_dir = Path(ROOT_DIR) / "data"
    backup_dir = data_dir / ".audit_backup"

    total_start = time.perf_counter()
    backed_up: list[Path] = []

    try:
        backed_up = _swap_pdf_in(pdf_path, data_dir, backup_dir)

        # --- Ingestion ---
        from tendermod.ingestion.ingestion_flow import ingest_documents
        t0 = time.perf_counter()
        try:
            ingest_documents()
        except Exception as exc:
            msg = f"Ingesta fallida: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            return result
        result.time_ingest = time.perf_counter() - t0
        logger.info("[runner] Ingest: %.1fs", result.time_ingest)

        # --- General Requirements ---
        from tendermod.evaluation.general_requirements_inference import get_general_requirements
        t0 = time.perf_counter()
        try:
            result.requirements = get_general_requirements(k=3)
        except Exception as exc:
            msg = f"Requisitos generales fallido: {exc}"
            logger.error(msg)
            result.errors.append(msg)
        result.time_requirements = time.perf_counter() - t0
        logger.info("[runner] Requirements: %.1fs", result.time_requirements)

        # --- Indicators ---
        from tendermod.evaluation.indicators_inference import get_indicators
        t0 = time.perf_counter()
        try:
            indicators_resp, _ = get_indicators(_INDICATOR_QUERY, k=8)
            result.indicators = indicators_resp
        except Exception as exc:
            msg = f"Indicadores fallido: {exc}"
            logger.error(msg)
            result.errors.append(msg)
        result.time_indicators = time.perf_counter() - t0
        logger.info("[runner] Indicators: %.1fs", result.time_indicators)

        # --- Experience ---
        from tendermod.evaluation.experience_inference import get_experience
        t0 = time.perf_counter()
        try:
            exp_resp, _ = get_experience(_EXPERIENCE_QUERY, k=8)
            result.experience = exp_resp
        except Exception as exc:
            msg = f"Experiencia fallida: {exc}"
            logger.error(msg)
            result.errors.append(msg)
        result.time_experience = time.perf_counter() - t0
        logger.info("[runner] Experience: %.1fs", result.time_experience)

    finally:
        _restore_pdf(data_dir, backup_dir, backed_up, pdf_path.name)

    result.time_total = time.perf_counter() - total_start
    logger.info("[runner] Total: %.1fs — errors: %d", result.time_total, len(result.errors))
    return result
