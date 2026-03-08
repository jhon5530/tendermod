# Análisis Técnico: Completar sistema de evaluación de cumplimiento

## Problema

El sistema tendermod evalúa si una empresa (proponente) cumple con los requisitos de una licitación pública colombiana. Tiene dos tracks de evaluación:

1. **Indicadores financieros**: requisitos del pliego (PDF) vs. indicadores reales de la empresa (SQLite)
2. **Experiencia RUP**: requisitos del pliego (PDF) vs. experiencia registrada en el RUP (SQLite)

Ambos tracks están parcialmente implementados. El Track 1 (indicadores) está al 85% — funciona pero no retorna resultado estructurado. El Track 2 (experiencia) está al 40% — el puente entre la extracción del PDF y la validación contra SQLite está roto y faltan dos validaciones críticas.

---

## Impacto Arquitectural

### Backend — cambios en servicios y lógica de evaluación

**Track 1 — Indicadores (cambios menores):**
- `compare_indicators.py`: `indicators_comparation()` no retorna nada — solo imprime
- `indicators_inference.py`: path de error retorna dict crudo en vez de `None`

**Track 2 — Experiencia (cambios mayores):**
- `compare_experience.py`: `experience_comparation()` descarta el resultado de `get_experience()` (sin `return`)
- `compare_experience.py`: `check_compliance_experience()` usa códigos UNSPSC hardcoded en vez de los extraídos del PDF
- `compare_experience.py`: `check_value_compliance()` no existe (TODO)
- `compare_experience.py`: `check_object_compliance()` no existe (TODO)
- `compare_experience.py`: falta orquestador `full_experience_evaluation()`
- `main.py`: `indicators_routine()` llama `evaluate_indicators_compliance()` que no existe en ningún archivo

### Base de datos — sin cambios
El esquema SQLite (tablas `indicadores` y `experiencia`) no requiere modificaciones.

### Schemas — agregar modelos de resultado
`schemas.py` solo tiene modelos de entrada. Faltan los modelos de salida para los resultados de cumplimiento.

---

## Gaps adicionales identificados en análisis profundo

1. **`get_experience()` retorna `None` sin manejo en cadena** — causaría `AttributeError` en `experience_comparation()`
2. **`get_indicators()` path de error retorna dict crudo** — `compare_indicators.py` línea 50 (`indicators.answer`) fallaría
3. **`run_llm_indices()` `max_tokens=500`** — insuficiente para JSON de experiencia con muchos códigos UNSPSC
4. **`ExperienceResponse` sin `model_config`** — `populate_by_name` puede fallar al parsear aliases con `model_validate_json()`
5. **`check_code_compliance()` construye `where_and` pero no lo usa** — dead code mezclado con score approach
6. **`qna_system_message_experience` línea 143** — typo en JSON del prompt: `"Seccion: "` en vez de `"Seccion": "` → el LLM aprende formato inválido
7. **`settings.py` línea 13** — `CHROMA_EXPERIENCE_PERSIST_DIR` lee env var `"CHROMA_PERSIST_DIR"` en vez de `"CHROMA_EXPERIENCE_PERSIST_DIR"`

---

## Decisiones de Diseño

### A) Validación de valor (`check_value_compliance`)

**Problema**: `ExperienceResponse.valor` llega como string libre del LLM: `"500 SMMLV"`, `"$100.000.000"`, `"I cannot find information on this"`.

**Decisión: Regex con fallback `None`** (sin costo de API adicional)

Lógica del parser `parse_valor(valor_str) -> Optional[float]`:
1. Si contiene `"SMMLV"` (case-insensitive): extraer número con regex `r'[\d.,]+'`, limpiar separadores colombianos, multiplicar por `SMMLV_2026 = 1_423_500`
2. Si contiene `$` o dígitos con separadores: limpiar `.` de miles (formato colombiano), convertir a float
3. Si no matchea ninguno (ej. "I cannot find..."): retornar `None` → validación marcada como no evaluable
4. Caso anglosajón (`,` como miles): agregar detección por patrón `\d{1,3}(,\d{3})+`

