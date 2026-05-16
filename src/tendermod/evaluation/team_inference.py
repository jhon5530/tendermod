import json
import logging

from langchain_openai import ChatOpenAI

from tendermod.data_sources.redneet_db.team_query_builder import build_and_execute_query
from tendermod.evaluation.prompts import TEAM_ANSWER_SYSTEM, TEAM_ANSWER_USER
from tendermod.evaluation.team_intent import parse_team_intent

logger = logging.getLogger(__name__)


def ask_team(question: str, chat_history: list[dict] | None = None) -> str:
    """
    Pipeline determinístico de 3 pasos para consultas sobre el equipo:
    1. LLM parsea la intención → TeamQuery (structured output, sin alucinaciones SQL)
    2. QueryBuilder Python genera SQL parametrizado → ejecuta en SQLite
    3. LLM redacta la respuesta en lenguaje natural a partir de datos reales

    chat_history: lista de dicts [{"role": "user"|"assistant", "content": "..."}]
    con los últimos N mensajes de la conversación para contexto.
    """
    history = chat_history or []

    # Paso 1: augmentar la pregunta con contexto reciente para el intent parser
    question_for_intent = question
    if history:
        recent = history[-6:]  # últimos 3 turnos
        context_lines = "\n".join(
            f"- {'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content']}"
            for m in recent
        )
        question_for_intent = (
            f"Contexto reciente de la conversacion:\n{context_lines}\n\nPregunta actual: {question}"
        )
    intent = parse_team_intent(question_for_intent)

    # Paso 2: ejecutar query determinístico
    rows, sql = build_and_execute_query(intent)
    logger.info("[team_inference] Pregunta=%r | SQL=%s | filas=%d", question, sql, len(rows))

    # Paso 3: redactar respuesta incluyendo historial completo como contexto
    results_text = json.dumps(rows, ensure_ascii=False, indent=2) if rows else "[]"
    llm = ChatOpenAI(temperature=0.2, model_name="gpt-4o-mini")
    messages = [
        {"role": "system", "content": TEAM_ANSWER_SYSTEM},
        *history[-10:],  # últimos 10 mensajes (5 turnos) como contexto
        {"role": "user", "content": TEAM_ANSWER_USER.format(
            question=question,
            results=results_text,
        )},
    ]
    response = llm.invoke(messages)
    answer = response.content.strip()
    logger.info("[team_inference] Respuesta: %s", answer[:200])
    return answer
