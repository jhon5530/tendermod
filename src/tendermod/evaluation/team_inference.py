import logging
import os
import sqlite3
from collections import defaultdict

from langchain_openai import ChatOpenAI

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
from tendermod.evaluation.prompts import TEAM_CONTEXT_SYSTEM, TEAM_CONTEXT_USER

logger = logging.getLogger(__name__)


def _get_cert_columns(conn: sqlite3.Connection) -> tuple[str, str]:
    """Detecta dinámicamente los nombres de columnas del esquema actual."""
    info = conn.execute("PRAGMA table_info(certificaciones)").fetchall()
    cols = {row[1] for row in info}
    vigencia_col = next((c for c in ("Vigencia", "Vencimiento") if c in cols), None)
    join_col = "p.Persona" if "Persona" in cols else None
    return vigencia_col, join_col


def _load_all_team_data() -> str:
    """
    Carga TODAS las personas y certificaciones como texto estructurado.
    Incluye formación académica (Titulo_Profesional, Posgrado, Anios_Experiencia).
    Separa certificaciones vigentes / vencidas para facilitar evaluación de perfiles.
    """
    db_path = os.path.join(REDNEET_DB_PERSIST_DIR, "redneet_database.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        vigencia_col, _ = _get_cert_columns(conn)
        vig_select = f"c.{vigencia_col}" if vigencia_col else "NULL"

        # Detectar columnas de formación disponibles en personas
        p_cols = {row[1] for row in conn.execute("PRAGMA table_info(personas)").fetchall()}
        titulo_sel = "p.Titulo_Profesional" if "Titulo_Profesional" in p_cols else "NULL"
        tecnico_sel = "p.Titulo_Tecnico_Tecnologico" if "Titulo_Tecnico_Tecnologico" in p_cols else "NULL"
        posgrado_sel = "p.Posgrado" if "Posgrado" in p_cols else "NULL"
        anios_sel = "p.Anios_Experiencia" if "Anios_Experiencia" in p_cols else "NULL"

        rows = conn.execute(
            f"SELECT p.Persona, p.Cargo, "
            f"{titulo_sel} as Titulo_Profesional, "
            f"{tecnico_sel} as Titulo_Tecnico_Tecnologico, "
            f"{posgrado_sel} as Posgrado, "
            f"{anios_sel} as Anios_Experiencia, "
            f"c.Categoria, c.Certificacion, {vig_select} as Vigencia "
            "FROM personas p "
            "LEFT JOIN certificaciones c ON p.Persona = c.Persona "
            "ORDER BY p.Persona, c.Categoria, c.Certificacion"
        ).fetchall()
    finally:
        conn.close()

    personas: dict[str, dict] = defaultdict(lambda: {
        "cargo": "", "titulo": None, "tecnico": None,
        "posgrado": None, "anios": None,
        "vigentes": [], "vencidas": [],
    })

    for r in rows:
        p = personas[r["Persona"]]
        p["cargo"] = r["Cargo"] or ""
        if p["titulo"] is None:
            p["titulo"] = r["Titulo_Profesional"]
            p["tecnico"] = r["Titulo_Tecnico_Tecnologico"]
            p["posgrado"] = r["Posgrado"]
            p["anios"] = r["Anios_Experiencia"]
        if r["Certificacion"]:
            entry = f'{r["Certificacion"]} [{r["Categoria"]}]'
            vig = (r["Vigencia"] or "").strip()
            if vig.lower() == "vencida":
                p["vencidas"].append(entry)
            else:
                p["vigentes"].append(entry)

    total_vigentes = sum(len(d["vigentes"]) for d in personas.values())
    total_vencidas = sum(len(d["vencidas"]) for d in personas.values())
    lines: list[str] = [
        f"RESUMEN: {len(personas)} personas en el equipo, "
        f"{total_vigentes} certs vigentes, {total_vencidas} certs vencidas.",
        "",
    ]
    for nombre, data in sorted(personas.items()):
        anios_str = f" | AÑOS EXP: {data['anios']}" if data["anios"] is not None else ""
        lines.append(f"PERSONA: {nombre} | CARGO: {data['cargo']}{anios_str}")
        lines.append(f"  FORMACIÓN PROFESIONAL: {data['titulo'] or '(sin datos)'}")
        if data["tecnico"]:
            lines.append(f"  FORMACIÓN TÉCNICA: {data['tecnico']}")
        lines.append(f"  POSGRADO: {data['posgrado'] or '(sin datos)'}")
        if data["vigentes"]:
            lines.append(f"  CERTIFICACIONES VIGENTES ({len(data['vigentes'])}):")
            for cert in data["vigentes"]:
                lines.append(f"    - {cert}")
        else:
            lines.append("  CERTIFICACIONES VIGENTES: (ninguna)")
        if data["vencidas"]:
            lines.append(f"  CERTIFICACIONES VENCIDAS ({len(data['vencidas'])}):")
            for cert in data["vencidas"]:
                lines.append(f"    - {cert}")
        lines.append("")

    return "\n".join(lines)


def ask_team(question: str, chat_history: list[dict] | None = None) -> str:
    """
    Pipeline Full-Context: carga TODOS los datos del equipo (350 registros, ~17K tokens)
    y deja que el LLM razone directamente sobre el dataset completo.

    Elimina el intent parser + SQL builder — sin JOINs, sin esquemas de intención,
    sin ambigüedad en qué alias mostrar. El LLM ve todos los datos y aplica la lógica
    correcta para cualquier tipo de consulta (AND, OR, conteo, filtrado por vigencia, etc.).
    """
    history = chat_history or []

    try:
        team_data = _load_all_team_data()
    except Exception as exc:
        logger.error("[team_inference] Error cargando datos del equipo: %s", exc)
        return "No se pudieron cargar los datos del equipo. Verifique que el Excel esté cargado."

    llm = ChatOpenAI(temperature=0.1, model_name="gpt-4o-mini")
    messages = [
        {"role": "system", "content": TEAM_CONTEXT_SYSTEM},
        *history[-10:],
        {"role": "user", "content": TEAM_CONTEXT_USER.format(
            team_data=team_data,
            question=question,
        )},
    ]

    response = llm.invoke(messages)
    answer = response.content.strip()
    logger.info("[team_inference] Pregunta=%r | Respuesta: %s", question, answer[:200])
    return answer
