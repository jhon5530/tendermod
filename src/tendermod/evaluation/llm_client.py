import json
import logging
import re

from openai import OpenAI
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

from tendermod.evaluation.prompts import basic_comparation_system_prompt, basic_comparation_user_prompt
from tendermod.evaluation.schemas import ExperienceResponse, MultipleIndicatorResponse, GeneralRequirementList

load_dotenv()
def run_llm_indices(system_message, user_message, max_tokens=2500, temperature=0.3, top_p=0.95):
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p
        )
        # Extract and print the generated text from the response
    print("----- ------ ------ LLM Response ----- ------ ------ ")
    print(response.choices[0].message.content)
    print("----- ------ ------ LLM Response end  ----- ------ ------ ")
    response = response.choices[0].message.content.strip()

    return response


def run_llm_indicators_comparation(indicadores_emparejados: str, general_info: str, max_tokens=1000, temperature=0.0, top_p=1):
    client = OpenAI()
    user_prompt = basic_comparation_user_prompt
    user_prompt = user_prompt.replace("{general_info}", general_info)
    user_prompt = user_prompt.replace("{indicadores_emparejados}", indicadores_emparejados)

    print(f"System Prompt:\n{basic_comparation_system_prompt}")
    print(f"User Prompt:\n{user_prompt}")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": basic_comparation_system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p
    )
    return response.choices[0].message.content


def run_llm_quick_experience(text: str) -> ExperienceResponse:
    from tendermod.evaluation.prompts import QUICK_EXPERIENCE_SYSTEM_PROMPT, QUICK_EXPERIENCE_USER_PROMPT
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(ExperienceResponse)
    messages = [
        SystemMessage(content=QUICK_EXPERIENCE_SYSTEM_PROMPT),
        HumanMessage(content=QUICK_EXPERIENCE_USER_PROMPT(text))
    ]
    return structured_llm.invoke(messages)


def run_llm_quick_indicators(text: str) -> MultipleIndicatorResponse:
    from tendermod.evaluation.prompts import QUICK_INDICATORS_SYSTEM_PROMPT, QUICK_INDICATORS_USER_PROMPT
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(MultipleIndicatorResponse)
    messages = [
        SystemMessage(content=QUICK_INDICATORS_SYSTEM_PROMPT),
        HumanMessage(content=QUICK_INDICATORS_USER_PROMPT(text))
    ]
    return structured_llm.invoke(messages)


def run_llm_general_requirements(context: str, query: str) -> GeneralRequirementList:
    from tendermod.evaluation.prompts import (
        qna_system_message_general_requirements,
        qna_user_message_general_requirements,
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(GeneralRequirementList)
    user_content = (
        qna_user_message_general_requirements
        .replace("{context}", context)
        .replace("{question}", query)
    )
    messages = [
        SystemMessage(content=qna_system_message_general_requirements),
        HumanMessage(content=user_content),
    ]
    return structured_llm.invoke(messages)


def run_llm_requirements_from_chapter(chapter_text: str, chapter_title: str) -> GeneralRequirementList:
    """Extrae requerimientos del texto completo de un capítulo del pliego."""
    from tendermod.evaluation.prompts import (
        qna_system_message_general_requirements,
        qna_user_message_general_requirements,
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(GeneralRequirementList)
    user_content = (
        qna_user_message_general_requirements
        .replace("{context}", chapter_text)
        .replace("{question}", f"requerimientos en el capítulo: {chapter_title}")
    )
    messages = [
        SystemMessage(content=qna_system_message_general_requirements),
        HumanMessage(content=user_content),
    ]
    return structured_llm.invoke(messages)


def run_llm_experience_from_chapters(chapters_text: str):
    """Extrae ExperienceResponse del texto completo de capítulos de experiencia."""
    from tendermod.evaluation.prompts import qna_system_message_experience
    from tendermod.evaluation.schemas import ExperienceResponse
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(ExperienceResponse)
    user_content = (
        "###Context\n"
        + chapters_text
        + "\n\n###Question\n"
        "Extrae TODOS los requisitos de experiencia del proponente: "
        "códigos UNSPSC, valor mínimo en SMMLV o COP por segmento, objeto requerido, "
        "cantidad de contratos y cualquier segmento o sub-requisito independiente de experiencia."
    )
    messages = [
        SystemMessage(content=qna_system_message_experience),
        HumanMessage(content=user_content),
    ]
    return structured_llm.invoke(messages)


def run_llm_chapter_detection(pages_text: str, total_pages: int) -> list[dict]:
    """
    Detecta capítulos y sus rangos de página desde las primeras páginas del PDF.
    Retorna lista de dicts con title, start_page, end_page (1-based).
    """
    from tendermod.evaluation.prompts import CHAPTER_DETECTION_SYSTEM, CHAPTER_DETECTION_USER

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    user_content = (
        CHAPTER_DETECTION_USER
        .replace("{pages_text}", pages_text)
        .replace("{total_pages}", str(total_pages))
    )
    messages = [
        SystemMessage(content=CHAPTER_DETECTION_SYSTEM),
        HumanMessage(content=user_content),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()

    # Limpiar markdown fence si el LLM lo incluye
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("[run_llm_chapter_detection] JSON inválido: %s — raw: %s", exc, raw[:300])
        return []





