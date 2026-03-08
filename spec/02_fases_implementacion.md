# Plan de Fases: tendermod — Completar sistema de evaluación de cumplimiento

## Ruta crítica

```
Fase 1 → Fase 2 → Fase 3 ──┐
                             ├──→ Fase 6
              Fase 2 → Fase 4 → Fase 5 ──┘

Fase 7 (opcional, independiente)
```

Fases 3 y 4 pueden ejecutarse en paralelo una vez completada la Fase 2.

---

## Fase 1 — Bugs de infraestructura (prerequisitos bloqueantes)

### Objetivo
Corregir tres bugs que contaminan capas superiores y bloquean el funcionamiento correcto del sistema. Son fixes de una línea cada uno, pero sin ellos las fases posteriores producirán resultados incorrectos silenciosamente.

### Archivos involucrados
- `src/tendermod/config/settings.py`
- `src/tendermod/evaluation/prompts.py`
- `src/tendermod/evaluation/llm_client.py`
- `.env`

### Cambios exactos por archivo

**`settings.py`** — línea 13:
- Cambiar `os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_experience")` → `os.getenv("CHROMA_EXPERIENCE_PERSIST_DIR", "./data/chroma_experience")`
- Sin este fix, el vector store de experiencia apunta al mismo directorio que el de licitación

**`prompts.py`** — línea 143:
- Cambiar `"Seccion: "` → `"Seccion": "` (comilla de cierre de clave faltante)
- Sin este fix, el LLM aprende un formato JSON inválido y falla el parsing de `ExperienceResponse`

**`llm_client.py`** — función `run_llm_indices()`:
- Cambiar parámetro `max_tokens=500` → `max_tokens=1000`
- Sin este fix, el JSON de experiencia con múltiples códigos UNSPSC puede truncarse

**`.env`**:
- Agregar línea: `CHROMA_EXPERIENCE_PERSIST_DIR=./data/chroma_experience`

### Dependencias
Ninguna. Esta fase es el punto de partida.

### Criterio de éxito
Ejecutar en Python:
```python
from tendermod.config.settings import CHROMA_PERSIST_DIR, CHROMA_EXPERIENCE_PERSIST_DIR
assert CHROMA_PERSIST_DIR != CHROMA_EXPERIENCE_PERSIST_DIR
print("OK:", CHROMA_PERSIST_DIR, CHROMA_EXPERIENCE_PERSIST_DIR)
```
Debe imprimir dos rutas distintas sin error.

Validar que el prompt de experiencia tiene JSON sintácticamente correcto revisando `"Seccion":` con comillas en ambos lados de los dos puntos.

### Riesgos
- **Riesgo**: `.env` puede no tener la nueva variable → `CHROMA_EXPERIENCE_PERSIST_DIR` usaría el default hardcoded, lo cual es aceptable pero mejor ser explícito.
- **Mitigación**: Verificar con `python -c "from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR; print(CHROMA_EXPERIENCE_PERSIST_DIR)"`.

---

## Fase 2 — Schemas de resultado

### Objetivo
Definir los tipos de dato que todos los módulos de evaluación producirán como salida. Esta fase no tiene lógica de negocio — solo define contratos Pydantic. Es prerequisito de las Fases 3, 4 y 5.

### Archivos involucrados
- `src/tendermod/evaluation/schemas.py`

### Cambios exactos por archivo

**`schemas.py`**:

*Imports a agregar*:
- `from pydantic import ConfigDict` (ya importa `BaseModel` y `Field`)
- `Optional` a los imports de `typing`

*Modificación en `ExperienceResponse`*:
- Agregar `model_config = ConfigDict(populate_by_name=True)` como primer atributo de clase
- Necesario para que `model_validate_json()` funcione correctamente cuando el JSON del LLM usa los alias definidos en `Field(alias=...)`

*Nuevo modelo `IndicatorComplianceResult`*:
- `cumple: Optional[bool]` — `True`/`False`/`None` si no se pudo determinar
- `detalle: str` — texto completo del LLM con la argumentación
- `indicadores_evaluados: List[str]` — nombres de indicadores que se compararon
- `indicadores_faltantes: List[str]` — indicadores requeridos sin datos en SQLite

