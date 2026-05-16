import json
import logging

from langchain_openai import ChatOpenAI

from tendermod.evaluation.prompts import TEAM_INTENT_SYSTEM, TEAM_INTENT_USER
from tendermod.evaluation.schemas import TeamQuery

logger = logging.getLogger(__name__)


def parse_team_intent(question: str) -> TeamQuery:
    """
    Llama al LLM para parsear la intención de la pregunta del usuario en un
    TeamQuery estructurado. Usa structured output para garantizar JSON válido.
    """
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")
    structured_llm = llm.with_structured_output(TeamQuery)

    messages = [
        {"role": "system", "content": TEAM_INTENT_SYSTEM},
        {"role": "user", "content": TEAM_INTENT_USER.format(question=question)},
    ]

    intent: TeamQuery = structured_llm.invoke(messages)
    logger.info("[team_intent] Pregunta: %r → %s", question, intent.model_dump())
    return intent
