import logging
import os
import sqlite3

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
from tendermod.evaluation.schemas import TeamQuery

logger = logging.getLogger(__name__)


def _build_multi_filter_sql(
    intent: TeamQuery,
) -> tuple[str, list]:
    """
    Construye FROM + WHERE para la query.

    Cuando hay listas de múltiples términos (AND), genera self-JOINs:
      FROM certificaciones c1 JOIN certificaciones c2 ON c1.Persona = c2.Persona ...
    Cuando todos los filtros son simples (un solo campo), usa FROM certificaciones c.
    Retorna (from_clause, where_clause, params, alias_base).
    """
    cert_terms: list[str] = []
    cat_terms: list[str] = []

    # Normalizar: campos simples y listas se unifican en una lista por tipo
    if intent.filter_cert_list:
        cert_terms = list(intent.filter_cert_list)
    elif intent.filter_cert:
        cert_terms = [intent.filter_cert]

    if intent.filter_categoria_list:
        cat_terms = list(intent.filter_categoria_list)
    elif intent.filter_categoria:
        cat_terms = [intent.filter_categoria]

    # Calcular cuántos aliases necesitamos
    # Cada término necesita su propio alias para el self-JOIN
    total_terms = len(cert_terms) + len(cat_terms)

    if total_terms <= 1:
        # Caso simple: un solo filtro o ninguno, sin JOINs
        conditions: list[str] = []
        params: list = []

        if cert_terms:
            conditions.append("LOWER(c.Certificacion) LIKE LOWER(?)")
            params.append(f"%{cert_terms[0]}%")
        if cat_terms:
            conditions.append("LOWER(c.Categoria) LIKE LOWER(?)")
            params.append(f"%{cat_terms[0]}%")

        if intent.filter_persona:
            conditions.append("c.Persona LIKE ?")
            params.append(f"%{intent.filter_persona}%")

        if intent.filter_vencimiento == "vigente":
            conditions.append("LOWER(c.Vencimiento) = 'vigente'")
        elif intent.filter_vencimiento == "vencida":
            conditions.append("LOWER(c.Vencimiento) = 'vencida'")

        from_clause = "certificaciones c"
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return from_clause, where, params, "c"

    # Caso multi-término: necesitamos self-JOINs
    # Asignamos un alias por término: c1 para cert[0], c2 para cert[1], ..., cN para cat[0], ...
    aliases: list[str] = [f"c{i+1}" for i in range(total_terms)]
    cert_aliases = aliases[: len(cert_terms)]
    cat_aliases = aliases[len(cert_terms) :]

    # FROM con JOINs encadenados sobre c1
    base_alias = aliases[0]
    join_parts = [f"certificaciones {base_alias}"]
    for alias in aliases[1:]:
        join_parts.append(f"JOIN certificaciones {alias} ON {base_alias}.Persona = {alias}.Persona")
    from_clause = " ".join(join_parts)

    # WHERE conditions
    conditions = []
    params = []

    for alias, term in zip(cert_aliases, cert_terms):
        conditions.append(f"LOWER({alias}.Certificacion) LIKE LOWER(?)")
        params.append(f"%{term}%")

    for alias, term in zip(cat_aliases, cat_terms):
        conditions.append(f"LOWER({alias}.Categoria) LIKE LOWER(?)")
        params.append(f"%{term}%")

    if intent.filter_persona:
        conditions.append(f"{base_alias}.Persona LIKE ?")
        params.append(f"%{intent.filter_persona}%")

    if intent.filter_vencimiento == "vigente":
        conditions.append(f"LOWER({base_alias}.Vencimiento) = 'vigente'")
    elif intent.filter_vencimiento == "vencida":
        conditions.append(f"LOWER({base_alias}.Vencimiento) = 'vencida'")

    where = f"WHERE {' AND '.join(conditions)}"
    return from_clause, where, params, base_alias


def build_and_execute_query(intent: TeamQuery) -> tuple[list[dict], str]:
    """
    Construye SQL determinístico a partir de la intención parseada y lo ejecuta.
    Retorna (filas, sql_generado) para facilitar el logging y diagnóstico.
    """
    from_clause, where, params, alias = _build_multi_filter_sql(intent)
    multi = "JOIN" in from_clause  # usa self-JOINs → necesita DISTINCT

    if intent.action == "count":
        if intent.group_by == "persona":
            sql = (
                f"SELECT {alias}.Persona, COUNT(*) as total "
                f"FROM {from_clause} {where} "
                f"GROUP BY {alias}.Persona ORDER BY total DESC"
            )
        elif intent.group_by == "certificacion":
            sql = (
                f"SELECT {alias}.Certificacion, COUNT(*) as total "
                f"FROM {from_clause} {where} "
                f"GROUP BY {alias}.Certificacion ORDER BY total DESC"
            )
        elif intent.group_by == "categoria":
            sql = (
                f"SELECT {alias}.Categoria, COUNT(*) as total "
                f"FROM {from_clause} {where} "
                f"GROUP BY {alias}.Categoria ORDER BY total DESC"
            )
        else:
            distinct = "DISTINCT " if multi else ""
            sql = f"SELECT COUNT({distinct}{alias}.Persona) as total FROM {from_clause} {where}"

    elif intent.action == "detail":
        if multi:
            # Multi-cert: el JOIN ya garantiza que estas personas tienen TODAS las certs buscadas.
            # Mostrar solo Persona+Cargo para no confundir al LLM con datos de un solo alias.
            sql = (
                f"SELECT DISTINCT {alias}.Persona, {alias}.Cargo "
                f"FROM {from_clause} {where} ORDER BY {alias}.Persona"
            )
        else:
            sql = (
                f"SELECT {alias}.Persona, {alias}.Cargo, {alias}.Categoria, "
                f"{alias}.Certificacion, {alias}.Descripcion, {alias}.Fecha_Expedicion, "
                f"{alias}.Fecha_Expiracion, {alias}.Vencimiento "
                f"FROM {from_clause} {where} ORDER BY {alias}.Persona, {alias}.Certificacion"
            )

    else:  # list (default)
        if multi:
            # Multi-cert: mostrar solo personas distintas. El JOIN garantiza que cumplen TODOS los criterios.
            sql = (
                f"SELECT DISTINCT {alias}.Persona, {alias}.Cargo "
                f"FROM {from_clause} {where} ORDER BY {alias}.Persona"
            )
        else:
            sql = (
                f"SELECT {alias}.Persona, {alias}.Cargo, {alias}.Certificacion, "
                f"{alias}.Categoria, {alias}.Vencimiento "
                f"FROM {from_clause} {where} ORDER BY {alias}.Persona, {alias}.Certificacion"
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