SQL de validación: `SELECT SUM("VALOR") FROM experiencia WHERE "NUMERO RUP" = ?`
(Se suma el VALOR de todos los contratos del RUP, ya que un proponente puede acreditar con múltiples contratos)

### B) Validación de objeto (`check_object_compliance`)

**Opciones evaluadas**:
- LLM por cada RUP: costo alto (N llamadas API), latencia proporcional. Descartado como primario.
- ChromaDB similarity: ya existe `chroma_experience` con embeddings de `OBJETO` y `DESCRIPCION GENERAL`. Costo cero de API adicional.
- Marcar como `None`: evita complejidad pero deja gap funcional crítico.

**Decisión: ChromaDB similarity search** como mecanismo primario. LLM como función auxiliar opcional.

Lógica de `check_object_compliance(numero_rup, objeto_requerido) -> Optional[bool]`:
1. Si `objeto_requerido` es `"None"` o contiene "No specific purpose"/"cannot find": retornar `None`
2. `similarity_search_with_relevance_scores(objeto_requerido, k=20)` en vector store de experiencia
3. Filtrar resultados cuyo `metadata["numero_rup"] == str(numero_rup)`
4. Si alguno tiene score ≥ 0.75: retornar `True`
5. Si hay resultados del RUP pero ninguno supera umbral: retornar `False`
6. Si no hay resultados para ese RUP: retornar `None`

### C) Extracción de bool desde texto de indicadores

**Decisión: Regex con orden correcto** para evitar falso positivo de "Cumple" dentro de "No cumple":
1. Buscar `r'\bNo cumple\b'` (case-insensitive) primero → `False`
2. Buscar `r'\bCumple\b'` → `True`
3. Sin match → `None` (indeterminado)

---

## Propuesta de Solución

### Nuevos schemas de resultado (`schemas.py`)

```python
class IndicatorComplianceResult(BaseModel):
    cumple: Optional[bool]            # True/False/None si no se pudo determinar
    detalle: str                      # Texto completo del LLM
    indicadores_evaluados: List[str]  # Nombres de indicadores comparados
    indicadores_faltantes: List[str]  # Indicadores requeridos sin datos en SQLite

class RupExperienceResult(BaseModel):
    numero_rup: Union[int, str]
    cumple_codigos: bool
    cumple_valor: Optional[bool]      # None si valor no especificado en pliego
    cumple_objeto: Optional[bool]     # None si objeto no especificado
    cumple_total: bool                # True solo si todos los evaluables son True

class ExperienceComplianceResult(BaseModel):
    codigos_requeridos: List[str]
    valor_requerido_cop: Optional[float]
    objeto_requerido: Optional[str]
    rups_evaluados: List[RupExperienceResult]
    rups_cumplen: List[Union[int, str]]
    cumple: bool                      # True si al menos 1 RUP cumple todo
```

### Corrección en `ExperienceResponse`

Agregar `model_config = ConfigDict(populate_by_name=True)` para que `model_validate_json()` funcione correctamente con aliases.

### Mapa de dependencias entre archivos

```
settings.py (paso 1)
    └── compare_experience.py (paso 7)  [CHROMA_EXPERIENCE_PERSIST_DIR]

schemas.py (paso 2)
    ├── compare_indicators.py (paso 6)  [IndicatorComplianceResult]
    └── compare_experience.py (paso 7)  [RupExperienceResult, ExperienceComplianceResult]

prompts.py (paso 3)
    └── llm_client.py (paso 4)          [object_compliance_system_prompt]

llm_client.py (paso 4)
    └── compare_experience.py (paso 7)  [run_llm_object_compliance — opcional]

indicators_inference.py (paso 5)
    └── compare_indicators.py (paso 6)  [get_indicators() con fix]

compare_indicators.py (paso 6)
    └── main.py (paso 8)

compare_experience.py (paso 7)
    └── main.py (paso 8)
```

---

## Plan de Implementación

### Paso 1 — `config/settings.py` (fix bug, prerequisito de todo)

**Tipo**: Fix 1 línea
**Archivo**: `src/tendermod/config/settings.py`

