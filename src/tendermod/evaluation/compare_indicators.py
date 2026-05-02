import re
from typing import Optional

from tendermod.evaluation.indicators_inference import get_general_info, get_indicators
from tendermod.evaluation.llm_client import run_llm_indicators_comparation
from tendermod.evaluation.schemas import IndicatorComplianceResult
from tendermod.ingestion.db_loader import get_specific_gold_indicator


def extract_compliance_bool(text: str) -> Optional[bool]:
    if re.search(r'\bNo cumple\b', text, re.IGNORECASE):
        return False
    if re.search(r'\bCumple\b', text, re.IGNORECASE):
        return True
    return None


def _compute_cumple(valor_empresa, condicion: str, umbral) -> 'Optional[bool]':
    if valor_empresa is None or umbral is None:
        return None
    try:
        v, u = float(valor_empresa), float(umbral)
        return {"Mayor o igual a": v >= u, "Menor o igual a": v <= u,
                "Mayor que": v > u, "Menor que": v < u}.get(condicion)
    except (ValueError, TypeError):
        return None


def _normalize_indicator_name(name: str) -> str:
    """Normaliza nombre de indicador: minúsculas, sin tildes, sin espacios extra."""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', str(name))
    ascii_str = nfkd.encode('ascii', 'ignore').decode('ascii')
    return ' '.join(ascii_str.lower().split())


def _parse_budget_from_text(text: str) -> Optional[float]:
    """Extrae el valor numérico del presupuesto de un texto con formato colombiano."""
    if not text:
        return None
    m = re.search(r'\$\s*([\d.]+)', text)
    if not m:
        return None
    raw = m.group(1)
    if re.search(r'\d\.\d{3}', raw):
        raw = raw.replace('.', '')
    try:
        return float(raw)
    except ValueError:
        return None


def merge_indicators(tender_indicators_json: dict, gold_indicators_str: str,
                     presupuesto: float = None) -> list:
    """
    Empareja los indicadores del pliego con los valores reales de la empresa.
    Parsea el campo 'valor' del pliego para separar operador y umbral numérico.
    Retorna lista de dicts con: indicador, valor_empresa, condicion, umbral.
    """
    import json
    import re

    # Parsear el JSON de indicadores de la empresa
    try:
        if isinstance(gold_indicators_str, str):
            gold_data = json.loads(gold_indicators_str)
        else:
            gold_data = gold_indicators_str
        gold_list = gold_data.get("indicadores", [])
        gold_map = {item["nombre"]: item["valor"] for item in gold_list}
        # Mapa normalizado como fallback cuando el SQL agent devuelve nombres de la DB
        gold_map_norm = {_normalize_indicator_name(k): v for k, v in gold_map.items()}
    except Exception:
        gold_map = {}
        gold_map_norm = {}

    # Requisitos del pliego
    tender_list = tender_indicators_json.get("result", [])

    resultado = []
    for req in tender_list:
        nombre = req.get("nombre", "")
        valor_texto = str(req.get("valor", ""))

        # Intentar parsear operador y umbral del texto
        condicion = None
        umbral = None

        # Patrones en orden de especificidad (más específico primero).
        # mode: None=valor directo, "pct"=dividir/100, "pct_rel"=% del presupuesto
        _OP_A = r'(?:a[l]?|que)'  # "a", "al", "que"
        patrones = [
            # % relativo al presupuesto ("15 % del POE", "15% del presupuesto")
            (rf'[Mm]ayor o igual {_OP_A}\s+([\d.,]+)\s*%\s+del', "Mayor o igual a", "pct_rel"),
            (rf'[Mm]enor o igual {_OP_A}\s+([\d.,]+)\s*%\s+del', "Menor o igual a", "pct_rel"),
            # % absoluto ("65%", "0.65%")
            (rf'[Mm]enor o igual {_OP_A}\s+([\d.,]+)\s*%',       "Menor o igual a", "pct"),
            (rf'[Mm]ayor o igual {_OP_A}\s+([\d.,]+)\s*%',       "Mayor o igual a", "pct"),
            # Valores directos — variantes "a", "al", "que"
            (rf'[Mm]enor o igual {_OP_A}\s+([\d.,]+)',            "Menor o igual a", None),
            (rf'[Mm]ayor o igual {_OP_A}\s+([\d.,]+)',            "Mayor o igual a", None),
            (r'[Nn]o\s+[Mm]ayor\s+(?:de|a|que)\s+([\d.,]+)',     "Menor o igual a", None),
            (r'[Nn]o\s+[Mm]enor\s+(?:de|a|que)\s+([\d.,]+)',     "Mayor o igual a", None),
            (r'[Mm]ínimo\s+([\d.,]+)',                            "Mayor o igual a", None),
            (r'[Mm]inimo\s+([\d.,]+)',                            "Mayor o igual a", None),
            (r'[Mm]áximo\s+([\d.,]+)',                            "Menor o igual a", None),
            (r'[Mm]aximo\s+([\d.,]+)',                            "Menor o igual a", None),
            (r'>=\s*([\d.,]+)',                                   "Mayor o igual a", None),
            (r'<=\s*([\d.,]+)',                                   "Menor o igual a", None),
            (r'[Mm]enor que\s+([\d.,]+)',                         "Menor que",       None),
            (r'[Mm]ayor que\s+([\d.,]+)',                         "Mayor que",       None),
            (r'>\s*([\d.,]+)',                                    "Mayor que",       None),
            (r'<\s*([\d.,]+)',                                    "Menor que",       None),
        ]
        for patron, op, mode in patrones:
            m = re.search(patron, valor_texto)
            if m:
                condicion = op
                raw = m.group(1)
                # Normalizar separadores de miles colombianos
                if ',' in raw:
                    raw = raw.replace('.', '').replace(',', '.')
                elif re.search(r'\d\.\d{3}', raw) and raw.count('.') >= 2:
                    raw = raw.replace('.', '')
                try:
                    val = float(raw)
                    if mode == "pct_rel":
                        umbral = (presupuesto * val / 100) if presupuesto else None
                    elif mode == "pct":
                        umbral = val / 100.0
                    else:
                        umbral = val
                except ValueError:
                    umbral = None
                break

        # Fallback: pasar el texto completo para que el LLM de comparación lo interprete
        if condicion is None:
            condicion = valor_texto  # e.g. "Mayor o igual a 1.13" sin parsear
            umbral = valor_texto

        valor_empresa = gold_map.get(nombre)
        if valor_empresa is None:
            valor_empresa = gold_map_norm.get(_normalize_indicator_name(nombre))

        resultado.append({
            "indicador": nombre,
            "valor_empresa": valor_empresa,
            "condicion": condicion,
            "umbral": umbral,
        })

    return resultado


