"""
Agente conversacional Redneet — accede a contratos, equipo e indicadores.

Patrón Full-Context: carga los tres datasets como texto estructurado y deja
que gpt-4.1 razone sobre el conjunto completo. Sin ChromaDB, sin SQL agent,
sin intent parser — el LLM ve todos los datos y aplica la lógica correcta
para cualquier tipo de consulta (búsqueda, evaluación de cumplimiento, estadísticas).

Costo estimado por pregunta: ~$0.02-0.04 (contexto ~25K tokens con historial).
"""
import logging
import os
import sqlite3

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
from tendermod.evaluation.team_inference import _load_all_team_data

logger = logging.getLogger(__name__)

_REDNEET_USER_TEMPLATE = """\
=== CONTRATOS EJECUTADOS ({n_rups} registros) ===
{experience}

=== INDICADORES FINANCIEROS ACTUALES ===
{indicators}

=== EQUIPO DE TRABAJO ===
{team}

---
{question}"""

# Columnas fijas de la tabla experiencia (no son UNSPSC)
_EXPERIENCE_FIXED_COLS = {
    "NUMERO RUP", "CLIENTE", "OBJETO", "VALOR", "SMMLV",
    "FECHA FINALIZACION", "DIAS DE EJECUCION", "DESCRIPCION GENERAL",
}


def _load_experience_as_text() -> tuple[str, int]:
    """
    Carga tabla `experiencia` de SQLite como texto compacto.
    Incluye solo códigos UNSPSC activos (valor == 1), descarta las 173 columnas binarias.
    Retorna (texto, n_contratos).
    """
    db_path = os.path.join(REDNEET_DB_PERSIST_DIR, "redneet_database.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        col_info = conn.execute("PRAGMA table_info(experiencia)").fetchall()
        unspsc_cols = [
            row[1] for row in col_info
            if row[1] not in _EXPERIENCE_FIXED_COLS and row[1].strip().isdigit()
        ]
        rows = conn.execute("SELECT * FROM experiencia ORDER BY [NUMERO RUP]").fetchall()
    finally:
        conn.close()

    lines: list[str] = []
    for row in rows:
        rup = row["NUMERO RUP"]
        cliente = (row["CLIENTE"] or "").strip()
        objeto = (row["OBJETO"] or "").strip()[:200]  # truncar para controlar tokens
        descripcion = (row["DESCRIPCION GENERAL"] or "").strip()[:80]
        try:
            valor = float(row["VALOR"] or 0)
            smmlv = float(row["SMMLV"] or 0)
        except (TypeError, ValueError):
            valor, smmlv = 0.0, 0.0
        fecha = (row["FECHA FINALIZACION"] or "").strip()[:10]  # solo fecha, sin hora
        try:
            dias = int(float(row["DIAS DE EJECUCION"] or 0))
        except (TypeError, ValueError):
            dias = 0

        active_codes = [col for col in unspsc_cols if row[col] == 1]
        codes_str = ", ".join(active_codes) if active_codes else "N/A"

        lines.append(
            f"RUP-{rup} | {cliente} | ${valor:,.0f} COP ({smmlv:.1f} SMMLV) | Fin: {fecha} | {dias}d\n"
            f"  Objeto: {objeto}\n"
            f"  Descripción: {descripcion}\n"
            f"  Códigos UNSPSC: {codes_str}"
        )

    return "\n\n".join(lines), len(rows)


def _load_indicators_as_text() -> str:
    """Carga tabla `indicadores` como texto compacto."""
    db_path = os.path.join(REDNEET_DB_PERSIST_DIR, "redneet_database.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT INDICADOR, VALOR FROM indicadores").fetchall()
    finally:
        conn.close()

    if not rows:
        return "(Sin datos de indicadores cargados)"
    return "\n".join(f"  {r['INDICADOR']}: {r['VALOR']}" for r in rows)


def ask_redneet(question: str, chat_history: list[dict] | None = None) -> str:
    """
    Agente conversacional unificado Redneet.

    Carga experiencia + indicadores + equipo como contexto completo y deja
    que gpt-4.1 razone sobre los tres datasets para responder cualquier pregunta.

    Args:
        question: Pregunta en lenguaje natural (búsqueda, evaluación de cumplimiento, estadísticas).
        chat_history: Lista de mensajes previos [{role, content}, ...] — máximo 10.

    Returns:
        Respuesta en lenguaje natural en español, con datos concretos.
    """
    from tendermod.evaluation.prompts import REDNEET_AGENT_SYSTEM

    history = chat_history or []

    try:
        experience_text, n_rups = _load_experience_as_text()
    except Exception as exc:
        logger.error("[redneet_inference] Error cargando experiencia: %s", exc)
        experience_text, n_rups = "(Error cargando datos de experiencia)", 0

    try:
        indicators_text = _load_indicators_as_text()
    except Exception as exc:
        logger.error("[redneet_inference] Error cargando indicadores: %s", exc)
        indicators_text = "(Error cargando indicadores)"

    try:
        team_text = _load_all_team_data()
    except Exception as exc:
        logger.error("[redneet_inference] Error cargando equipo: %s", exc)
        team_text = "(Error cargando datos del equipo)"

    user_content = _REDNEET_USER_TEMPLATE.format(
        n_rups=n_rups,
        experience=experience_text,
        indicators=indicators_text,
        team=team_text,
        question=question,
    )

    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)
    messages: list = [SystemMessage(content=REDNEET_AGENT_SYSTEM)]
    for m in history[-10:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append(HumanMessage(content=user_content))

    response = llm.invoke(messages)
    answer = response.content.strip()
    logger.info(
        "[redneet_inference] question=%r | answer_preview=%s",
        question[:80], answer[:150],
    )
    return answer
