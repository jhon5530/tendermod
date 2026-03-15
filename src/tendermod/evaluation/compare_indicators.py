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


def merge_indicators(tender_indicators_json: dict, gold_indicators_str: str) -> list:
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
    except Exception:
        gold_map = {}

    # Requisitos del pliego
    tender_list = tender_indicators_json.get("result", [])

    resultado = []
    for req in tender_list:
        nombre = req.get("nombre", "")
        valor_texto = str(req.get("valor", ""))

        # Intentar parsear operador y umbral del texto
        condicion = None
        umbral = None

        # Patrones: "Mayor o igual a 1.30", "Menor o igual a 0.78", "Mayor que X", etc.
        patrones = [
            (r'[Mm]enor o igual a\s+([\d.,]+)', "Menor o igual a"),
            (r'[Mm]ayor o igual a\s+([\d.,]+)', "Mayor o igual a"),
            (r'[Mm]enor que\s+([\d.,]+)', "Menor que"),
            (r'[Mm]ayor que\s+([\d.,]+)', "Mayor que"),
        ]
        for patron, op in patrones:
            m = re.search(patron, valor_texto)
            if m:
                condicion = op
                raw = m.group(1)
                # Solo eliminar puntos si son separadores de miles colombianos
                # (patrón: dígito.exactamente3dígitos, con múltiples grupos)
                # Ejemplos: "1.000.000" → miles | "1.30" → decimal, NO tocar
                if ',' in raw:
                    # Formato colombiano: puntos = miles, coma = decimal
                    raw = raw.replace('.', '').replace(',', '.')
                elif re.search(r'\d\.\d{3}', raw) and raw.count('.') >= 2:
                    # Múltiples puntos de miles: "1.000.000"
                    raw = raw.replace('.', '')
                # else: punto único es decimal → dejar como está ("1.30", "0.78")
                try:
                    umbral = float(raw)
                except ValueError:
                    umbral = None
                break

        # Si no se pudo parsear, dejar el texto original como umbral
        if condicion is None:
            condicion = "ver descripción"
            umbral = valor_texto  # texto completo para que el LLM lo interprete

        resultado.append({
            "indicador": nombre,
            "valor_empresa": gold_map.get(nombre),
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
