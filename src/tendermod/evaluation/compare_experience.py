


import re
import sqlite3
from typing import Optional, Dict, Union
from tendermod.evaluation.experience_inference import get_experience
from tendermod.ingestion.experience_db_loader import DB_PATH
from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import read_vectorstore

SMMLV_2026 = 1_423_500  # Salario Mínimo Mensual Legal Vigente 2026 en COP


def experience_comparation():

    """Query para obtener los experiencias del RAG"""
    query = """

    - EXPERIENCIA DEL PROPONENTE
    - EXPERIENCIA DEL OFERENTE

    """
    k = 10
    tender_experience = get_experience(user_input=query, k=k)




def parse_valor(valor_str: str) -> Optional[float]:
    """
    Parsea el string de valor mínimo requerido extraído del pliego por el LLM.
    Soporta formatos: '500 SMMLV', '$100.000.000', '100,000,000' (anglosajón).
    Retorna None si no se puede parsear (valor no especificado o formato desconocido).
    """
    if not valor_str or valor_str.strip() in ("None", ""):
        return None
    if re.search(r'cannot find|no se encontr|not found|no especif', valor_str, re.IGNORECASE):
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
            return float(raw) * SMMLV_2026
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


def check_value_compliance(
    numero_rup: Union[int, str],
    valor_minimo_cop: float,
    table: str = "experiencia",
) -> bool:
    """
    Verifica si la suma del VALOR de todos los contratos del RUP
    supera el valor mínimo requerido en COP.
    """
    db_path = DB_PATH
    sql = f'SELECT SUM("VALOR") as total FROM {table} WHERE "NUMERO RUP" = ?'
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(sql, (str(numero_rup),))
        row = cur.fetchone()

    if row is None or row[0] is None:
        return False
    total = float(row[0])
    if total == 0:
        return False
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


def check_compliance_experience():
    
    codes = ["39121011", "721515", "81101701"]

    # Valide si la experiencia cumple con los codigos minimos solicitados
    rups = check_code_compliance(codes, min_codigos=3)
    print(f"RUP experience in compliance with codes: {rups}")          # -> lista

    #TODO
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

