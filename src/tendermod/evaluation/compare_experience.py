


import sqlite3
from typing import Union
from tendermod.evaluation.experience_inference import get_experience
from tendermod.ingestion.experience_db_loader import DB_PATH


def experience_comparation():

    """Query para obtener los experiencias del RAG"""
    query = """

    - EXPERIENCIA DEL PROPONENTE
    - EXPERIENCIA DEL OFERENTE

    """
    k = 10
    tender_experience = get_experience(user_input=query, k=k)




def check_compliance_experience():
    
    codes = ["39121011", "721515", "81101701"]

    # Valide si la experiencia cumple con los codigos minimos solicitados
    rups = check_code_compliance(codes, min_codigos=3)
    print(f"RUP experience in compliance with codes: {rups}")          # -> lista

    # Valide si cumple con el valor a acreditar
    # Valide si cumple con el objeto


def check_code_compliance(
    code_list,
    table: str = "experiencia",
    rup_col: str = "NUMERO RUP",
    min_codigos = 1
    ):

    
    db_path = DB_PATH

    code_list_normalized = []

    [code_list_normalized.append(normalize_to_prefix6(c)) for c in code_list]

    print("Code List Normalized", code_list_normalized, "\n")
    """
    Devuelve los NUMERO RUP que cumplen TODOS los prefijos (AND):
    - Para cada prefijo (columna), el valor debe ser distinto de 0 (o no nulo).
    """

    # Construye condiciones AND: COALESCE("391210",0) <> 0 AND ...
    where_and = " AND ".join([f'COALESCE("{p}", 0) <> 0' for p in code_list_normalized])

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
    s = str(code).strip()
    if len(s) < 6 or not s[:6].isdigit():
        return s[:6]
    return s[:6]