**Cambio específico**:
- Línea 13 actual: `CHROMA_EXPERIENCE_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_experience")`
- Línea 13 nueva: `CHROMA_EXPERIENCE_PERSIST_DIR = os.getenv("CHROMA_EXPERIENCE_PERSIST_DIR", "./data/chroma_experience")`

Sin este fix, el vector store de experiencia apunta al mismo directorio que el de licitación, mezclando dos colecciones completamente diferentes. También agregar `CHROMA_EXPERIENCE_PERSIST_DIR` al `.env`.

---

### Paso 2 — `evaluation/schemas.py` (nuevos modelos de resultado)

**Tipo**: Agregar 3 modelos + fix ConfigDict
**Archivo**: `src/tendermod/evaluation/schemas.py`

**Cambios**:
1. Agregar `from pydantic import ConfigDict` al import
2. Agregar `model_config = ConfigDict(populate_by_name=True)` a `ExperienceResponse`
3. Agregar modelo `IndicatorComplianceResult` con campos: `cumple: Optional[bool]`, `detalle: str`, `indicadores_evaluados: List[str]`, `indicadores_faltantes: List[str]`
4. Agregar modelo `RupExperienceResult` con campos: `numero_rup: Union[int, str]`, `cumple_codigos: bool`, `cumple_valor: Optional[bool]`, `cumple_objeto: Optional[bool]`, `cumple_total: bool`
5. Agregar modelo `ExperienceComplianceResult` con campos: `codigos_requeridos: List[str]`, `valor_requerido_cop: Optional[float]`, `objeto_requerido: Optional[str]`, `rups_evaluados: List[RupExperienceResult]`, `rups_cumplen: List[Union[int, str]]`, `cumple: bool`

---

### Paso 3 — `evaluation/prompts.py` (fix typo + prompt objeto)

**Tipo**: Fix typo + agregar prompt
**Archivo**: `src/tendermod/evaluation/prompts.py`

**Cambios**:
1. Corregir línea 143: `"Seccion: "` → `"Seccion": "` (el typo hace que el LLM aprenda JSON inválido)
2. Agregar constante `object_compliance_system_prompt` — el LLM recibe el objeto requerido por el pliego y la descripción de un contrato del RUP, responde exclusivamente con JSON `{"cumple": true/false, "razon": "..."}`

---

### Paso 4 — `evaluation/llm_client.py` (ajuste max_tokens + función objeto)

**Tipo**: Fix parámetro + nueva función
**Archivo**: `src/tendermod/evaluation/llm_client.py`

**Cambios**:
1. Cambiar default `max_tokens=500` → `max_tokens=1000` en `run_llm_indices()` (el JSON de experiencia puede superar 500 tokens)
2. Agregar función `run_llm_object_compliance(objeto_pliego, objeto_rup, descripcion_rup, max_tokens=200, temperature=0.0) -> dict`
   - Construir user prompt concatenando los tres campos
   - Llamar a OpenAI con `object_compliance_system_prompt`
   - Parsear respuesta como JSON
   - Retornar `{"cumple": bool, "razon": str}`, o `{"cumple": None, "razon": "error de parsing"}` en fallo

---

### Paso 5 — `evaluation/indicators_inference.py` (fix path de error)

**Tipo**: Fix menor
**Archivo**: `src/tendermod/evaluation/indicators_inference.py`

**Cambio**: En el bloque `except` del parsing, cambiar el return de dict crudo a `None`, alineando el comportamiento con `get_experience()` y permitiendo detección correcta del error en `compare_indicators.py`.

---

### Paso 6 — `evaluation/compare_indicators.py` (return estructurado)

**Tipo**: Agregar función + modificar return
**Archivo**: `src/tendermod/evaluation/compare_indicators.py`

**Cambios**:
1. Agregar función `extract_compliance_bool(text: str) -> Optional[bool]`:
   - Buscar `r'\bNo cumple\b'` (case-insensitive) primero → `False`
   - Buscar `r'\bCumple\b'` → `True`
   - Sin match → `None`
2. En `indicators_comparation()`:
   - Después de `comparation_response`, agregar `cumple = extract_compliance_bool(comparation_response)`
   - Construir y retornar `IndicatorComplianceResult(cumple=cumple, detalle=comparation_response, indicadores_evaluados=[i.indicador for i in tender_indicators.answer], indicadores_faltantes=[])`
   - Envolver en try/except para manejar el caso donde `get_indicators()` retorna `None`

