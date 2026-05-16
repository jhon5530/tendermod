import logging
import os
import sqlite3

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
from tendermod.evaluation.schemas import TeamQuery

logger = logging.getLogger(__name__)


def build_and_execute_query(intent: TeamQuery) -> tuple[list[dict], str]:
    """
    Construye SQL determinístico a partir de la intención parseada y lo ejecuta.
    Retorna (filas, sql_generado) para facilitar el logging y diagnóstico.
    """
    conditions: list[str] = []
    params: list[str] = []

    if intent.filter_cert:
        conditions.append("c.Certificacion LIKE ?")
        params.append(f"%{intent.filter_cert}%")

    if intent.filter_categoria:
        conditions.append("c.Categoria LIKE ?")
        params.append(f"%{intent.filter_categoria}%")

    if intent.filter_persona:
        conditions.append("c.Persona LIKE ?")
        params.append(f"%{intent.filter_persona}%")

    if intent.filter_vencimiento == "vigente":
        conditions.append("LOWER(c.Vencimiento) = 'vigente'")
    elif intent.filter_vencimiento == "vencida":
        conditions.append("LOWER(c.Vencimiento) = 'vencida'")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    if intent.action == "count":
        if intent.group_by == "persona":
            sql = (
                f"SELECT c.Persona, COUNT(*) as total "
                f"FROM certificaciones c {where} "
                f"GROUP BY c.Persona ORDER BY total DESC"
            )
        elif intent.group_by == "certificacion":
            sql = (
                f"SELECT c.Certificacion, COUNT(*) as total "
                f"FROM certificaciones c {where} "
                f"GROUP BY c.Certificacion ORDER BY total DESC"
            )
        elif intent.group_by == "categoria":
            sql = (
                f"SELECT c.Categoria, COUNT(*) as total "
                f"FROM certificaciones c {where} "
                f"GROUP BY c.Categoria ORDER BY total DESC"
            )
        else:
            sql = f"SELECT COUNT(*) as total FROM certificaciones c {where}"

    elif intent.action == "detail":
        sql = (
            f"SELECT c.Persona, c.Cargo, c.Categoria, c.Certificacion, "
            f"c.Descripcion, c.Fecha_Expedicion, c.Fecha_Expiracion, c.Vencimiento "
            f"FROM certificaciones c {where} ORDER BY c.Persona, c.Certificacion"
        )

    else:  # list (default)
        sql = (
            f"SELECT c.Persona, c.Cargo, c.Certificacion, c.Categoria, c.Vencimiento "
            f"FROM certificaciones c {where} ORDER BY c.Persona, c.Certificacion"
        )

    db_path = os.path.join(REDNEET_DB_PERSIST_DIR, "redneet_database.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        logger.info("[team_query_builder] SQL: %s | params: %s | rows: %d", sql, params, len(rows))
        return rows, sql
    finally:
        conn.close()