*Nuevo modelo `RupExperienceResult`*:
- `numero_rup: Union[int, str]`
- `cumple_codigos: bool`
- `cumple_valor: Optional[bool]` — `None` si el pliego no especifica valor mínimo
- `cumple_objeto: Optional[bool]` — `None` si el pliego no especifica objeto requerido
- `cumple_total: bool` — `True` solo si todos los criterios evaluables son `True`

*Nuevo modelo `ExperienceComplianceResult`*:
- `codigos_requeridos: List[str]`
- `valor_requerido_cop: Optional[float]` — ya convertido a COP
- `objeto_requerido: Optional[str]`
- `rups_evaluados: List[RupExperienceResult]`
- `rups_cumplen: List[Union[int, str]]` — solo los que tienen `cumple_total=True`
- `cumple: bool` — `True` si al menos 1 RUP cumple todos los criterios evaluables

### Dependencias
Fase 1 (no hay dependencia técnica directa, pero por coherencia completar los fixes primero).

### Criterio de éxito
```python
from tendermod.evaluation.schemas import (
    IndicatorComplianceResult,
    RupExperienceResult,
    ExperienceComplianceResult,
    ExperienceResponse
)
# Debe importar sin errores

r = RupExperienceResult(numero_rup=123, cumple_codigos=True, cumple_valor=None, cumple_objeto=True, cumple_total=True)
print(r)  # debe imprimir el modelo

e = ExperienceResponse.model_validate_json('{"Listado de codigos": ["12345678"], "Cuantos codigos": "1", "Objeto": "test", "Cantidad de contratos": "1", "Valor a acreditar": "500 SMMLV", "Pagina": "5", "Seccion": "3.2"}')
print(e.listado_codigos)  # debe imprimir ['12345678']
```

### Riesgos
- **Riesgo**: Los alias en `ExperienceResponse` usan espacios (`"Listado de codigos"`) — sin `populate_by_name=True` el parsing puede fallar con ciertas versiones de Pydantic.
- **Mitigación**: El criterio de éxito incluye validación explícita del alias parsing.

---

## Fase 3 — Track 1 completo: indicadores con resultado estructurado

### Objetivo
Cerrar el Track 1 de indicadores financieros. El flujo ya funciona end-to-end pero no retorna nada — solo imprime. Esta fase agrega el return estructurado y manejo de errores sin tocar la lógica de evaluación existente.

### Archivos involucrados
- `src/tendermod/evaluation/indicators_inference.py`
- `src/tendermod/evaluation/compare_indicators.py`

### Cambios exactos por archivo

**`indicators_inference.py`** — función `get_indicators()`:
- En el bloque `except` del parsing de JSON, cambiar el return actual (dict crudo) por `return None`
- Esto alinea el comportamiento con `get_experience()` y permite detección limpia del error en `compare_indicators.py`

**`compare_indicators.py`**:

*Imports a agregar*:
- `import re`
- `from typing import Optional`
- `from tendermod.evaluation.schemas import IndicatorComplianceResult`

*Nueva función `extract_compliance_bool(text: str) -> Optional[bool]`*:
- Buscar `r'\bNo cumple\b'` primero (case-insensitive) → retornar `False`
- Buscar `r'\bCumple\b'` → retornar `True`
- Sin match → retornar `None`
- El orden importa: "No cumple" debe buscarse antes que "Cumple" para evitar el falso positivo

*Modificar `indicators_comparation()`*:
- Firma nueva: `def indicators_comparation() -> Optional[IndicatorComplianceResult]`
- Agregar guard al inicio: si `get_indicators()` retorna `None`, retornar `IndicatorComplianceResult` con `cumple=None` y `detalle="Error al extraer indicadores del PDF"`
- Después de `comparation_response`: agregar `cumple = extract_compliance_bool(comparation_response)`
- Construir y retornar `IndicatorComplianceResult(cumple=cumple, detalle=comparation_response, indicadores_evaluados=[i.indicador for i in tender_indicators.answer], indicadores_faltantes=[])`
- Mantener los prints existentes para trazabilidad durante desarrollo