**Firma final**:
```python
def indicators_comparation() -> Optional[IndicatorComplianceResult]
```

---

### Paso 7 — `evaluation/compare_experience.py` (reescritura casi completa)

**Tipo**: 2 fixes + 3 funciones nuevas
**Archivo**: `src/tendermod/evaluation/compare_experience.py`

**Constante nueva en módulo**: `SMMLV_2026 = 1_423_500`

**Cambio 1 — Corregir `experience_comparation()`**:
```python
def experience_comparation() -> Optional[ExperienceResponse]
```
- Mantener query y k actuales
- Validar: si `get_experience()` retorna `None`, imprimir error y retornar `None`
- Retornar `tender_experience`

**Cambio 2 — Refactorizar `check_compliance_experience()`**:
```python
def check_compliance_experience(
    tender_experience: ExperienceResponse
) -> ExperienceComplianceResult
```
- Extraer `codes = tender_experience.listado_codigos` (ya no hardcoded)
- Parsear `min_codigos` desde `tender_experience.cantidad_codigos` (try int(), fallback a `len(codes)`)
- Llamar `rups_codigos = check_code_compliance(codes, min_codigos=min_codigos)`
- Llamar `valor_cop = parse_valor(tender_experience.valor)`
- Si `rups_codigos` vacío: retornar `ExperienceComplianceResult` con `cumple=False`
- Para cada RUP en `rups_codigos`: evaluar valor y objeto, construir `RupExperienceResult`
- Construir `cumple_total = cumple_codigos AND (cumple_valor si not None else True) AND (cumple_objeto si not None else True)`
- Retornar `ExperienceComplianceResult`

**Función nueva 1 — `parse_valor(valor_str: str) -> Optional[float]`**:
1. Si vacío, `"None"`, contiene "cannot find" → `None`
2. Si contiene "SMMLV": regex `r'[\d.,]+'`, limpiar separadores colombianos, × `SMMLV_2026`
3. Si contiene `$` o patrón numérico: limpiar `.` de miles, `','` de decimales, convertir a float
4. Si patrón anglosajón (`,` como miles): `re.sub(r',(?=\d{3})', '', s)` antes de parsear
5. Fallback: `None`

**Función nueva 2 — `check_value_compliance(numero_rup, valor_minimo_cop) -> bool`**:
```python
def check_value_compliance(
    numero_rup: Union[int, str],
    valor_minimo_cop: float,
    table: str = "experiencia",
) -> bool
```
- SQL: `SELECT SUM("VALOR") as total FROM experiencia WHERE "NUMERO RUP" = ?`
- Si `total is None`: retornar `False`
- Retornar `float(total) >= valor_minimo_cop`

**Función nueva 3 — `check_object_compliance(numero_rup, objeto_requerido) -> Optional[bool]`**:
```python
def check_object_compliance(
    numero_rup: Union[int, str],
    objeto_requerido: str,
    similarity_threshold: float = 0.75,
) -> Optional[bool]
```
- Si `objeto_requerido` es `"None"`, vacío, o contiene "No specific purpose"/"cannot find": `None`
- Leer vector store de experiencia con `read_vectorstore(embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR)`
- `results = vectorstore.similarity_search_with_relevance_scores(objeto_requerido, k=20)`
- Filtrar resultados donde `metadata["numero_rup"] == str(numero_rup)`
- Si alguno tiene score ≥ `similarity_threshold`: `True`
- Si hay resultados del RUP pero ninguno supera umbral: `False`
- Sin resultados para el RUP: `None`

---

### Paso 8 — `main.py` (orquestación limpia)

**Tipo**: Reescritura del orquestador
**Archivo**: `src/tendermod/main.py`

**Cambios**:
1. Eliminar `indicators_routine()` (llama función inexistente `evaluate_indicators_compliance`)
2. Reemplazar `main()` con orquestador limpio:

