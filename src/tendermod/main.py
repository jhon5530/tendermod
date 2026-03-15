from tendermod.data_sources.redneet_db.xls_loader import load_db
from tendermod.evaluation.compare_experience import check_compliance_experience, experience_comparation
from tendermod.evaluation.compare_indicators import indicators_comparation
from tendermod.ingestion.ingestion_experience_flow import ingest_experience_data
from tendermod.ingestion.ingestion_flow import ingest_documents

from dotenv import load_dotenv


def main():
    load_dotenv()

    # ══════════════════════════════════════════════════════════════
    # MODO INGESTA — Ejecutar solo cuando se cargue un nuevo PDF,
    # Excel o experiencia. Comentar después de ingestar.
    # ══════════════════════════════════════════════════════════════
    ingest_documents()                                                    # PDF licitacion -> ChromaDB
    #load_db(tab_name="indicadores", file_name="rib.xlsx")                 # Excel -> SQLite indicadores
    #load_db(tab_name="experiencia", file_name="experiencia_rup.xlsx")     # Excel -> SQLite experiencia
    #ingest_experience_data()                                              # SQLite experiencia -> ChromaDB

    # ══════════════════════════════════════════════════════════════
    # MODO EVALUACION — Flujo principal
    # ══════════════════════════════════════════════════════════════
    print("\n=== EVALUACION DE CUMPLIMIENTO ===\n")

    # Track 1: Indicadores financieros
    print("--- TRACK 1: INDICADORES FINANCIEROS ---")
    result_ind = indicators_comparation()

    if result_ind is not None:
        estado_ind = "CUMPLE" if result_ind.cumple else ("NO CUMPLE" if result_ind.cumple is False else "INDETERMINADO")
        print(f"\n  Resultado: {estado_ind}")
    else:
        estado_ind = "ERROR"
        print("  ERROR: No se pudo evaluar los indicadores financieros")

    # Track 2: Experiencia
    print("\n--- TRACK 2: EXPERIENCIA ---")
    tender_exp = experience_comparation()

    result_exp = None
    if tender_exp is None:
        estado_exp = "ERROR"
        print("  ERROR: No se pudieron extraer requisitos de experiencia del PDF")
    else:
        result_exp = check_compliance_experience(tender_exp)

        print(f"\n  Codigos requeridos: {result_exp.codigos_requeridos}")
        print(f"  Valor minimo requerido: {result_exp.valor_requerido_cop} COP")
        print(f"  Objeto requerido: {result_exp.objeto_requerido}")
        print()

        for rup in result_exp.rups_evaluados:
            cod    = "OK"    if rup.cumple_codigos else "FALLA"
            obj    = "OK"    if rup.cumple_objeto is True else ("FALLA" if rup.cumple_objeto is False else "N/A")
            res    = "CUMPLE" if rup.cumple_total else "NO CUMPLE"
            cliente = rup.cliente or "DESCONOCIDO"
            valor_str = f"${rup.valor_cop:,.0f} COP" if rup.valor_cop is not None else "N/A"
            print(f"  {cliente} - RUP {rup.numero_rup} -> Codigos: {cod} | Valor: {valor_str} | Objeto: {obj} -> {res}")

        if result_exp.total_valor_cop is not None:
            print(f"\n  Suma total experiencia (RUPs calificados): ${result_exp.total_valor_cop:,.0f} COP")
        print(f"  RUPs que cumplen: {result_exp.rups_cumplen}")
        estado_exp = "CUMPLE" if result_exp.cumple else "NO CUMPLE"
        print(f"  Resultado: {estado_exp}")

    # Veredicto final
    # cumple_ind = result_ind.cumple is not False if result_ind else False
    # cumple_exp = result_exp.cumple if result_exp else False
    # cumple_final = cumple_ind and cumple_exp

    # print(f"\n=== VEREDICTO FINAL: {'CUMPLE' if cumple_final else 'NO CUMPLE'} ===\n")


if __name__ == "__main__":
    main()
