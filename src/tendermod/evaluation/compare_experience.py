


import re
import sqlite3
from typing import Optional, Union, List
from tendermod.evaluation.experience_inference import get_experience
from tendermod.evaluation.schemas import (
    ExperienceResponse,
    ExperienceComplianceResult,
    RupExperienceResult,
    SubRequirementComplianceResult,
)
from tendermod.ingestion.experience_db_loader import DB_PATH
from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import read_vectorstore
from tendermod.evaluation.indicators_inference import get_general_info

import datetime as _dt
import logging as _logging

_logger = _logging.getLogger(__name__)

# Patrones que indican que `objeto` contiene meta-texto genérico en lugar del objeto real.
# El LLM a veces extrae la REGLA de relación ("debe estar relacionado con el objeto del proceso")
# en lugar del OBJETO REAL ("servicios de redes y telecomunicaciones").
_GENERIC_OBJETO_PATTERNS = [
    r"objeto del proceso",
    r"proceso de selecci[oó]n",
    r"objeto del contrato que se va a celebrar",
    r"relacionado con el objeto",
    r"misma actividad.*proceso",
    r"mismo objeto del proceso",
    r"objeto de selecci[oó]n",
    r"deber[aá]\s+guardar\s+relaci[oó]n",
    r"en\s+la\s+misma\s+l[ií]nea.*negocio.*proceso",
    r"verificar\s+la\s+experiencia\s+debe",
]


def _is_generic_objeto(texto: str) -> bool:
    """Retorna True si `objeto` es meta-texto genérico (no el objeto real del proceso)."""
    if not texto or texto.strip() in ("None", ""):
        return False
    t = texto.lower()
    return any(re.search(p, t) for p in _GENERIC_OBJETO_PATTERNS)


def _extract_objeto_from_general_info(general_info_text: str) -> Optional[str]:
    """
    Extrae el objeto real del proceso desde el texto libre de general_info_text.
    Busca patrones como 'Objeto: ...', 'Objeto del contrato: ...', etc.
    Retorna None si no encuentra ningún patrón reconocible.
    """
    if not general_info_text:
        return None
    patterns = [
        r"[Oo]bjeto\s+del\s+(?:contrato|proceso|presente\s+proceso|proceso\s+de\s+contrataci[oó]n)\s*[:：]\s*(.+?)(?:\n|$|Número|Presupuesto|N[uú]mero)",
        r"[Oo]bjeto\s+a\s+contratar\s*[:：]\s*(.+?)(?:\n|$)",
        r"[Oo]bjeto\s*[:：]\s*(.+?)(?:\n|$|Número|Presupuesto)",
        r"El\s+objeto\s+(?:del|de\s+este|de\s+la\s+presente)\s+(?:contrato|proceso|licitaci[oó]n)\s+es\s*[:：]?\s*(.+?)(?:\.|$|\n)",
    ]
    for pattern in patterns:
        m = re.search(pattern, general_info_text, re.IGNORECASE)
        if m:
            obj = m.group(1).strip().rstrip('.')
            # Limpiar formato Markdown que el LLM puede incluir en general_info_text
            obj = re.sub(r'\*+', '', obj).strip()
            if len(obj) > 10:  # descartar matches triviales
                return obj
    return None

# Actualizar este dict cada diciembre con el valor oficial del año siguiente (decreto del gobierno).
_SMMLV_BY_YEAR: dict[int, float] = {
    2024: 1_300_000,
    2025: 1_423_500,
    2026: 1_423_500,
}

def _get_smmlv() -> float:
    """Retorna el SMMLV vigente para el año actual. Usa el último año conocido como fallback."""
    year = _dt.date.today().year
    if year in _SMMLV_BY_YEAR:
        return _SMMLV_BY_YEAR[year]
    # Fallback al año más reciente disponible
    return _SMMLV_BY_YEAR[max(_SMMLV_BY_YEAR)]


def _parse_presupuesto(texto: str) -> Optional[float]:
    """Extrae el valor numérico en COP del texto libre que devuelve get_general_info."""
    if not texto:
        return None
    nums = re.findall(r'\$?\s*([\d.]+)', texto)
    for raw in nums:
        cleaned = raw.replace('.', '')
        try:
            val = float(cleaned)
            if val > 1_000_000:
                return val
        except ValueError:
            continue
    return None


def experience_comparation() -> Optional[ExperienceResponse]:
    """Query para obtener los requisitos de experiencia del RAG.
    La query usa múltiples sinónimos para adaptarse a distintos formatos de pliego.
    """
    query = (
        "experiencia del proponente oferente requisitos habilitantes "
        "experiencia específica general contratos ejecutados acreditados "
        "códigos UNSPSC valor acreditar SMMLV COP cantidad contratos objeto"
    )
    k = 10
    tender_experience, experience_context = get_experience(user_input=query, k=k)
    if tender_experience is None:
        print("ERROR: No se pudieron extraer requisitos de experiencia del PDF")
        return None, ""
    return tender_experience, experience_context




def parse_valor(valor_str: str, presupuesto_cop: Optional[float] = None) -> Optional[float]:
    """
    Parsea el string de valor mínimo requerido extraído del pliego por el LLM.
    Soporta formatos: '500 SMMLV', '$100.000.000', '100,000,000' (anglosajón),
    y '100% del presupuesto' (porcentaje del presupuesto oficial).
    Retorna None si no se puede parsear (valor no especificado o formato desconocido).
    """
    if not valor_str or valor_str.strip() in ("None", ""):
        return None
    if re.search(r'cannot find|no se encontr|not found|no especif', valor_str, re.IGNORECASE):
        return None

    # Caso porcentaje del presupuesto: "100% del presupuesto", "50%", etc.
    match_pct = re.search(r'(\d+[\.,]?\d*)\s*%', valor_str)
    if match_pct:
        if presupuesto_cop is not None:
            pct = float(match_pct.group(1).replace(',', '.'))
            return (pct / 100) * presupuesto_cop
        else:
            print("[parse_valor] Porcentaje detectado pero presupuesto no disponible → None")
            return None

    # Caso SMMLV
    if re.search(r'smmlv', valor_str, re.IGNORECASE):
        nums = re.findall(r'[\d.,]+', valor_str)
        if not nums:
            return None
        raw = nums[0]
        # Limpiar separadores colombianos: puntos como miles, coma como decimal
        if ',' in raw and '.' in raw:
            raw = raw.replace('.', '').replace(',', '.')
        elif '.' in raw and re.search(r'\.\d{3}$', raw):
            raw = raw.replace('.', '')
        elif ',' in raw:
            raw = raw.replace(',', '.')
        try:
            return float(raw) * _get_smmlv()
        except ValueError:
            return None

    # Caso anglosajón: comas como separadores de miles (ej: 100,000,000)
    anglosajón = re.match(r'^\$?\s*(\d{1,3}(?:,\d{3})+)$', valor_str.strip())
    if anglosajón:
        raw = anglosajón.group(1).replace(',', '')
        try:
            return float(raw)
        except ValueError:
            return None

    # Caso colombiano: puntos como miles (ej: $100.000.000 o 100.000.000)
    nums = re.findall(r'[\d.,]+', valor_str)
    if nums:
        raw = nums[0]
        if '.' in raw and re.search(r'\.\d{3}', raw):
            raw = raw.replace('.', '')
        elif ',' in raw:
            raw = raw.replace(',', '.')
        try:
            return float(raw)
        except ValueError:
            return None

    return None