### Dependencias
Fase 2 (necesita `IndicatorComplianceResult`).

### Criterio de éxito
```python
from tendermod.evaluation.compare_indicators import indicators_comparation
result = indicators_comparation()
print(type(result))   # <class 'IndicatorComplianceResult'>
print(result.cumple)  # True, False, o None
print(result.detalle) # texto del LLM
```
El sistema no debe lanzar excepción. Si el PDF está cargado y ChromaDB tiene datos, `result.cumple` debe ser `True` o `False`.

### Riesgos
- **Riesgo**: `get_indicators()` puede retornar un resultado válido donde `tender_indicators.answer` está vacío → `indicadores_evaluados` sería `[]` y `comparation_response` no tendría con qué comparar.
- **Mitigación**: El prompt del SQL Agent ya maneja indicadores faltantes — el LLM lo indica en `detalle`.

---

## Fase 4 — Funciones de validación de valor y objeto

### Objetivo
Implementar las dos validaciones que faltan en el Track 2 de experiencia: verificar que el valor acumulado del RUP supera el mínimo requerido, y que el objeto del contrato es semánticamente compatible con el requerido en el pliego. Ambas funciones son independientes del orquestador — pueden desarrollarse y probarse en aislamiento.

### Archivos involucrados
- `src/tendermod/evaluation/compare_experience.py`

### Cambios exactos por archivo

**`compare_experience.py`**:

*Imports a agregar*:
- `import re`
- `from typing import Optional`
- `from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR`
- `from tendermod.retrieval.embeddings import embed_docs`
- `from tendermod.retrieval.vectorstore import read_vectorstore`

*Constante nueva*:
- `SMMLV_2026 = 1_423_500` (valor del SMMLV 2026 en COP)

*Nueva función `parse_valor(valor_str: str) -> Optional[float]`*:
- Si `valor_str` es `"None"`, vacío, o contiene "cannot find" (case-insensitive) → `None`
- Si contiene "SMMLV": extraer número con `r'[\d.,]+'`, limpiar separadores colombianos (`.` de miles → quitar, `,` decimal → `.`), multiplicar por `SMMLV_2026`
- Si contiene `$` o patrón numérico: limpiar `.` de miles (formato colombiano), `','` decimal → `.`, convertir a float
- Detección anglosajón: si el número tiene `,` como separadores de miles (`\d{1,3}(,\d{3})+`), aplicar `re.sub(r',(?=\d{3})', '', s)` antes de parsear
- Fallback final: `None`

*Nueva función `check_value_compliance(numero_rup, valor_minimo_cop) -> bool`*:
- Parámetros: `numero_rup: Union[int, str]`, `valor_minimo_cop: float`
- Conectar a SQLite con `DB_PATH`
- SQL: `SELECT SUM("VALOR") as total FROM experiencia WHERE "NUMERO RUP" = ?`
- Si `total is None` → `False`
- Si `total == 0` → `False`
- Retornar `float(total) >= valor_minimo_cop`

*Nueva función `check_object_compliance(numero_rup, objeto_requerido, similarity_threshold=0.75) -> Optional[bool]`*:
- Parámetros: `numero_rup: Union[int, str]`, `objeto_requerido: str`, `similarity_threshold: float = 0.75`
- Guard: si `objeto_requerido` es `"None"`, vacío, o contiene "No specific purpose"/"cannot find" (case-insensitive) → `None`
- Cargar vector store: `read_vectorstore(embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR)`
- `results = vectorstore.similarity_search_with_relevance_scores(objeto_requerido, k=20)`
- Filtrar resultados donde `doc.metadata["numero_rup"] == str(numero_rup)`
- Si alguno tiene score ≥ `similarity_threshold` → `True`
- Si hay resultados del RUP pero ninguno supera el umbral → `False`
- Si no hay resultados para ese RUP → `None`

### Dependencias
Fase 1 (para `CHROMA_EXPERIENCE_PERSIST_DIR` correcto).
La ChromaDB de experiencia debe estar ingresada previamente con `ingest_experience_data()`.

