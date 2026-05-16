import json
import logging

from langchain_openai import ChatOpenAI

from tendermod.data_sources.redneet_db.team_query_builder import build_and_execute_query
from tendermod.evaluation.prompts import TEAM_ANSWER_SYSTEM, TEAM_ANSWER_USER
from tendermod.evaluation.team_intent import parse_team_intent

logger = logging.getLogger(__name__)


def ask_team(question: str) -> str:
    """
    Pipeline determinístico de 3 pasos para consultas sobre el equipo:
    1. LLM parsea la intención → TeamQuery (structured output, sin alucinaciones SQL)
    2. QueryBuilder Python genera SQL parametrizado → ejecuta en SQLite
    3. LLM redacta la respuesta en lenguaje natural a partir de datos reales
    """
    # Paso 1: parsear intención
    intent = parse_team_intent(question)

    # Paso 2: ejecutar query determinístico
    rows, sql = build_and_execute_query(intent)
    logger.info("[team_inference] Pregunta=%r | SQL=%s | filas=%d", question, sql, len(rows))

    # Paso 3: redactar respuesta
    results_text = json.dumps(rows, ensure_ascii=False, indent=2) if rows else "[]"
    llm = ChatOpenAI(temperature=0.2, model_name="gpt-4o-mini")
    messages = [
        {"role": "system", "content": TEAM_ANSWER_SYSTEM},
        {"role": "user", "content": TEAM_ANSWER_USER.format(
            question=question,
            results=results_text,
        )},
    ]
    response = llm.invoke(messages)
    answer = response.content.strip()
    logger.info("[team_inference] Respuesta: %s", answer[:200])
    return answer
