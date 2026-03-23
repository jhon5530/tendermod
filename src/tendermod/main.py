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
    #ingest_documents()                                                    # PDF licitacion -> ChromaDB
    #load_db(tab_name="indicadores", file_name="rib.xlsx")                 # Excel -> SQLite indicadores
    #load_db(tab_name="experiencia", file_name="experiencia_rup.xlsx")     # Excel -> SQLite experiencia
    #ingest_experience_data()                                              # SQLite experiencia -> ChromaDB

    # ══════════════════════════════════════════════════════════════
    # MODO EVALUACION — Flujo principal
    # ══════════════════════════════════════════════════════════════


    objeto_requerido = "Redes Wifi, codigos UNSPSC 432217, 432233, 432226, 811617 "
  
    quick_evaluate_debug(objeto_requerido)
    return 0

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
            cod     = "OK"     if rup.cumple_codigos else "FALLA"
            res     = "CUMPLE" if rup.cumple_total   else "NO CUMPLE"
            cliente = rup.cliente or "DESCONOCIDO"
            valor_str = f"${rup.valor_cop:,.0f} COP" if rup.valor_cop is not None else "N/A"

            # Score de similitud semantica con el objeto
            if rup.score_objeto is not None:
                obj_rel = (
                    f"SUPERA ({rup.score_objeto:.3f})"
                    if rup.score_objeto >= 0.75
                    else f"BAJO ({rup.score_objeto:.3f})"
                )
            else:
                obj_rel = "N/A"

            # Estado del objeto con razon de descarte cuando falla
            if rup.cumple_objeto is True:
                obj_str = f"OK  [{obj_rel}]"
            elif rup.cumple_objeto is False:
                if rup.score_objeto is None:
                    razon = "ChromaDB sin datos"
                else:
                    razon = f"Score {rup.score_objeto:.3f} < umbral 0.75"
                obj_str = f"FALLA [{razon}]"
            else:
                obj_str = f"N/A [{obj_rel}]"

            print(f"  {cliente} - RUP {rup.numero_rup} -> Codigos: {cod} | Valor: {valor_str} | Objeto: {obj_str} -> {res}")

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


def quick_evaluate_debug(objeto_requerido=""):
    """
    Debug CLI: evalúa relevancia semántica de objeto contra ChromaDB de experiencia.
    Útil para inspeccionar scores, diagnosticar filtros y verificar ingesta.

    Uso: descomentar llamada en main() o llamar directamente.
    """
    load_dotenv()
    print("\n=== DEBUG: RELEVANCIA SEMÁNTICA DE OBJETO ===\n")

    from tendermod.retrieval.embeddings import embed_docs
    from tendermod.retrieval.vectorstore import read_vectorstore
    from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
    from tendermod.evaluation.compare_experience import check_code_compliance, normalize_and_validate_codes

    # --- Parámetros de debug (modificar según necesidad) ---
   #objeto_requerido = """IMPLEMENTACION DE REDES DE DATOS, IMPLEMENTACION Y ADECUCACIONES DE CABLEADO ESTRUCTURADO DE LA RED, CONFIGURACION DE EQUIPOS DE RED, MIGRACION Y REPARACION DE SERVIDOR, LICENCIAS ANTIVIRUS Y FIREWALL, UPS, SOPORTE MESA DE AYUDA PERSONAL IN-HOUSE """
   # ← CAMBIAR
    codigos_unspsc   = []                             # ← opcional: ["432217", "432220"]
    umbral           = 0.75
    top_k            = 20
    # -------------------------------------------------------

    try:
        vs = read_vectorstore(embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR, collection_name="rup")
        total_docs = vs._collection.count()
        print(f"ChromaDB experiencia → {total_docs} documentos en colección 'rup'")
        if total_docs == 0:
            print("  ADVERTENCIA: ChromaDB vacío. Ejecute ingest_experience_data().")
            return
    except Exception as e:
        print(f"  ERROR conectando a ChromaDB: {e}")
        return

    # Muestra de documentos
    sample = vs._collection.get(limit=5, include=["documents", "metadatas"])
    print("\n--- Muestra ChromaDB (5 docs) ---")
    for _, meta in zip(sample["documents"], sample["metadatas"]):
        rup  = meta.get("numero_rup", "?")
        obj  = (meta.get("objeto") or "")[:70]
        desc = (meta.get("descripcion") or "")[:50]
        print(f"  RUP {rup:<5} | Objeto: {obj}")
        print(f"         | Desc:   {desc}")

    # Filtro por códigos UNSPSC (opcional)
    rups_codigos = None
    if codigos_unspsc:
        codes_norm = normalize_and_validate_codes(codigos_unspsc)
        rups_codigos = set(check_code_compliance(codes_norm))
        print(f"\nRUPs que cumplen códigos {codes_norm}: {sorted(rups_codigos)}")

    # Similarity search
    k_real = min(top_k, total_docs)
    print(f"\n--- Búsqueda semántica: '{objeto_requerido}' (top {k_real}, umbral {umbral}) ---")
    results = vs.similarity_search_with_relevance_scores(objeto_requerido, k=k_real)

    print(f"\n{'RUP':<8} {'Score':>7}  {'Umbral':^12}  {'En UNSPSC':^10}  Objeto")
    print("-" * 90)
    for doc, score in sorted(results, key=lambda x: -x[1]):
        rup      = doc.metadata.get("numero_rup", "?")
        obj_txt  = (doc.metadata.get("objeto") or "")[:55]
        supera   = "SUPERA" if score >= umbral else "bajo  "
        en_codes = "SI" if (rups_codigos and int(rup) in rups_codigos) else ("—" if rups_codigos else "N/A")
        print(f"  {str(rup):<6} {score:>7.4f}  {supera:^12}  {en_codes:^10}  {obj_txt}")

    aprobados = [doc.metadata.get("numero_rup") for doc, s in results if s >= umbral]
    print(f"\nRUPs que SUPERAN umbral {umbral}: {aprobados if aprobados else '(ninguno)'}")
    print(f"RUPs que NO superan umbral: {[doc.metadata.get('numero_rup') for doc, s in results if s < umbral][:10]} ...")


if __name__ == "__main__":
    main()
    #quick_evaluate_debug()   # ← descomentar para debug de objeto semántico