### Criterio de éxito
Probar cada función en aislamiento:
```python
from tendermod.evaluation.compare_experience import parse_valor, check_value_compliance, check_object_compliance

# parse_valor
assert parse_valor("500 SMMLV") == 711_750_000.0
assert parse_valor("$100.000.000") == 100_000_000.0
assert parse_valor("I cannot find information") is None
assert parse_valor("None") is None

# check_value_compliance (con un NUMERO RUP real de la DB)
result = check_value_compliance(12345, 100_000_000.0)
print(type(result))  # bool

# check_object_compliance (requiere ChromaDB ingresada)
result = check_object_compliance(12345, "Instalación de redes eléctricas")
print(result)  # True, False, o None
```

### Riesgos
- **Riesgo 1**: ChromaDB de experiencia vacía → `check_object_compliance` retorna `None` para todos los RUPs (no evaluable). Comportamiento de degradación elegante aceptable.
- **Riesgo 2**: El LLM puede retornar valores en formato mixto ("aprox. $500 millones") que no matchea ningún regex → `parse_valor` retorna `None` correctamente.
- **Riesgo 3**: `VALOR` en SQLite puede ser `NULL` para registros incompletos → manejado con el check `total is None`.
- **Mitigación Riesgo 1**: Verificar con `python -m tendermod.ingestion.ingestion_experience_flow` antes de correr esta fase si se quiere validar `check_object_compliance`.

---

## Fase 5 — Orquestador del Track 2: experiencia completa

### Objetivo
Conectar todas las piezas del Track 2. Corregir el puente roto entre la extracción RAG del PDF (`experience_comparation`) y la validación contra SQLite/ChromaDB (`check_compliance_experience`). Esta fase consume las funciones creadas en la Fase 4 y los schemas de la Fase 2.

### Archivos involucrados
- `src/tendermod/evaluation/compare_experience.py`

### Cambios exactos por archivo

**`compare_experience.py`**:

*Imports a agregar*:
- `from tendermod.evaluation.schemas import ExperienceResponse, ExperienceComplianceResult, RupExperienceResult`

*Modificar `experience_comparation()`*:
- Firma nueva: `def experience_comparation() -> Optional[ExperienceResponse]`
- Agregar guard: si `get_experience()` retorna `None`, imprimir error descriptivo y retornar `None`
- Agregar `return tender_experience` (actualmente el resultado se descarta)

*Refactorizar `check_compliance_experience()`*:
- Firma nueva: `def check_compliance_experience(tender_experience: ExperienceResponse) -> ExperienceComplianceResult`
- Eliminar `codes = ["39121011", "721515", "81101701"]` (hardcoded)
- Extraer `codes = tender_experience.listado_codigos`
- Parsear `min_codigos`: intentar `int(tender_experience.cantidad_codigos)`, fallback a `len(codes)` si falla
- Llamar `rups_codigos = check_code_compliance(codes, min_codigos=min_codigos)`
- Llamar `valor_cop = parse_valor(tender_experience.valor)`
- Si `rups_codigos` está vacío: retornar `ExperienceComplianceResult` con `cumple=False`, listas vacías
- Para cada `rup` en `rups_codigos`:
  - `cumple_valor = check_value_compliance(rup, valor_cop) if valor_cop is not None else None`
  - `cumple_objeto = check_object_compliance(rup, tender_experience.objeto)`
  - `cumple_total = True` si `cumple_codigos=True` AND (`cumple_valor` si not None else `True`) AND (`cumple_objeto` si not None else `True`)
  - Construir `RupExperienceResult`
- Filtrar `rups_cumplen = [r.numero_rup for r in rups_evaluados if r.cumple_total]`
- Retornar `ExperienceComplianceResult(codigos_requeridos=codes, valor_requerido_cop=valor_cop, objeto_requerido=tender_experience.objeto, rups_evaluados=rups_evaluados, rups_cumplen=rups_cumplen, cumple=len(rups_cumplen) > 0)`

*Limpiar `check_code_compliance()`*:
- Eliminar la variable `where_and` que se construye pero nunca se usa (dead code identificado)

### Dependencias
Fases 2 y 4 (necesita schemas de resultado y las funciones de validación).

