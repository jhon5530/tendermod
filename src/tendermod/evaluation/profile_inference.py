import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langchain_openai import ChatOpenAI

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.prompts import (
    PROFILE_EVALUATION_SYSTEM,
    PROFILE_EVALUATION_USER,
    PROFILE_EXTRACTION_SYSTEM,
    PROFILE_EXTRACTION_USER,
)
from tendermod.evaluation.schemas import (
    ProfileComplianceResult,
    ProfileRequirement,
    ProfileRequirementList,
    TeamProfileComplianceList,
)
from tendermod.evaluation.team_inference import _load_all_team_data
from tendermod.ingestion.chapter_extractor import extract_page_range, get_chapter_ranges

logger = logging.getLogger(__name__)

_MAX_BLOCK_CHARS = 20_000   # igual que general_requirements_inference


def _get_pdf_path() -> str:
    data_dir = Path(CHROMA_PERSIST_DIR).parent
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def _build_profile_blocks(pdf_path: str, chapters: list[dict]) -> list[dict]:
    """Fusiona capítulos en bloques de ≤_MAX_BLOCK_CHARS chars sin cortar a mitad de capítulo."""
    blocks: list[dict] = []
    current_text = ""
    current_title = ""

    for ch in chapters:
        header = (
            f"\n\n[=== SECCIÓN: {ch['title'][:80]} | "
            f"Páginas {ch['start_page'] + 1}–{ch['end_page']} ===]\n"
        )
        ch_text = header + extract_page_range(pdf_path, ch["start_page"], ch["end_page"])
        if len(current_text) + len(ch_text) > _MAX_BLOCK_CHARS and current_text:
            blocks.append({"text": current_text, "title": current_title})
            current_text = ch_text
            current_title = ch["title"]
        else:
            if not current_title:
                current_title = ch["title"]
            current_text += ch_text

    if current_text:
        blocks.append({"text": current_text, "title": current_title})

    return blocks


def _extract_profiles_from_block(
    llm: ChatOpenAI,
    block_text: str,
    block_title: str,
) -> ProfileRequirementList:
    """Extrae perfiles de un bloque de texto usando structured output."""
    # Normalizar saltos de línea simples (fragmentación de celdas de tabla PDF).
    # "Líder de\nProyecto" → "Líder de Proyecto". Párrafos dobles se preservan.
    normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', block_text)
    result: ProfileRequirementList = llm.invoke([
        {"role": "system", "content": PROFILE_EXTRACTION_SYSTEM},
        {"role": "user",   "content": PROFILE_EXTRACTION_USER.format(text=normalized)},
    ])
    if result.perfiles:
        logger.info(
            "[profile_inference] Bloque '%s': %d perfil(es) — %s",
            block_title[:40], len(result.perfiles), [p.rol for p in result.perfiles],
        )
    return result


def get_team_profiles_from_pdf() -> ProfileRequirementList:
    """
    Extrae los perfiles de equipo de trabajo requeridos del pliego.

    Divide el documento en bloques de ≤20K chars y procesa cada uno en paralelo,
    garantizando cobertura total del documento independientemente de dónde esté
    la sección de equipo.
    """
    pdf_path = _get_pdf_path()
    chapters = get_chapter_ranges(pdf_path, use_llm=False)
    blocks = _build_profile_blocks(pdf_path, chapters)

    logger.info(
        "[profile_inference] %d capítulos → %d bloques para extracción de perfiles",
        len(chapters), len(blocks),
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        ProfileRequirementList
    )

    all_profiles: list[ProfileRequirement] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_to_idx = {
            pool.submit(_extract_profiles_from_block, llm, block["text"], block["title"]): i
            for i, block in enumerate(blocks)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                partial = future.result()
                all_profiles.extend(partial.perfiles)
            except Exception as exc:
                logger.warning(
                    "[profile_inference] Bloque %d/%d falló: %s", idx + 1, len(blocks), exc
                )

    # Deduplicar por nombre de rol (mantener primera ocurrencia)
    seen: set[str] = set()
    unique: list[ProfileRequirement] = []
    for p in all_profiles:
        key = p.rol.upper().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Filtrar perfiles sin ningún requisito específico: probablemente alucinaciones.
    # Un perfil válido debe tener al menos formación, certificación o experiencia en años.
    filtered: list[ProfileRequirement] = []
    for p in unique:
        has_requirements = (
            bool(p.formacion_requerida)
            or bool(p.certificaciones_requeridas)
            or p.anios_experiencia_min is not None
        )
        if has_requirements:
            filtered.append(p)
        else:
            logger.warning(
                "[profile_inference] Perfil '%s' descartado: sin formación, certificaciones "
                "ni experiencia especificadas — probable alucinación del LLM.",
                p.rol,
            )

    logger.info(
        "[profile_inference] Extracción completada: %d perfiles válidos (de %d únicos) — %s",
        len(filtered), len(unique), [p.rol for p in filtered],
    )
    return ProfileRequirementList(perfiles=filtered)


def evaluate_team_profiles(profiles: ProfileRequirementList) -> TeamProfileComplianceList:
    """
    Evalúa el cumplimiento de cada perfil requerido contra el equipo de la empresa.
    Una llamada LLM por perfil (Full-Context).
    """
    team_data = _load_all_team_data()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        ProfileComplianceResult
    )

    results: list[ProfileComplianceResult] = []
    for i, profile in enumerate(profiles.perfiles):
        logger.info(
            "[profile_inference] Evaluando perfil %d/%d: %s",
            i + 1, len(profiles.perfiles), profile.rol,
        )
        try:
            result: ProfileComplianceResult = llm.invoke([
                {"role": "system", "content": PROFILE_EVALUATION_SYSTEM},
                {"role": "user",   "content": PROFILE_EVALUATION_USER.format(
                    profile=profile.model_dump_json(indent=2),
                    team_data=team_data,
                )},
            ])
            results.append(result)
            logger.info(
                "[profile_inference] Perfil '%s': cumple=%s, candidatos=%s",
                profile.rol, result.cumple, result.personas_que_cumplen,
            )
        except Exception as exc:
            logger.error("[profile_inference] Error evaluando perfil '%s': %s", profile.rol, exc)
            results.append(ProfileComplianceResult(
                rol=profile.rol,
                cantidad_requerida=profile.cantidad,
                cumple=False,
            ))

    cumple_equipo = all(r.cumple for r in results)
    logger.info(
        "[profile_inference] Evaluación completa: %d/%d perfiles cumplen — cumple_equipo=%s",
        sum(1 for r in results if r.cumple), len(results), cumple_equipo,
    )
    return TeamProfileComplianceList(perfiles_evaluados=results, cumple_equipo=cumple_equipo)