def parse_cantidad_contratos(cantidad_str: Optional[str]) -> Optional[int]:
    """
    Parsea el string de cantidad de contratos extraído del pliego por el LLM.
    Soporta formatos: '3', 'mínimo 3', 'tres (3)', 'three', etc.
    Retorna None si no se puede parsear (sin límite de contratos).
    """
    if not cantidad_str or cantidad_str.strip() in ("None", ""):
        return None
    if re.search(r'cannot find|no se encontr|not found|no especif|no aplica', cantidad_str, re.IGNORECASE):
        return None

    # Palabras en español/inglés para números del 1 al 10
    palabras = {
        "uno": 1, "una": 1, "one": 1,
        "dos": 2, "two": 2,
        "tres": 3, "three": 3,
        "cuatro": 4, "four": 4,
        "cinco": 5, "five": 5,
        "seis": 6, "six": 6,
        "siete": 7, "seven": 7,
        "ocho": 8, "eight": 8,
        "nueve": 9, "nine": 9,
        "diez": 10, "ten": 10,
    }
    texto = cantidad_str.lower().strip()
    for palabra, valor in palabras.items():
        if re.search(rf'\b{palabra}\b', texto):
            return valor

    # Extraer el primer entero del string
    match = re.search(r'\d+', cantidad_str)
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None

    return None


def select_top_n_rups(
    rups: list,
    n: Optional[int],
    table: str = "experiencia",
) -> list:
    """
    Selecciona los top-N RUPs de mayor valor entre los candidatos.

    - Si n es None o n <= 0, retorna la lista completa sin modificar.
    - Si hay menos RUPs que n, retorna todos los disponibles.
    - RUPs con VALOR NULL quedan al final del orden (NULLS LAST).
    """
    if not rups:
        return []
    if n is None or n <= 0:
        return rups

    db_path = DB_PATH
    placeholders = ",".join("?" * len(rups))
    rups_str = [str(r) for r in rups]
    sql = (
        f'SELECT "NUMERO RUP" FROM {table} '
        f'WHERE "NUMERO RUP" IN ({placeholders}) '
        f'ORDER BY CAST("VALOR" AS REAL) DESC NULLS LAST '
        f'LIMIT ?'
    )

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, rups_str + [n])
        rows = cur.fetchall()

    out = []
    for r in rows:
        v = r["NUMERO RUP"]
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            out.append(v)
    return out


def get_rup_details(rups: list, table: str = "experiencia") -> dict:
    """
    Devuelve un dict {numero_rup: {cliente, valor_cop}} para los RUPs indicados.
    """
    if not rups:
        return {}
    db_path = DB_PATH
    placeholders = ",".join("?" * len(rups))
    rups_str = [str(r) for r in rups]
    sql = f'SELECT "NUMERO RUP", "CLIENTE", "VALOR" FROM {table} WHERE "NUMERO RUP" IN ({placeholders})'

    result = {}
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, rups_str)
        for row in cur.fetchall():
            rup_key = row["NUMERO RUP"]
            try:
                rup_key = int(rup_key)
            except (TypeError, ValueError):
                pass
            result[rup_key] = {
                "cliente": row["CLIENTE"],
                "valor_cop": float(row["VALOR"]) if row["VALOR"] is not None else None,
            }
    return result


def check_value_compliance(
    rups: list,
    valor_minimo_cop: float,
    table: str = "experiencia",
) -> bool:
    """
    Verifica si la suma del VALOR de todos los RUPs calificados
    supera el valor mínimo requerido en COP.
    La experiencia se acredita con la suma de todos los contratos aplicables.
    """
    if not rups:
        return False

    db_path = DB_PATH
    placeholders = ",".join("?" * len(rups))
    rups_str = [str(r) for r in rups]
    sql = f'SELECT SUM("VALOR") as total FROM {table} WHERE "NUMERO RUP" IN ({placeholders})'

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(sql, rups_str)
        row = cur.fetchone()

    if row is None or row[0] is None:
        return False
    total = float(row[0])
    print(f"Suma total VALOR de RUPs {rups}: ${total:,.0f} COP (requerido: ${valor_minimo_cop:,.0f} COP)")
    return total >= valor_minimo_cop


def check_object_compliance(
    numero_rup: Union[int, str],
    objeto_requerido: str,
    similarity_threshold: float = 0.75,
) -> Optional[bool]:
    """
    Verifica si el objeto/descripción del RUP en ChromaDB es semánticamente
    compatible con el objeto requerido en el pliego.
    Retorna None si el objeto no está especificado o si el RUP no tiene
    registros en el vector store.
    """
    if not objeto_requerido or objeto_requerido.strip() in ("None", ""):
        return None
    if re.search(r'no specific purpose|cannot find|no se encontr|not found', objeto_requerido, re.IGNORECASE):
        return None

    try:
        vectorstore = read_vectorstore(embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR)
        results = vectorstore.similarity_search_with_relevance_scores(objeto_requerido, k=20)
    except Exception as e:
        print(f"Error al consultar ChromaDB de experiencia: {e}")
        return None

    rup_str = str(numero_rup)
    rup_results = [
        (doc, score) for doc, score in results
        if str(doc.metadata.get("numero_rup", "")) == rup_str
    ]

    if not rup_results:
        return None  # El RUP no tiene registros en el vector store

    return any(score >= similarity_threshold for _, score in rup_results)