```
main():
  load_dotenv()
  print banner

  # Track 1
  result_indicadores = indicators_comparation()
  print Track 1 result con formato

  # Track 2
  tender_experience = experience_comparation()
  if tender_experience is None:
    print error
  else:
    result_experiencia = check_compliance_experience(tender_experience)
    print Track 2 result con formato por RUP

  # Veredicto final
  cumple_final = (result_indicadores.cumple is not False) AND result_experiencia.cumple
  print veredicto final
```

**Salida esperada del sistema terminado**:
```
=== EVALUACION DE CUMPLIMIENTO ===

TRACK 1 - INDICADORES FINANCIEROS
  Resultado: CUMPLE / NO CUMPLE / INDETERMINADO
  Detalle: [texto del LLM]

TRACK 2 - EXPERIENCIA
  Codigos requeridos: [lista]
  Valor requerido:    $XXX.XXX.XXX COP
  Objeto requerido:   "..."

  RUP 12345 -> Codigos OK | Valor OK | Objeto OK -> CUMPLE
  RUP 67890 -> Codigos OK | Valor FALLA | Objeto OK -> NO CUMPLE

  RUPs que cumplen: [12345]
  Resultado: CUMPLE

=== VEREDICTO FINAL: CUMPLE / NO CUMPLE ===
```

---

## Tabla de cambios consolidada

| Función | Archivo | Estado actual | Estado final |
|---------|---------|---------------|--------------|
| `indicators_comparation()` | compare_indicators.py | Solo imprime | Retorna `IndicatorComplianceResult` |
| `extract_compliance_bool()` | compare_indicators.py | No existe | Nueva |
| `experience_comparation()` | compare_experience.py | Descarta resultado | Retorna `Optional[ExperienceResponse]` |
| `check_compliance_experience()` | compare_experience.py | Códigos hardcoded, sin retorno | Recibe `ExperienceResponse`, retorna `ExperienceComplianceResult` |
| `parse_valor()` | compare_experience.py | No existe | Nueva |
| `check_value_compliance()` | compare_experience.py | No existe (TODO) | Nueva |
| `check_object_compliance()` | compare_experience.py | No existe (TODO) | Nueva (ChromaDB) |
| `get_indicators()` | indicators_inference.py | Error path = dict crudo | Error path = `None` |
| `run_llm_indices()` | llm_client.py | `max_tokens=500` | `max_tokens=1000` |
| `run_llm_object_compliance()` | llm_client.py | No existe | Nueva (opcional) |
| `main()` | main.py | Llama función inexistente | Orquestador limpio |
| `indicators_routine()` | main.py | Código roto | Eliminada |
| `ExperienceResponse` | schemas.py | Sin `model_config` | Con `ConfigDict(populate_by_name=True)` |
| `IndicatorComplianceResult` | schemas.py | No existe | Nuevo modelo |
| `RupExperienceResult` | schemas.py | No existe | Nuevo modelo |
| `ExperienceComplianceResult` | schemas.py | No existe | Nuevo modelo |
| `CHROMA_EXPERIENCE_PERSIST_DIR` | settings.py | Lee env var incorrecta | Lee `"CHROMA_EXPERIENCE_PERSIST_DIR"` |

---

## Consideraciones de Riesgo

**Riesgo 1 — ChromaDB de experiencia puede no estar ingresada**: `check_object_compliance()` depende de que `ingest_experience_data()` haya sido ejecutado previamente. Si `data/chroma_experience/` está vacío, todos los objetos serán `None` (no evaluables). Comportamiento de degradación elegante aceptable.

**Riesgo 2 — Separador de miles en valores COP**: El parser asume notación colombiana (`.` para miles, `,` para decimales). Si el LLM retorna notación anglosajona (`$100,000,000`), se necesita detección del patrón adicional.

**Riesgo 3 — `cantidad_codigos` como string ambiguo del LLM**: Puede llegar como `"3"`, `"tres"`, `"al menos 3"`. El parseo a `int` debe ser defensivo: intentar `int()`, fallback a `len(codes)`.

**Riesgo 4 — Columna `VALOR` en SQLite con NULL o cero**: `check_value_compliance()` debe manejar `NULL` (→ `False`) y `0` (→ `False` si `valor_minimo_cop > 0`).
