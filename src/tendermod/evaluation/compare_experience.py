


import re
import sqlite3
from typing import Optional, Dict, Union
from tendermod.evaluation.experience_inference import get_experience
from tendermod.evaluation.schemas import ExperienceResponse, ExperienceComplianceResult, RupExperienceResult
from tendermod.ingestion.experience_db_loader import DB_PATH
from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import read_vectorstore
from tendermod.evaluation.indicators_inference import get_general_info

SMMLV_2026 = 1_423_500  # Salario Mínimo Mensual Legal Vigente 2026 en COP


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
    tender_experience = get_experience(user_input=query, k=k)
    if tender_experience is None:
        print("ERROR: No se pudieron extraer requisitos de experiencia del PDF")
        return None
    return tender_experience




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


def filter_rups_by_object(
    rups: list,
    objeto_requerido: str,
    similarity_threshold: float = 0.75,
) -> tuple:
    """
    Filtra semánticamente un pool de RUPs contra el objeto requerido en el pliego.

    Evalúa todos los RUPs en una sola consulta a ChromaDB (Fase 2).
    Usa k dinámico = max(20, len(rups) * 4) para garantizar cobertura del pool
    aunque la colección sea grande.

    Política de exclusión:
    - RUP con score >= similarity_threshold → aprobado.
    - RUP con score < similarity_threshold → excluido (se loguea).
    - RUP sin registros en ChromaDB (sin datos) → conservado (comportamiento
      conservador: la duda favorece al proponente, no al sistema).

    Casos de cortocircuito — retorna (rups, {}) sin consultar ChromaDB:
    - objeto_requerido vacío, "None" o coincide con frases de "no encontrado".
    - Excepción al conectar con ChromaDB (log de advertencia crítica).

    Retorna:
        rups_aprobados (list): pool filtrado listo para check_value_compliance().
        scores_por_rup (dict): {numero_rup: float|None} para trazabilidad en el
            resultado final. None significa "sin datos en ChromaDB".
    """
    if not objeto_requerido or objeto_requerido.strip() in ("None", ""):
        return rups, {}
    if re.search(
        r'no specific purpose|cannot find|no se encontr|not found|no especif',
        objeto_requerido,
        re.IGNORECASE,
    ):
        return rups, {}

    k_dinamico = max(20, len(rups) * 4)

    try:
        vectorstore = read_vectorstore(
            embed_docs(),
            path=CHROMA_EXPERIENCE_PERSIST_DIR,
            collection_name="rup",
        )
        results = vectorstore.similarity_search_with_relevance_scores(
            objeto_requerido, k=k_dinamico
        )
    except Exception as e:
        print(
            f"ADVERTENCIA CRITICA: No se pudo consultar ChromaDB de experiencia "
            f"para el filtro de objeto. Se omite el filtro. Error: {e}"
        )
        return rups, {}

    # Agrupar scores por numero_rup → tomar el máximo por contrato
    scores_por_rup: dict = {}
    for doc, score in results:
        raw_key = doc.metadata.get("numero_rup")
        if raw_key is None:
            continue
        try:
            rup_key = int(raw_key)
        except (TypeError, ValueError):
            rup_key = raw_key
        clamped = max(0.0, min(1.0, score))
        scores_por_rup[rup_key] = max(scores_por_rup.get(rup_key, 0.0), clamped)

    if not scores_por_rup:
        print(
            "ADVERTENCIA CRITICA: ChromaDB de experiencia no devolvió resultados "
            "para el objeto requerido. Se omite el filtro de objeto."
        )
        return rups, {}

    rups_aprobados = []
    for rup in rups:
        score = scores_por_rup.get(rup)
        if score is None:
            # Sin datos en ChromaDB para este RUP → conservar
            print(
                f"[filter_rups_by_object] RUP {rup}: sin datos en ChromaDB → conservado"
            )
            rups_aprobados.append(rup)
        elif score >= similarity_threshold:
            print(
                f"[filter_rups_by_object] RUP {rup}: score={score:.3f} >= {similarity_threshold} → aprobado"
            )
            rups_aprobados.append(rup)
        else:
            print(
                f"[filter_rups_by_object] RUP {rup}: score={score:.3f} < {similarity_threshold} → EXCLUIDO por objeto"
            )

    return rups_aprobados, scores_por_rup


def check_compliance_experience(tender_experience: ExperienceResponse) -> ExperienceComplianceResult:
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

    # --- FASE 1: Seleccionar top-N contratos por valor ---
    # La regla real del pliego es acreditar con los N contratos de mayor valor,
    # no con el universo completo de contratos que cumplen los códigos.
    cantidad_n = parse_cantidad_contratos(getattr(tender_experience, 'cantidad_contratos', None))
    print(f"Cantidad de contratos requerida: {cantidad_n} (None = sin límite)")

    rups_top_n = select_top_n_rups(rups_codigos, cantidad_n)
    print(f"[Fase 1] RUPs top-{cantidad_n} por valor: {rups_top_n}")

    # --- FASE 2: Filtro semántico por objeto del proceso ---
    # Solo se aplica si el pliego exige explícitamente que la experiencia sea
    # relacionada con el objeto del proceso. Si el filtro no se activa, los
    # scores se calculan igualmente para trazabilidad pero no excluyen RUPs.
    objeto_exige_relevancia = getattr(
        tender_experience, 'objeto_exige_relevancia', 'NO_ESPECIFICADO'
    )
    objeto = tender_experience.objeto
    print(f"[Fase 2] objeto_exige_relevancia={objeto_exige_relevancia} | objeto='{objeto}'")

    scores_objeto: dict = {}
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

    if objeto_exige_relevancia == "SI" and objeto_definido:
        # Filtro activo: excluir RUPs que no superen el umbral semántico
        rups_filtrados, scores_objeto = filter_rups_by_object(rups_top_n, objeto)
        rups_excluidos = [r for r in rups_top_n if r not in rups_filtrados]
        if rups_excluidos:
            print(f"[Fase 2] RUPs excluidos por objeto: {rups_excluidos}")
    else:
        # Filtro inactivo: conservar todo el pool
        rups_filtrados = rups_top_n
        if objeto_definido:
            # Calcular scores de todas formas para auditoría (no excluye)
            _, scores_objeto = filter_rups_by_object(rups_top_n, objeto)
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

    # Obtener detalles (CLIENTE, VALOR) de los RUPs filtrados
    rup_details = get_rup_details(rups_filtrados)

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
                cumple_objeto = score_obj >= 0.75
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
            cumple_total=cumple_total
        ))

    rups_cumplen = [r.numero_rup for r in rups_evaluados if r.cumple_total]

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
        cumple=len(rups_cumplen) > 0
    )


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