def _get_all_rups() -> list:
    """Retorna todos los NUMERO RUP únicos presentes en SQLite."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT "NUMERO RUP" FROM experiencia ORDER BY "NUMERO RUP"')
        rows = cur.fetchall()
    out = []
    for (v,) in rows:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            out.append(v)
    return out


def _check_experience_semantic_only(
    tender_experience: ExperienceResponse,
    similarity_threshold: float = 0.75,
) -> ExperienceComplianceResult:
    """
    Evalúa experiencia usando SOLO similitud semántica cuando no hay códigos UNSPSC.
    Usa todos los RUPs de la BD como pool de candidatos y aplica el filtro de objeto
    como excluyente (objeto_exige_relevancia=SI implícito).
    """
    todos_rups = _get_all_rups()
    if not todos_rups:
        _logger.warning("[_check_experience_semantic_only] No hay RUPs en SQLite.")
        return ExperienceComplianceResult(codigos_requeridos=[], cumple=False)

    objeto = tender_experience.objeto
    cantidad_n = parse_cantidad_contratos(getattr(tender_experience, 'cantidad_contratos', None))

    _logger.info(
        "[_check_experience_semantic_only] Pool: %d RUPs totales | objeto: '%s'",
        len(todos_rups), (objeto or "")[:80],
    )

    # Filtro semántico excluyente sobre todos los RUPs
    rups_semanticos, scores_objeto, objetos_objeto = filter_rups_by_object(
        todos_rups, objeto, similarity_threshold
    )
    rups_excluidos = [r for r in todos_rups if r not in rups_semanticos]

    # Top-N por valor sobre los que pasaron el filtro semántico
    rups_top_n = select_top_n_rups(rups_semanticos, cantidad_n)

    # Valor: parsear sin presupuesto (en quick evaluate no hay ChromaDB de licitación)
    valor_cop = parse_valor(tender_experience.valor, presupuesto_cop=None)
    cumple_valor_global = (
        check_value_compliance(rups_top_n, valor_cop) if valor_cop is not None else None
    )

    rup_details = get_rup_details(rups_top_n)
    total_valor_cop = sum(
        d["valor_cop"] for d in rup_details.values() if d["valor_cop"] is not None
    ) or None

    rups_evaluados = []
    for rup in rups_top_n:
        detalles = rup_details.get(rup, {})
        score_obj = scores_objeto.get(rup)
        cumple_objeto = (score_obj >= similarity_threshold) if score_obj is not None else None
        cumple_total = (
            (cumple_valor_global if cumple_valor_global is not None else True)
            and (cumple_objeto if cumple_objeto is not None else True)
            and rup not in rups_excluidos
        )
        rups_evaluados.append(RupExperienceResult(
            numero_rup=rup,
            cliente=detalles.get("cliente"),
            valor_cop=detalles.get("valor_cop"),
            cumple_codigos=True,
            cumple_valor=cumple_valor_global,
            cumple_objeto=cumple_objeto,
            score_objeto=score_obj,
            objeto_contrato=objetos_objeto.get(rup),
            cumple_total=cumple_total,
        ))

    # Top-10 excluidos para trazabilidad
    excluidos_con_score = [
        (r, scores_objeto.get(r)) for r in rups_excluidos
    ]
    excluidos_con_score.sort(key=lambda x: x[1] if x[1] is not None else -1.0, reverse=True)
    excluidos_detalles = get_rup_details([r for r, _ in excluidos_con_score[:10]])
    for rup, score_obj in excluidos_con_score[:10]:
        detalles = excluidos_detalles.get(rup, {})
        rups_evaluados.append(RupExperienceResult(
            numero_rup=rup,
            cliente=detalles.get("cliente"),
            valor_cop=detalles.get("valor_cop"),
            cumple_codigos=True,
            cumple_valor=None,
            cumple_objeto=False,
            score_objeto=score_obj,
            objeto_contrato=objetos_objeto.get(rup),
            cumple_total=False,
        ))

    rups_cumplen = [r.numero_rup for r in rups_evaluados if r.cumple_total]

    return ExperienceComplianceResult(
        codigos_requeridos=[],
        rups_candidatos_codigos=todos_rups,
        cantidad_contratos_requerida=cantidad_n,
        valor_requerido_cop=valor_cop,
        objeto_requerido=objeto,
        rups_evaluados=rups_evaluados,
        rups_cumplen=rups_cumplen,
        total_valor_cop=total_valor_cop,
        rups_excluidos_por_objeto=rups_excluidos,
        objeto_exige_relevancia="SI",
        similarity_threshold_usado=similarity_threshold,
        cumple=len(rups_cumplen) > 0,
        modo_evaluacion="GLOBAL",
    )


def _fetch_rup_data_for_llm(rups: list) -> dict:
    """Carga OBJETO y DESCRIPCION GENERAL de los RUPs del pool desde SQLite."""
    if not rups:
        return {}
    placeholders = ",".join("?" * len(rups))
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f'SELECT "NUMERO RUP", OBJETO, "DESCRIPCION GENERAL" '
            f'FROM experiencia WHERE "NUMERO RUP" IN ({placeholders})',
            [str(r) for r in rups],
        ).fetchall()
    return {
        row["NUMERO RUP"]: {
            "objeto": (row["OBJETO"] or "").strip(),
            "descripcion": (row["DESCRIPCION GENERAL"] or "").strip(),
        }
        for row in rows
    }


def _filter_rups_by_object_llm(
    rups: list,
    objeto_requerido: str,
) -> tuple:
    """
    Filtra el pool de RUPs usando un LLM como juez de relevancia de negocio.

    Reemplaza la búsqueda vectorial (ChromaDB) que no distingue suficientemente
    entre contratos con vocabulario similar pero tecnología diferente
    (ej: "rack de servidores" vs "sistema hiperconvergente").

    Threshold interno: score LLM >= 7/10 → cumple_objeto.
    scores_por_rup devuelve valores normalizados /10 (0.0-1.0) para
    compatibilidad con el display existente en RupExperienceResult.

    Retorna misma firma que filter_rups_by_object_chromadb.
    """
    import json as _json
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    from tendermod.evaluation.prompts import EXPERIENCE_OBJECT_RELEVANCE_SYSTEM

    LLM_THRESHOLD = 7  # score >= 7/10 → aprobado

    rup_data = _fetch_rup_data_for_llm(rups)
    if not rup_data:
        return rups, {}, {}

    lines = [f"Objeto del proceso a evaluar:\n{objeto_requerido}\n\nContratos del proponente:"]
    for rup in rups:
        data = rup_data.get(rup, {})
        obj = data.get("objeto", "")[:150]
        desc = data.get("descripcion", "")[:60]
        lines.append(f"RUP-{rup}: {obj} | Descripción: {desc}")
    user_content = "\n".join(lines)

    try:
        llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)
        response = llm.invoke([
            SystemMessage(content=EXPERIENCE_OBJECT_RELEVANCE_SYSTEM),
            HumanMessage(content=user_content),
        ])
        raw = response.content.strip()
        # Limpiar markdown fence si el LLM lo incluye
        if raw.startswith("```"):
            import re as _re
            raw = _re.sub(r"^```[a-z]*\n?", "", raw)
            raw = _re.sub(r"\n?```$", "", raw.strip())
        scores_raw: dict = _json.loads(raw)
    except Exception as exc:
        _logger.error("[filter_rups_by_object_llm] LLM/parse error: %s", exc)
        return None  # señal de fallback

    # Normalizar claves del JSON: el LLM puede devolver "RUP-5", "5", o 5
    scores_normalized: dict = {}
    for key, val in scores_raw.items():
        numeric_key = str(key).replace("RUP-", "").strip()
        scores_normalized[numeric_key] = val

    scores_por_rup: dict = {}
    objetos_por_rup: dict = {}
    rups_aprobados: list = []

    for rup in rups:
        raw_key = str(rup)
        llm_score_raw = scores_normalized.get(raw_key)
        try:
            llm_score = int(llm_score_raw) if llm_score_raw is not None else None
        except (TypeError, ValueError):
            llm_score = None

        if llm_score is None:
            # RUP no puntuado → conservar (política conservadora)
            _logger.warning("[filter_rups_by_object_llm] RUP %s no puntuado por LLM → conservado", rup)
            rups_aprobados.append(rup)
            scores_por_rup[rup] = None
        else:
            normalized = round(max(0.0, min(1.0, llm_score / 10)), 3)
            scores_por_rup[rup] = normalized
            objetos_por_rup[rup] = rup_data.get(rup, {}).get("objeto", "")
            if llm_score >= LLM_THRESHOLD:
                _logger.info("[filter_rups_by_object_llm] RUP %s: score=%d/10 (%.2f) ≥ %d → APROBADO", rup, llm_score, normalized, LLM_THRESHOLD)
                rups_aprobados.append(rup)
            else:
                _logger.info("[filter_rups_by_object_llm] RUP %s: score=%d/10 (%.2f) < %d → EXCLUIDO", rup, llm_score, normalized, LLM_THRESHOLD)

    _logger.info("[filter_rups_by_object_llm] objeto=%r | pool=%d | aprobados=%d | scores=%s",
                 objeto_requerido[:60], len(rups), len(rups_aprobados),
                 {k: v for k, v in scores_por_rup.items() if v is not None})
    return rups_aprobados, scores_por_rup, objetos_por_rup


def _filter_rups_by_object_chromadb(
    rups: list,
    objeto_requerido: str,
    similarity_threshold: float = 0.75,
) -> tuple:
    """Implementación original con ChromaDB — usada como fallback del LLM."""
    try:
        vectorstore = read_vectorstore(
            embed_docs(),
            path=CHROMA_EXPERIENCE_PERSIST_DIR,
            collection_name="rup",
        )
        try:
            total_docs = vectorstore._collection.count()
            k_dinamico = min(total_docs, max(200, len(rups) * 10)) if total_docs > 0 else max(20, len(rups) * 4)
        except Exception:
            k_dinamico = max(200, len(rups) * 10)
        results = vectorstore.similarity_search_with_relevance_scores(
            objeto_requerido, k=k_dinamico
        )
    except Exception as e:
        _logger.warning("[filter_rups_chromadb] No se pudo consultar ChromaDB: %s", e)
        return rups, {}, {}

    scores_por_rup: dict = {}
    objetos_por_rup: dict = {}
    for doc, score in results:
        raw_key = doc.metadata.get("numero_rup")
        if raw_key is None:
            continue
        try:
            rup_key = int(raw_key)
        except (TypeError, ValueError):
            rup_key = raw_key
        clamped = max(0.0, min(1.0, score))
        if clamped > scores_por_rup.get(rup_key, -1.0):
            scores_por_rup[rup_key] = clamped
            objetos_por_rup[rup_key] = doc.page_content

    if not scores_por_rup:
        _logger.warning("[filter_rups_chromadb] ChromaDB no devolvió resultados — se omite filtro de objeto")
        return rups, {}, {}

    rups_aprobados = []
    for rup in rups:
        score = scores_por_rup.get(rup)
        if score is None:
            rups_aprobados.append(rup)
        elif score >= similarity_threshold:
            rups_aprobados.append(rup)

    return rups_aprobados, scores_por_rup, objetos_por_rup


def filter_rups_by_object(
    rups: list,
    objeto_requerido: str,
    similarity_threshold: float = 0.75,
) -> tuple:
    """
    Filtra un pool de RUPs por relevancia semántica con el objeto requerido.

    Usa LLM (gpt-4.1-mini) como juez primario: evalúa 0-10 qué tan relacionado
    está cada contrato del pool con el objeto del pliego. Solo pasan score >= 7.
    Si el LLM falla, hace fallback a ChromaDB con similarity_threshold.

    Retorna:
        rups_aprobados (list): pool filtrado.
        scores_por_rup (dict): {numero_rup: float 0.0-1.0} — score LLM normalizado /10 o ChromaDB.
        objetos_por_rup (dict): {numero_rup: str} — texto del contrato para display.
    """
    if not objeto_requerido or objeto_requerido.strip() in ("None", ""):
        return rups, {}, {}
    if re.search(
        r'no specific purpose|cannot find|no se encontr|not found|no especif',
        objeto_requerido,
        re.IGNORECASE,
    ):
        return rups, {}, {}

    # Intento LLM primero
    result = _filter_rups_by_object_llm(rups, objeto_requerido)
    if result is not None:
        return result

    # Fallback ChromaDB
    _logger.warning("[filter_rups_by_object] LLM falló → usando ChromaDB (threshold=%.2f)", similarity_threshold)
    return _filter_rups_by_object_chromadb(rups, objeto_requerido, similarity_threshold)


def _check_global_experience(
    tender_experience: ExperienceResponse,
    similarity_threshold: float = 0.75,
) -> ExperienceComplianceResult:
    """Lógica de evaluación GLOBAL (flujo original, sin cambios)."""
    raw_codes = tender_experience.listado_codigos

    if not raw_codes:
        print("ADVERTENCIA: No se encontraron códigos UNSPSC en los requisitos del pliego")
        return ExperienceComplianceResult(
            codigos_requeridos=[],
            cumple=False
        )

    # Normalizar y validar los códigos extraídos por el LLM (reconstruye fragmentos
    # de tabla UNSPSC como ["43", "22", "17"] → ["432217"])
    codes = normalize_and_validate_codes(raw_codes)

    if not codes:
        print("ADVERTENCIA: Los códigos UNSPSC del pliego no pudieron normalizarse")
        return ExperienceComplianceResult(
            codigos_requeridos=raw_codes,
            cumple=False
        )

    # Determinar min_codigos desde la regla lógica del pliego
    # "ALL" exige presencia en todos los códigos listados
    # "AT_LEAST_ONE" (default) basta con que el contrato tenga alguno de los códigos
    regla = getattr(tender_experience, 'regla_codigos', 'AT_LEAST_ONE')
    min_codigos = len(codes) if regla == "ALL" else 1
    print(f"Regla de validación de códigos: {regla} → min_codigos={min_codigos}")

    # Validar códigos UNSPSC contra SQLite (los códigos ya vienen normalizados
    # porque check_compliance_experience llamó normalize_and_validate_codes arriba;
    # check_code_compliance llama normalize_and_validate_codes internamente pero
    # los códigos de 6 dígitos pasan sin modificación)
    rups_codigos = check_code_compliance(codes, min_codigos=min_codigos)
    print(f"RUPs que cumplen códigos: {rups_codigos} ({len(rups_codigos)} total)")

    if not rups_codigos:
        return ExperienceComplianceResult(
            codigos_requeridos=codes,  # códigos normalizados (6 dígitos)
            rups_candidatos_codigos=[],
            cumple=False
        )

    # --- Parámetros compartidos por FASE 1 y FASE 2 ---
    cantidad_n = parse_cantidad_contratos(getattr(tender_experience, 'cantidad_contratos', None))
    print(f"Cantidad de contratos requerida: {cantidad_n} (None = sin límite)")

    objeto_exige_relevancia = getattr(
        tender_experience, 'objeto_exige_relevancia', 'NO_ESPECIFICADO'
    )
    objeto = tender_experience.objeto
    print(f"objeto_exige_relevancia={objeto_exige_relevancia} | objeto='{objeto}'")

    scores_objeto: dict = {}
    objetos_objeto: dict = {}
    rups_excluidos: list = []

    objeto_definido = (
        objeto
        and objeto.strip() not in ("None", "")
        and not re.search(
            r'no specific purpose|cannot find|no se encontr|not found|no especif',
            objeto,
            re.IGNORECASE,
        )
    )

    # Promover a SI cuando el objeto es largo y específico pero no marcado explícitamente.
    # Un objeto descriptivo > 30 chars implica que la relevancia semántica importa.
    if objeto_exige_relevancia == "NO_ESPECIFICADO" and objeto_definido and len(objeto.strip()) > 30:
        objeto_exige_relevancia = "SI"
        _logger.info(
            "[_check_global_experience] objeto_exige_relevancia promovido a SI "
            "(objeto explícito de %d chars).", len(objeto.strip())
        )

    if objeto_exige_relevancia == "SI" and objeto_definido:
        # Filtro activo: aplicar semántico ANTES de top-N para no descartar
        # candidatos relevantes de menor valor.
        # FASE 2 primero → FASE 1 sobre los que pasan el filtro
        rups_semanticos, scores_objeto, objetos_objeto = filter_rups_by_object(rups_codigos, objeto, similarity_threshold)

        if not scores_objeto and rups_codigos:
            # ChromaDB vacío con filtro activo → no se puede verificar → excluir todos
            print(
                "ERROR [Fase 2]: Filtro de objeto ACTIVO pero ChromaDB de experiencia "
                "no devolvió datos. Todos los RUPs quedan excluidos. "
                "Ejecute ingest_experience_data() para poblar el vector store."
            )
            rups_excluidos = list(rups_codigos)
            rups_semanticos = []
        else:
            rups_excluidos = [r for r in rups_codigos if r not in rups_semanticos]

        if rups_excluidos:
            print(f"[Fase 2] RUPs excluidos por objeto: {rups_excluidos}")

        # FASE 1: top-N por valor sobre los que superaron el filtro semántico
        rups_top_n = select_top_n_rups(rups_semanticos, cantidad_n)
        print(f"[Fase 1] RUPs top-{cantidad_n} por valor (post-semántico): {rups_top_n}")
        rups_filtrados = rups_top_n
    else:
        # Filtro inactivo: FASE 1 primero (top-N por valor), luego scores para auditoría
        rups_top_n = select_top_n_rups(rups_codigos, cantidad_n)
        print(f"[Fase 1] RUPs top-{cantidad_n} por valor: {rups_top_n}")
        rups_filtrados = rups_top_n
        if objeto_definido:
            # Calcular scores de todas formas para auditoría (no excluye)
            _, scores_objeto, objetos_objeto = filter_rups_by_object(rups_top_n, objeto, similarity_threshold)
            print(
                f"[Fase 2] Filtro inactivo ({objeto_exige_relevancia}). "
                f"Scores calculados para auditoría: {scores_objeto}"
            )

    print(f"[Fase 2] RUPs filtrados para cálculo de valor: {rups_filtrados}")

    # --- VALOR: calcular sobre el pool ya filtrado por objeto ---
    presupuesto_str = get_general_info("Cual es el presupuesto oficial del proceso?", k=2)
    presupuesto_cop = _parse_presupuesto(presupuesto_str)
    print(f"Presupuesto oficial recuperado: {presupuesto_cop}")
    valor_cop = parse_valor(tender_experience.valor, presupuesto_cop=presupuesto_cop)
    print(f"Valor mínimo requerido (COP): {valor_cop}")

    cumple_valor_global = (
        check_value_compliance(rups_filtrados, valor_cop)
        if valor_cop is not None
        else None
    )

    # Obtener detalles (CLIENTE, VALOR) de todos los RUPs del top-N para display,
    # independientemente de si pasaron el filtro de objeto.
    rup_details = get_rup_details(rups_top_n)

    # Calcular total COP de los RUPs que pasaron el filtro de objeto
    total_valor_cop = sum(
        d["valor_cop"] for d in rup_details.values() if d["valor_cop"] is not None
    ) or None

    # --- Construir RupExperienceResult para todos los RUPs del top-N ---
    # Los excluidos por objeto se incluyen en la lista de resultados con
    # cumple_objeto=False para trazabilidad; no contribuyen al cumplimiento.
    rups_evaluados = []
    for rup in rups_top_n:
        detalles = rup_details.get(rup, {})
        score_obj = scores_objeto.get(rup)  # None si no hay datos o no se evaluó

        if objeto_exige_relevancia == "SI" and objeto_definido:
            if rup in rups_excluidos:
                cumple_objeto = False
            elif score_obj is None:
                cumple_objeto = None   # sin datos en ChromaDB → conservado
            else:
                cumple_objeto = score_obj >= similarity_threshold
        else:
            # Filtro no activo → no se puede afirmar True/False, solo anotar score
            cumple_objeto = None

        cumple_total = (
            (cumple_valor_global if cumple_valor_global is not None else True)
            and (cumple_objeto if cumple_objeto is not None else True)
            and rup not in rups_excluidos  # excluidos nunca cumplen
        )

        rups_evaluados.append(RupExperienceResult(
            numero_rup=rup,
            cliente=detalles.get("cliente"),
            valor_cop=detalles.get("valor_cop"),
            cumple_codigos=True,
            cumple_valor=cumple_valor_global,
            cumple_objeto=cumple_objeto,
            score_objeto=score_obj,
            objeto_contrato=objetos_objeto.get(rup),
            cumple_total=cumple_total
        ))

    rups_cumplen = [r.numero_rup for r in rups_evaluados if r.cumple_total]

    # --- Top-10 RUPs excluidos por objeto (solo cuando el filtro estuvo activo) ---
    # Muestra los mejores candidatos descartados para trazabilidad y revisión humana.
    if objeto_exige_relevancia == "SI" and objeto_definido and rups_excluidos:
        # Ordenar excluidos por score descendente (score None al final)
        excluidos_con_score = [
            (rup, scores_objeto.get(rup))
            for rup in rups_excluidos
        ]
        excluidos_con_score.sort(
            key=lambda x: x[1] if x[1] is not None else -1.0,
            reverse=True,
        )
        top10_excluidos = excluidos_con_score[:10]

        # Obtener detalles de DB para los excluidos que aún no están en rup_details
        excluidos_sin_detalle = [r for r, _ in top10_excluidos if r not in rup_details]
        if excluidos_sin_detalle:
            rup_details.update(get_rup_details(excluidos_sin_detalle))

        for rup, score_obj in top10_excluidos:
            detalles = rup_details.get(rup, {})
            rups_evaluados.append(RupExperienceResult(
                numero_rup=rup,
                cliente=detalles.get("cliente"),
                valor_cop=detalles.get("valor_cop"),
                cumple_codigos=True,
                cumple_valor=None,
                cumple_objeto=False,
                score_objeto=score_obj,
                objeto_contrato=objetos_objeto.get(rup),
                cumple_total=False,
            ))

    return ExperienceComplianceResult(
        codigos_requeridos=codes,
        rups_candidatos_codigos=rups_codigos,
        cantidad_contratos_requerida=cantidad_n,
        valor_requerido_cop=valor_cop,
        objeto_requerido=objeto if objeto_definido else None,
        rups_evaluados=rups_evaluados,
        rups_cumplen=rups_cumplen,
        total_valor_cop=total_valor_cop,
        rups_excluidos_por_objeto=rups_excluidos,
        objeto_exige_relevancia=objeto_exige_relevancia,
        similarity_threshold_usado=similarity_threshold,
        cumple=len(rups_cumplen) > 0,
        modo_evaluacion="GLOBAL",
    )


def check_multi_condition_experience(
    tender_experience: ExperienceResponse,
    rups_candidatos_codigos: list,
    similarity_threshold: float = 0.75,
) -> ExperienceComplianceResult:
    """
    Evaluacion MULTI_CONDICION: cada sub-requisito debe ser cubierto por un
    contrato RUP distinto.

    Algoritmo greedy:
    1. Para cada sub-requisito hace similarity_search en ChromaDB experiencia.
    2. Calcula el score maximo por RUP dentro del pool candidato (por codigos).
    3. Ordena sub-requisitos de menor a mayor numero de candidatos (mas restrictivos primero).
    4. Asigna el RUP disponible con mayor score a cada sub-req; lo retira del pool.

    El campo `cumple` global es True solo si TODOS los sub-requisitos cumplen.
    """
    sub_requisitos = tender_experience.sub_requisitos
    print(f"[MULTI_CONDICION] {len(sub_requisitos)} sub-requisitos | pool codigos: {len(rups_candidatos_codigos)} RUPs")

    # Abrir vectorstore una sola vez
    vectorstore = None
    try:
        vectorstore = read_vectorstore(
            embed_docs(),
            path=CHROMA_EXPERIENCE_PERSIST_DIR,
            collection_name="rup",
        )
        try:
            total_docs = vectorstore._collection.count()
            k_dinamico = min(total_docs, max(200, len(rups_candidatos_codigos) * 10)) if total_docs > 0 else max(20, len(rups_candidatos_codigos) * 4)
        except Exception:
            k_dinamico = max(200, len(rups_candidatos_codigos) * 10)
        print(f"[MULTI_CONDICION] ChromaDB abierto. k_dinamico={k_dinamico}")
    except Exception as e:
        print(f"[MULTI_CONDICION] ERROR al abrir ChromaDB: {e}")

    # Paso 1: calcular candidatos por sub-requisito (scores maximos por RUP)
    candidatos_por_subreq: List[List[tuple]] = []  # [(rup, score, objeto_contrato), ...]

    for i, sub in enumerate(sub_requisitos):
        scores_por_rup: dict = {}
        objetos_por_rup: dict = {}

        if vectorstore is not None:
            try:
                # Combinar objeto global + descripción del sub-req para mejorar
                # la similitud semántica cuando descripcion contiene lenguaje
                # de requisito legal (códigos UNSPSC, "Al menos N contratos...")
                # en lugar de descripción de actividad. Para sub-reqs con descripción
                # propia (FNA: "instalación de UPS en Datacenter"), objeto añade
                # contexto sin quitar especificidad.
                objeto_global = (tender_experience.objeto or "").strip()
                if objeto_global and objeto_global not in ("None", ""):
                    semantic_query = f"{objeto_global} {sub.descripcion}".strip()
                else:
                    semantic_query = sub.descripcion
                results = vectorstore.similarity_search_with_relevance_scores(
                    semantic_query, k=k_dinamico
                )
                for doc, score in results:
                    raw_key = doc.metadata.get("numero_rup")
                    if raw_key is None:
                        continue
                    try:
                        rup_key = int(raw_key)
                    except (TypeError, ValueError):
                        rup_key = raw_key
                    clamped = max(0.0, min(1.0, score))
                    if clamped > scores_por_rup.get(rup_key, -1.0):
                        scores_por_rup[rup_key] = clamped
                        objetos_por_rup[rup_key] = doc.page_content
            except Exception as e:
                print(f"[MULTI_CONDICION] ERROR similarity_search sub-req {i}: {e}")

        # Filtrar por pool de codigos y umbral
        candidatos = [
            (rup, scores_por_rup.get(rup, None), objetos_por_rup.get(rup))
            for rup in rups_candidatos_codigos
            if scores_por_rup.get(rup, 0.0) >= similarity_threshold
        ]
        print(f"[MULTI_CONDICION] Sub-req {i} '{sub.descripcion[:60]}': {len(candidatos)} candidatos")
        candidatos_por_subreq.append(candidatos)

    # Paso 2: greedy — ordenar por numero de candidatos ASC (mas restrictivos primero)
    indices_ordenados = sorted(range(len(sub_requisitos)), key=lambda i: len(candidatos_por_subreq[i]))

    resultados: List[SubRequirementComplianceResult] = [None] * len(sub_requisitos)  # type: ignore
    pool_disponible = set(rups_candidatos_codigos)

    for idx in indices_ordenados:
        sub = sub_requisitos[idx]
        candidatos = candidatos_por_subreq[idx]
        todos_candidatos_rup = [rup for rup, _, _ in candidatos]

        # Filtrar candidatos disponibles (no asignados aun)
        disponibles = [(rup, sc, obj) for rup, sc, obj in candidatos if rup in pool_disponible]
        disponibles.sort(key=lambda x: x[1] if x[1] is not None else -1.0, reverse=True)

        if disponibles:
            rup_elegido, score_elegido, objeto_elegido = disponibles[0]
            pool_disponible.discard(rup_elegido)
            cumple_sub = True
            print(f"[MULTI_CONDICION] Sub-req {idx}: RUP {rup_elegido} asignado (score={score_elegido:.3f})")
        else:
            rup_elegido, score_elegido, objeto_elegido = None, None, None
            cumple_sub = False
            print(f"[MULTI_CONDICION] Sub-req {idx}: sin candidatos disponibles -> NO CUMPLE")

        resultados[idx] = SubRequirementComplianceResult(
            indice=idx,
            descripcion=sub.descripcion,
            rups_candidatos=todos_candidatos_rup,
            rup_elegido=rup_elegido,
            score_objeto=score_elegido,
            objeto_contrato=objeto_elegido,
            cumple=cumple_sub,
        )

    sub_cumplidos = sum(1 for r in resultados if r.cumple)
    cumple_global = all(r.cumple for r in resultados)

    # Codigos requeridos globales (normalizados)
    raw_codes = tender_experience.listado_codigos
    codes = normalize_and_validate_codes(raw_codes) if raw_codes else raw_codes

    # Resolver valor requerido (igual que en _check_global_experience)
    presupuesto_str = get_general_info("Cual es el presupuesto oficial del proceso?", k=2)
    presupuesto_cop = _parse_presupuesto(presupuesto_str)
    print(f"[MULTI_CONDICION] Presupuesto oficial recuperado: {presupuesto_cop}")
    valor_cop = parse_valor(tender_experience.valor, presupuesto_cop=presupuesto_cop)
    print(f"[MULTI_CONDICION] Valor mínimo requerido (COP): {valor_cop}")

    return ExperienceComplianceResult(
        codigos_requeridos=codes,
        rups_candidatos_codigos=rups_candidatos_codigos,
        cantidad_contratos_requerida=None,
        valor_requerido_cop=valor_cop,
        objeto_requerido=tender_experience.objeto if tender_experience.objeto not in ("None", "", None) else None,
        rups_evaluados=[],
        rups_cumplen=[r.rup_elegido for r in resultados if r.cumple and r.rup_elegido is not None],
        total_valor_cop=None,
        rups_excluidos_por_objeto=[],
        objeto_exige_relevancia=tender_experience.objeto_exige_relevancia,
        similarity_threshold_usado=similarity_threshold,
        cumple=cumple_global,
        modo_evaluacion="MULTI_CONDICION",
        sub_requisitos_resultado=resultados,
        sub_requisitos_cumplidos=sub_cumplidos,
        sub_requisitos_totales=len(resultados),
    )


def check_compliance_experience(
    tender_experience: ExperienceResponse,
    similarity_threshold: float = 0.75,
) -> ExperienceComplianceResult:
    """
    Punto de entrada publico para la evaluacion de experiencia.

    Bifurca entre:
    - GLOBAL: flujo original (check_global_experience).
    - MULTI_CONDICION: nuevo flujo multi-sub-requisito (check_multi_condition_experience).
    """
    raw_codes = tender_experience.listado_codigos

    if not raw_codes:
        # Sin códigos UNSPSC: intentar evaluación por similitud semántica del objeto
        objeto = getattr(tender_experience, 'objeto', None)
        if (objeto
                and objeto.strip() not in ("None", "")
                and not _is_generic_objeto(objeto)
                and len(objeto.strip()) > 20):
            _logger.warning(
                "[check_compliance_experience] Sin códigos UNSPSC — fallback semántico "
                "con todos los RUPs de la BD. objeto='%s'",
                objeto[:80],
            )
            return _check_experience_semantic_only(tender_experience, similarity_threshold)
        print("ADVERTENCIA: No se encontraron códigos UNSPSC en los requisitos del pliego")
        return ExperienceComplianceResult(
            codigos_requeridos=[],
            cumple=False
        )

    codes = normalize_and_validate_codes(raw_codes)

    if not codes:
        print("ADVERTENCIA: Los códigos UNSPSC del pliego no pudieron normalizarse")
        return ExperienceComplianceResult(
            codigos_requeridos=raw_codes,
            cumple=False
        )

    regla = getattr(tender_experience, 'regla_codigos', 'AT_LEAST_ONE')
    min_codigos = len(codes) if regla == "ALL" else 1
    print(f"Regla de validación de códigos: {regla} → min_codigos={min_codigos}")

    rups_codigos = check_code_compliance(codes, min_codigos=min_codigos)
    print(f"RUPs que cumplen códigos: {rups_codigos} ({len(rups_codigos)} total)")

    if not rups_codigos:
        # Sin candidatos por código: intentar fallback semántico si hay objeto definido
        objeto = getattr(tender_experience, 'objeto', None)
        if (objeto
                and objeto.strip() not in ("None", "")
                and not _is_generic_objeto(objeto)
                and len(objeto.strip()) > 20):
            _logger.warning(
                "[check_compliance_experience] 0 RUPs con códigos UNSPSC '%s' — "
                "fallback semántico con todos los RUPs. objeto='%s'",
                codes, objeto[:80],
            )
            return _check_experience_semantic_only(tender_experience, similarity_threshold)
        return ExperienceComplianceResult(
            codigos_requeridos=codes,
            rups_candidatos_codigos=[],
            cumple=False
        )

    # Bifurcacion segun modo de evaluacion
    modo = getattr(tender_experience, 'modo_evaluacion', 'GLOBAL')
    sub_requisitos = getattr(tender_experience, 'sub_requisitos', [])

    if modo == "MULTI_CONDICION" and sub_requisitos:
        print(f"[check_compliance_experience] Modo MULTI_CONDICION detectado con {len(sub_requisitos)} sub-requisitos")
        return check_multi_condition_experience(tender_experience, rups_codigos, similarity_threshold)
    else:
        print("[check_compliance_experience] Modo GLOBAL")
        return _check_global_experience(tender_experience, similarity_threshold)


def check_code_compliance(
    code_list,
    table: str = "experiencia",
    rup_col: str = "NUMERO RUP",
    min_codigos: int = 1,
) -> list:
    """
    Devuelve los NUMERO RUP que cumplen los prefijos de código UNSPSC requeridos.

    - Normaliza y valida la lista de códigos con normalize_and_validate_codes
      antes de construir la consulta SQL. Esto resuelve el caso en que el LLM
      extrae fragmentos de tabla (ej. ["43", "22", "17"]) en lugar del código
      completo ("432217").
    - Para cada prefijo (columna), el valor debe ser distinto de 0 (o no nulo).
    - min_codigos controla cuántos códigos distintos debe tener el contrato:
        ALL  → min_codigos = len(codes)  (todos presentes simultáneamente)
        AT_LEAST_ONE → min_codigos = 1
    """
    db_path = DB_PATH

    # Normalizar y reconstruir fragmentos antes de consultar SQLite
    code_list_normalized = normalize_and_validate_codes(code_list)

    if not code_list_normalized:
        print("[check_code_compliance] ADVERTENCIA: no quedaron códigos válidos tras la normalización")
        return []

    print(f"[check_code_compliance] Códigos normalizados para consulta: {code_list_normalized}")

    score_expr = " + ".join([
        f'(CASE WHEN COALESCE("{c}", 0) > 0 THEN 1 ELSE 0 END)'
        for c in code_list_normalized
    ])

    sql = f'''
        SELECT DISTINCT "NUMERO RUP" AS numero_rup
        FROM experiencia
        WHERE ({score_expr}) >= ?
        ORDER BY numero_rup;
    '''

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, (min_codigos,))
        rows = cur.fetchall()

    # Intenta convertir a int (por si viene como texto)
    out = []
    for r in rows:
        v = r["numero_rup"]
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            out.append(v)  # si no se puede convertir, lo deja tal cual

    return out


def normalize_to_prefix6(code: Union[str, int]) -> str:
    """
    Normaliza un código UNSPSC a su prefijo de 6 dígitos.

    - Elimina letras, guiones y espacios antes de normalizar.
    - Lanza ValueError si tras la limpieza el resultado tiene menos de 6 dígitos,
      ya que no se puede formar un prefijo válido.
    """
    s = re.sub(r'[^0-9]', '', str(code).strip())
    if len(s) < 6:
        raise ValueError(
            f"Código UNSPSC demasiado corto para normalizar: '{code}' → '{s}' "
            f"({len(s)} dígitos). Se esperaban al menos 6."
        )
    return s[:6]


def normalize_and_validate_codes(raw_codes: list) -> list:
    """
    Limpia y valida la lista de códigos UNSPSC extraídos por el LLM antes de
    pasarlos a check_code_compliance.

    Problema que resuelve: cuando el pliego presenta los códigos en una tabla
    GRUPO/SEGMENTO/FAMILIA/CLASE, el LLM puede extraer los fragmentos como
    entradas separadas (ej. ["43", "22", "17"]) en lugar del código completo
    ("432217"). Esta función detecta y reconstruye esos fragmentos.

    Algoritmo:
    1. Limpia cada entrada: extrae solo dígitos, descarta letras/guiones.
    2. Clasifica cada entrada en:
       - válida: 6 u 8 dígitos exactos → se normaliza con normalize_to_prefix6.
       - fragmento: 1 a 4 dígitos → candidato a ser parte de un código tabulado.
       - ruido: 5 dígitos o más de 8 → se descarta con advertencia.
    3. Intenta reconstruir fragmentos consecutivos cuya concatenación sume
       exactamente 6 dígitos (patrón típico de tabla: 2+2+2).
    4. Descarta fragmentos irrecuperables con advertencia en el log.

    Retorna la lista de prefijos de 6 dígitos listos para consultar en SQLite.
    """
    valid: list = []
    fragments: list = []

    for raw in raw_codes:
        digits = re.sub(r'[^0-9]', '', str(raw).strip())

        if len(digits) in (6, 8):
            # Código completo: normalizar directamente
            valid.append(digits[:6])
            # Si había fragmentos acumulados sin resolver, intentar reconstruirlos
            # antes de pasar al siguiente código válido
            if fragments:
                reconstructed = _reconstruct_fragments(fragments)
                valid.extend(reconstructed)
                fragments = []

        elif 1 <= len(digits) <= 4:
            # Fragmento corto: acumular para intento de reconstrucción
            fragments.append(digits)

        elif len(digits) == 5:
            print(
                f"[normalize_and_validate_codes] ADVERTENCIA: código de 5 dígitos "
                f"descartado (no es UNSPSC válido): '{raw}'"
            )

        elif len(digits) > 8:
            # Puede ser un código de 8 dígitos con texto extra — tomar prefijo
            print(
                f"[normalize_and_validate_codes] ADVERTENCIA: entrada con más de 8 "
                f"dígitos, se toma prefijo de 6: '{raw}' → '{digits[:6]}'"
            )
            valid.append(digits[:6])

        else:
            # digits vacío (solo letras/símbolos)
            if str(raw).strip():
                print(
                    f"[normalize_and_validate_codes] ADVERTENCIA: entrada sin dígitos "
                    f"descartada: '{raw}'"
                )

    # Procesar fragmentos que quedaron al final de la lista
    if fragments:
        reconstructed = _reconstruct_fragments(fragments)
        valid.extend(reconstructed)

    # Deduplicar preservando orden (los duplicados legítimos ya fueron tratados
    # por el LLM; aquí eliminamos solo los producidos por la reconstrucción)
    seen = set()
    result = []
    for code in valid:
        if code not in seen:
            seen.add(code)
            result.append(code)
        # Nota: si el pliego repite un código intencionalmente, el LLM ya
        # debería haberlo incluido duplicado en raw_codes. Aquí deduplicamos
        # para evitar columnas SQL repetidas en check_code_compliance.

    return result


def _reconstruct_fragments(fragments: list) -> list:
    """
    Intenta reconstruir códigos UNSPSC de 6 dígitos a partir de una lista de
    fragmentos cortos (1-4 dígitos cada uno).

    Estrategia: concatenar fragmentos consecutivos hasta alcanzar exactamente
    6 dígitos. Si la acumulación supera los 6 dígitos sin haberlos alcanzado,
    el grupo se descarta como irrecuperable.

    Ejemplos:
        ["43", "22", "17"]  → ["432217"]   (2+2+2 = 6, patrón tabla UNSPSC)
        ["4", "3", "22", "17"] → ["432217"] (1+1+2+2 = 6)
        ["43", "22"]        → []            (4 dígitos, incompleto → descartado)
        ["43", "222", "17"] → []            (4+3 = 7 > 6, irrecuperable → descartado)
    """
    reconstructed = []
    buffer = ""

    for frag in fragments:
        if len(buffer) + len(frag) < 6:
            buffer += frag
        elif len(buffer) + len(frag) == 6:
            buffer += frag
            reconstructed.append(buffer)
            buffer = ""
        else:
            # La concatenación superaría 6 dígitos: el buffer actual es
            # irrecuperable; empezar nuevo intento desde este fragmento
            if buffer:
                print(
                    f"[_reconstruct_fragments] ADVERTENCIA: fragmentos irrecuperables "
                    f"descartados (no suman 6 dígitos): '{buffer}'"
                )
            buffer = frag  # reiniciar con el fragmento actual

    # Si quedó algo en el buffer que no alcanzó 6 dígitos
    if buffer:
        print(
            f"[_reconstruct_fragments] ADVERTENCIA: fragmentos finales irrecuperables "
            f"descartados (no suman 6 dígitos): '{buffer}'"
        )

    return reconstructed

