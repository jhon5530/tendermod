from tendermod.evaluation.indicators_inference import get_general_info, get_indicators
from tendermod.evaluation.llm_client import run_llm_indicators_comparation
from tendermod.ingestion.db_loader import get_specific_gold_indicator


def indicators_comparation():

    query = "Cuales los indicadores financieros como: Rentabilidades, capacidades, endeudamiento, indices"
    
    k = 2
    tender_indicators = get_indicators(user_input=query, k=k)
    #print(f"\n Tender indicators: {tender_indicators}")
    tender_indicators_json = from_indicator_schema_to_simple_json(tender_indicators)
    #print(f"\n Tender indicators Json: {tender_indicators_json}")
    identified_indicators = check_indicators_name(tender_indicators)

    
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
    print (tender_indicators_json)

    print("\n\nGold Indicators")
    print (gold_indicators["output"])
    general_info = get_general_info("Cual es el presupuesto del proceso?", k=2)
    comparation_response = run_llm_indicators_comparation(str(gold_indicators["output"]), str(tender_indicators_json), general_info)
    print(f"\n\nEl resultado de la comparacion es:\n {comparation_response}")

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
