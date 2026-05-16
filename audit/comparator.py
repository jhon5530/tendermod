"""
Compare Gold Standard requirements against tendermod extraction results.

Uses:
  - Count comparison: totals and per-category breakdowns
  - Semantic matching: cosine similarity via OpenAI text-embedding-3-small
  - Indicator comparison: name matching + threshold comparison
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from audit.gold_parser import GoldStandard, GoldRequirement, GoldIndicator

SEMANTIC_THRESHOLD = 0.78
INDICATOR_NAME_THRESHOLD = 0.85
INDICATOR_VALUE_TOLERANCE = 0.05  # 5% tolerance for threshold comparison


@dataclass
class IndicatorMatch:
    gold_name: str
    gold_threshold_raw: str
    gold_threshold_valor: Optional[float]
    gold_umbral_condicion: str
    tm_name: str = ""
    tm_value: str = ""
    name_score: float = 0.0
    matched: bool = False
    threshold_ok: Optional[bool] = None  # None = not comparable


@dataclass
class ComparisonResult:
    pdf_name: str
    counts: dict = field(default_factory=dict)
    recall: float = 0.0
    precision: float = 0.0
    f1: float = 0.0
    matched_pairs: list[dict] = field(default_factory=list)
    gold_unmatched: list[dict] = field(default_factory=list)
    tm_unmatched: list[dict] = field(default_factory=list)
    indicator_matches: list[IndicatorMatch] = field(default_factory=list)
    experience_summary: dict = field(default_factory=dict)
    time_total_extraction: float = 0.0
    time_comparison: float = 0.0
    semantic_used: bool = False


def _get_embeddings(texts: list[str]) -> np.ndarray:
    """Batch-embed texts using OpenAI text-embedding-3-small."""
    from langchain_openai import OpenAIEmbeddings
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")
    vectors = embedder.embed_documents(texts)
    return np.array(vectors, dtype=np.float32)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity between rows of a (n,d) and rows of b (m,d). Returns (n,m) matrix."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return a_norm @ b_norm.T


def _req_as_dict(r: GoldRequirement) -> dict:
    return {
        "id": r.id,
        "descripcion": r.descripcion,
        "categoria": r.categoria,
        "tipo": r.tipo,
        "seccion": r.seccion,
        "nombre": r.nombre,
    }


def _tm_req_as_dict(r) -> dict:
    return {
        "descripcion": r.descripcion,
        "categoria": r.categoria,
        "tipo": r.tipo,
        "seccion": r.seccion,
        "pagina": r.pagina,
    }


def _parse_tm_value(val_str: str) -> Optional[float]:
    """Parse tendermod indicator value string to float."""
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d,\.\-]", "", str(val_str)).replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _build_counts(gold: GoldStandard, tm_result) -> dict:
    gold_cats = Counter(r.categoria for r in gold.requirements)
    tm_reqs = tm_result.requirements.requisitos if tm_result.requirements else []
    tm_cats = Counter(r.categoria for r in tm_reqs)

    exp_resp = tm_result.experience
    tm_experience_summary = {}
    if exp_resp:
        tm_experience_summary = {
            "modo": exp_resp.modo_evaluacion,
            "codigos": exp_resp.listado_codigos,
            "cantidad_contratos": exp_resp.cantidad_contratos,
            "valor": exp_resp.valor,
            "objeto": exp_resp.objeto,
        }

    return {
        "gold_total_reqs": len(gold.requirements),
        "tendermod_total_reqs": len(tm_reqs),
        "gold_by_category": dict(gold_cats),
        "tendermod_by_category": dict(tm_cats),
        "gold_indicators_count": len(gold.indicators),
        "tendermod_indicators_count": len(tm_result.indicators.answer) if tm_result.indicators else 0,
        "gold_experience_segments": len(gold.experience),
        "tendermod_experience": tm_experience_summary,
    }


def _compare_indicators(gold_indicators: list[GoldIndicator], tm_result) -> list[IndicatorMatch]:
    if not gold_indicators:
        return []
    tm_inds = tm_result.indicators.answer if tm_result.indicators else []
    if not tm_inds:
        return [IndicatorMatch(
            gold_name=gi.nombre,
            gold_threshold_raw=gi.umbral_raw,
            gold_threshold_valor=gi.umbral_valor,
            gold_umbral_condicion=gi.umbral_condicion,
            matched=False,
        ) for gi in gold_indicators]

    gold_names = [gi.nombre for gi in gold_indicators]
    tm_names = [ti.indicador for ti in tm_inds]

    gold_vecs = _get_embeddings(gold_names)
    tm_vecs = _get_embeddings(tm_names)
    sim_matrix = _cosine_sim(gold_vecs, tm_vecs)

    matches: list[IndicatorMatch] = []
    for i, gi in enumerate(gold_indicators):
        best_j = int(np.argmax(sim_matrix[i]))
        best_score = float(sim_matrix[i, best_j])
        matched = best_score >= INDICATOR_NAME_THRESHOLD
        tm_ind = tm_inds[best_j] if matched else None

        threshold_ok = None
        if matched and gi.umbral_valor is not None and tm_ind:
            tm_val = _parse_tm_value(str(tm_ind.valor))
            if tm_val is not None:
                diff = abs(tm_val - gi.umbral_valor)
                rel_diff = diff / (abs(gi.umbral_valor) + 1e-10)
                threshold_ok = rel_diff <= INDICATOR_VALUE_TOLERANCE

        matches.append(IndicatorMatch(
            gold_name=gi.nombre,
            gold_threshold_raw=gi.umbral_raw,
            gold_threshold_valor=gi.umbral_valor,
            gold_umbral_condicion=gi.umbral_condicion,
            tm_name=tm_ind.indicador if tm_ind else "",
            tm_value=str(tm_ind.valor) if tm_ind else "",
            name_score=best_score,
            matched=matched,
            threshold_ok=threshold_ok,
        ))
    return matches


def compare(gold: GoldStandard, tm_result, semantic: bool = True) -> ComparisonResult:
    """
    Compare Gold Standard against a tendermod ExtractionResult.

    Args:
        gold: parsed Gold Standard
        tm_result: ExtractionResult from tendermod_runner
        semantic: if True, compute embedding-based requirement matching
    """
    t_start = time.perf_counter()
    result = ComparisonResult(
        pdf_name=gold.pdf_name,
        time_total_extraction=tm_result.time_total,
        semantic_used=semantic,
    )

    result.counts = _build_counts(gold, tm_result)

    # --- Indicator comparison (uses embeddings for names) ---
    if gold.indicators and (tm_result.indicators and tm_result.indicators.answer):
        result.indicator_matches = _compare_indicators(gold.indicators, tm_result)
    else:
        result.indicator_matches = [IndicatorMatch(
            gold_name=gi.nombre,
            gold_threshold_raw=gi.umbral_raw,
            gold_threshold_valor=gi.umbral_valor,
            gold_umbral_condicion=gi.umbral_condicion,
            matched=False,
        ) for gi in gold.indicators]

    # --- Experience summary ---
    if tm_result.experience:
        exp = tm_result.experience
        result.experience_summary = {
            "codigos_requeridos": exp.listado_codigos,
            "modo": exp.modo_evaluacion,
            "valor": exp.valor,
            "cantidad_contratos": exp.cantidad_contratos,
            "objeto": exp.objeto,
            "gold_segments": [s.nombre for s in gold.experience],
        }

    if not semantic:
        result.time_comparison = time.perf_counter() - t_start
        return result

    # --- Semantic requirement matching ---
    tm_reqs = tm_result.requirements.requisitos if tm_result.requirements else []
    gold_reqs = gold.requirements

    if not gold_reqs or not tm_reqs:
        result.recall = 0.0 if gold_reqs else 1.0
        result.precision = 0.0 if not tm_reqs else 1.0
        result.gold_unmatched = [_req_as_dict(r) for r in gold_reqs]
        result.tm_unmatched = [_tm_req_as_dict(r) for r in tm_reqs]
        result.time_comparison = time.perf_counter() - t_start
        return result

    gold_texts = [r.descripcion for r in gold_reqs]
    tm_texts = [r.descripcion for r in tm_reqs]

    gold_vecs = _get_embeddings(gold_texts)
    tm_vecs = _get_embeddings(tm_texts)
    sim_matrix = _cosine_sim(gold_vecs, tm_vecs)  # (n_gold, n_tm)

    gold_matched_indices: set[int] = set()
    tm_matched_indices: set[int] = set()

    for i, gr in enumerate(gold_reqs):
        best_j = int(np.argmax(sim_matrix[i]))
        best_score = float(sim_matrix[i, best_j])
        if best_score >= SEMANTIC_THRESHOLD:
            gold_matched_indices.add(i)
            tm_matched_indices.add(best_j)
            result.matched_pairs.append({
                "gold_id": gr.id,
                "gold_desc": gr.descripcion[:120],
                "gold_cat": gr.categoria,
                "gold_tipo": gr.tipo,
                "tm_desc": tm_reqs[best_j].descripcion[:120],
                "tm_cat": tm_reqs[best_j].categoria,
                "tm_tipo": tm_reqs[best_j].tipo,
                "score": round(best_score, 3),
            })

    result.gold_unmatched = [
        _req_as_dict(gold_reqs[i]) for i in range(len(gold_reqs)) if i not in gold_matched_indices
    ]
    result.tm_unmatched = [
        _tm_req_as_dict(tm_reqs[j]) for j in range(len(tm_reqs)) if j not in tm_matched_indices
    ]

    n_gold = len(gold_reqs)
    n_tm = len(tm_reqs)
    tp = len(gold_matched_indices)

    result.recall = tp / n_gold if n_gold else 0.0
    result.precision = len(tm_matched_indices) / n_tm if n_tm else 0.0
    denom = result.recall + result.precision
    result.f1 = 2 * result.recall * result.precision / denom if denom else 0.0

    result.time_comparison = time.perf_counter() - t_start
    return result