### Criterio de éxito
```python
from tendermod.evaluation.compare_experience import experience_comparation, check_compliance_experience

tender_exp = experience_comparation()
print(type(tender_exp))     # ExperienceResponse o None
print(tender_exp.listado_codigos)  # lista de strings, no hardcoded

if tender_exp:
    result = check_compliance_experience(tender_exp)
    print(type(result))     # ExperienceComplianceResult
    print(result.cumple)    # True o False
    print(result.rups_cumplen)  # lista de RUPs que cumplen todo
    for rup in result.rups_evaluados:
        print(rup.numero_rup, rup.cumple_codigos, rup.cumple_valor, rup.cumple_objeto)
```

### Riesgos
- **Riesgo**: `cantidad_codigos` del LLM puede ser `"tres"` o `"al menos 3"` → el `int()` fallará y se usará `len(codes)`. Documentar este comportamiento en el código.
- **Riesgo**: Si `listado_codigos` está vacío (el LLM no encontró códigos), `check_code_compliance([])` debe manejarse sin SQL inválido → agregar guard `if not codes: return ExperienceComplianceResult(cumple=False, ...)`.

---

## Fase 6 — Limpieza y orquestación final en main.py

### Objetivo
Conectar ambos tracks en el punto de entrada del sistema. Eliminar código roto (`indicators_routine`) y reemplazar la orquestación actual (solo llama una función con hardcoded) por el flujo completo que produce el veredicto final.

### Archivos involucrados
- `src/tendermod/main.py`

### Cambios exactos por archivo

**`main.py`**:

*Eliminar*:
- Función `indicators_routine()` completa (líneas 73-86) — llama a `evaluate_indicators_compliance` que no existe

*Limpiar imports*: Remover los que ya no se usan tras eliminar `indicators_routine`.

*Reescribir `main()`*:
```
1. load_dotenv()
2. Imprimir banner: "=== EVALUACION DE CUMPLIMIENTO ==="

3. TRACK 1 — Indicadores:
   result_ind = indicators_comparation()
   Imprimir resultado formateado:
     "TRACK 1 - INDICADORES FINANCIEROS"
     "  Resultado: CUMPLE / NO CUMPLE / INDETERMINADO"
     "  Detalle: {result_ind.detalle[:200]}..."

4. TRACK 2 — Experiencia:
   tender_exp = experience_comparation()
   Si es None:
     Imprimir "TRACK 2 - ERROR: No se pudieron extraer requisitos de experiencia del PDF"
   Si no es None:
     result_exp = check_compliance_experience(tender_exp)
     Imprimir:
       "TRACK 2 - EXPERIENCIA"
       "  Codigos requeridos: {result_exp.codigos_requeridos}"
       "  Valor minimo: {result_exp.valor_requerido_cop} COP"
       Por cada RUP en result_exp.rups_evaluados:
         "  RUP {rup.numero_rup} -> Codigos {'OK' if rup.cumple_codigos else 'FALLA'} | Valor {'OK' if rup.cumple_valor else 'FALLA' if rup.cumple_valor is not None else 'N/A'} | Objeto {'OK' if rup.cumple_objeto else 'FALLA' if rup.cumple_objeto is not None else 'N/A'} -> {'CUMPLE' if rup.cumple_total else 'NO CUMPLE'}"
       "  RUPs que cumplen: {result_exp.rups_cumplen}"
       "  Resultado: {'CUMPLE' if result_exp.cumple else 'NO CUMPLE'}"

5. VEREDICTO FINAL:
   cumple_ind = result_ind.cumple is not False  (None = indeterminado, no bloquea)
   cumple_exp = result_exp.cumple if result_exp else False
   cumple_final = cumple_ind and cumple_exp
   Imprimir "=== VEREDICTO FINAL: {'CUMPLE' if cumple_final else 'NO CUMPLE'} ==="
```

### Dependencias
Fases 3 y 5 (ambos tracks completos).

### Criterio de éxito
```bash
python -m tendermod.main
```
Debe imprimir el banner, ambos tracks, y el veredicto final sin excepciones. El sistema puede estar ejecutándose con datos reales o de prueba — lo importante es que no lanza `NameError`, `AttributeError`, ni `TypeError`.