def indicators_comparation() -> Optional[IndicatorComplianceResult]:

    """Query para obtener los indicadores del RAG"""
    query = "Cuales los indicadores financieros como: Rentabilidades, capacidades, endeudamiento, indices"
    
    k = 2
    tender_indicators = get_indicators(user_input=query, k=k)
    if tender_indicators is None:
        return IndicatorComplianceResult(
            cumple=None,
            detalle="Error al extraer indicadores del PDF",
            indicadores_evaluados=[],
            indicadores_faltantes=[]
        )
    #print(f"\n Tender indicators: {tender_indicators}")
    tender_indicators_json = from_indicator_schema_to_simple_json(tender_indicators)
    #print(f"\n Tender indicators Json: {tender_indicators_json}")
    identified_indicators = check_indicators_name(tender_indicators)

    
    """Query para obtener los indicadores de la base de datos"""
    query = (
        "Devuelve un objeto JSON válido con los siguientes indicadores: "
        f"\n{identified_indicators}\n\n"
        "REGLAS:\n"
        "1) Responde EXCLUSIVAMENTE con JSON válido (un único objeto).\n"
        "2) Prohibido: explicaciones, markdown, texto adicional, encabezados, bloques ```json.\n"
        "3) Si un indicador no existe, no lo inventes: inclúyelo en 'faltantes'.\n"
        "4) 'valor' debe ser número cuando sea posible.\n\n"
        "FORMATO (exacto):\n"
        '{"indicadores":[{"nombre":"...","valor":0.0}]}'
    )
    print(f"Query: \n {query}")

    gold_indicators = get_specific_gold_indicator(query)

    print("\n\nindicators_json")
    print(tender_indicators_json)

    print("\n\nGold Indicators")
    print(gold_indicators["output"])

    # Emparejar indicadores antes de pasar al LLM
    indicadores_emparejados = merge_indicators(tender_indicators_json, gold_indicators["output"])
    print("\n\nIndicadores emparejados:")
    print(indicadores_emparejados)

    general_info = get_general_info("Cual es el presupuesto del proceso?", k=2)
    comparation_response = run_llm_indicators_comparation(str(indicadores_emparejados), general_info)
    print(f"\n\nEl resultado de la comparacion es:\n {comparation_response}")

    cumple = extract_compliance_bool(comparation_response)
    return IndicatorComplianceResult(
        cumple=cumple,
        detalle=comparation_response,
        indicadores_evaluados=[i.indicador for i in tender_indicators.answer],
        indicadores_faltantes=[]
    )

    #return tender_indicators


def check_indicators_name(indicators):

    indicators_in_str = ""
    for indicator in indicators.answer:
        indicators_in_str = indicators_in_str + str(indicator.indicador) + "\n"
    return indicators_in_str


def from_indicator_schema_to_simple_json(tender_indicators):
    answer = [
    {"nombre": item.indicador, "valor": item.valor}
        for item in tender_indicators.answer
    ]
    payload = {"result": answer}
    return payload








"""EJEMPLOS PARA NO OLVIDAR"""

u2ser_input = f"""
        Busca información específica sobre:
        - índice de liquidez
        - endeudamiento
        - cobertura de intereses
        - capital de trabajo

        Responde SOLO con base en el texto.
        """