Salida esperada:
```
=== EVALUACION DE CUMPLIMIENTO ===

TRACK 1 - INDICADORES FINANCIEROS
  Resultado: CUMPLE
  Detalle: La empresa cumple con los indicadores requeridos...

TRACK 2 - EXPERIENCIA
  Codigos requeridos: ['391210', '721515', '811017']
  Valor minimo: 711750000.0 COP
  RUP 12345 -> Codigos OK | Valor OK | Objeto OK -> CUMPLE
  RUPs que cumplen: [12345]
  Resultado: CUMPLE

=== VEREDICTO FINAL: CUMPLE ===
```

### Riesgos
- **Riesgo**: Si `result_ind` es `None` (no se pudo extraer), el acceso a `result_ind.cumple` lanzaría `AttributeError` → agregar guard antes del veredicto.
- **Riesgo**: `result_exp` puede ser `None` si `experience_comparation()` falla → `result_exp.cumple` lanzaría error → usar `result_exp.cumple if result_exp else False`.

---

## Fase 7 — Función LLM auxiliar para validación de objeto (opcional)

### Objetivo
Agregar una función LLM como alternativa/fallback a ChromaDB para la validación semántica del objeto de experiencia. Útil cuando el vector store de experiencia no está disponible o cuando se quiere una validación más precisa para casos borderline. Esta fase no bloquea ninguna otra.

### Archivos involucrados
- `src/tendermod/evaluation/prompts.py`
- `src/tendermod/evaluation/llm_client.py`

### Cambios exactos por archivo

**`prompts.py`**:
- Agregar constante `object_compliance_system_prompt`:
  El LLM recibe el objeto requerido por el pliego y la descripción de un contrato del RUP. Debe responder exclusivamente con JSON `{"cumple": true/false, "razon": "explicacion breve"}`. El prompt debe instruir que el dominio es contratación pública colombiana y que la compatibilidad semántica es suficiente (no requiere identidad exacta de actividades).

**`llm_client.py`**:
- Nueva función `run_llm_object_compliance(objeto_pliego: str, objeto_rup: str, descripcion_rup: str, max_tokens: int = 200, temperature: float = 0.0) -> dict`:
  - Construir user prompt concatenando los tres campos con labels
  - Llamar a OpenAI con `object_compliance_system_prompt`
  - Parsear respuesta como JSON
  - Retornar `{"cumple": bool, "razon": str}`
  - En fallo de parsing: retornar `{"cumple": None, "razon": "error de parsing"}`

### Dependencias
Fase 1 (para `max_tokens` correcto en el cliente). No bloquea ni depende de Fases 2-6.

### Criterio de éxito
```python
from tendermod.evaluation.llm_client import run_llm_object_compliance

result = run_llm_object_compliance(
    "Instalación de redes eléctricas en edificios",
    "Suministro e instalación de cableado estructurado",
    "Proyecto de infraestructura eléctrica para edificio corporativo"
)
print(result)  # {"cumple": True, "razon": "..."}
assert isinstance(result["cumple"], bool) or result["cumple"] is None
```

### Riesgos
- **Riesgo**: Costo adicional de API si se activa para muchos RUPs → usar solo como fallback cuando ChromaDB retorna `None`.

---

## Resumen ejecutivo

| Fase | Archivos | Tipo | Depende de |
|------|----------|------|------------|
| 1 — Bugs infraestructura | settings.py, prompts.py, llm_client.py | Fix (3 líneas) | — |
| 2 — Schemas de resultado | schemas.py | Nuevo (3 modelos) | 1 |
| 3 — Track 1 completo | indicators_inference.py, compare_indicators.py | Fix + nueva función | 2 |
| 4 — Validaciones valor/objeto | compare_experience.py | Nueva (3 funciones) | 1 |
| 5 — Orquestador Track 2 | compare_experience.py | Refactor + fix | 2, 4 |
| 6 — Orquestación final | main.py | Reescritura | 3, 5 |
| 7 — LLM auxiliar objeto | prompts.py, llm_client.py | Nueva función (opcional) | 1 |
