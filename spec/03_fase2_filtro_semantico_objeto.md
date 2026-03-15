# Fase 2: Filtro semántico por objeto del proceso

## Contexto

La Fase 1 implementó la selección de top-N contratos por valor. Esta fase agrega una capa adicional: si el pliego exige que la experiencia sea **relacionada con el objeto del proceso**, los RUPs que no sean semánticamente relevantes al objeto se excluyen del pool antes de calcular el cumplimiento de valor.

**Problema actual:** `check_object_compliance()` existe pero solo anota `cumple_objeto` por RUP — no excluye candidatos ni afecta el cálculo de valor. Adicionalmente, tiene un bug crítico: llama `read_vectorstore()` sin `collection_name`, leyendo la colección equivocada (la experiencia está en colección `"rup"`).

---

## Bug crítico (prerrequisito)

`check_object_compliance()` en `compare_experience.py` llama:
```python
read_vectorstore(embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR)
```
Sin especificar `collection_name="rup"`, por lo que actualmente siempre devuelve `None`.

---

## Flujo actualizado (post Fase 1 + Fase 2)

```
1. check_code_compliance()         → rups_codigos (pool completo)
2. select_top_n_rups()             → rups_top_n (top-N por valor)   ← Fase 1
3. filter_rups_by_object()         → rups_filtrados                  ← Fase 2
   (solo si objeto_exige_relevancia = "SI")
4. check_value_compliance(rups_filtrados) → cumple_valor_global
   (ahora calcula sobre pool ya filtrado por objeto)
5. Construir RupExperienceResult con scores y RUPs excluidos
```

---

## Cambios por archivo

### `src/tendermod/evaluation/schemas.py`

**`ExperienceResponse`** — nuevo campo:
```python
objeto_exige_relevancia: Literal["SI", "NO", "NO_ESPECIFICADO"] = Field(
    default="NO_ESPECIFICADO",
    description="SI si el pliego exige que la experiencia sea relacionada con el objeto del proceso"
)
```

**`RupExperienceResult`** — nuevo campo para auditoría:
```python
score_objeto: Optional[float] = Field(
    default=None,
    description="Score de similitud semántica con el objeto requerido (0.0-1.0). None si no aplica."
)
```

**`ExperienceComplianceResult`** — nuevos campos:
```python
rups_excluidos_por_objeto: List[Union[int, str]] = []
objeto_exige_relevancia: Optional[str] = None
```

---

### `src/tendermod/evaluation/prompts.py`

Agregar **pregunta 7** en `qna_system_message_experience` (después de la pregunta 6 de `regla_codigos`):

```
7- Does the tender explicitly require that the experience must be related to or in the same area
   as the object/purpose of this specific contracting process?
   Answer "SI" ONLY if the pliego uses phrases like "experiencia relacionada con el objeto",
   "experiencia en actividades similares al objeto del contrato", or explicitly links
   experience requirements to the purpose of the process.
   Answer "NO" if the pliego explicitly states experience is not restricted by object.
   Answer "NO_ESPECIFICADO" in all other cases.
```

Agregar en el ejemplo JSON del prompt:
```json
"Objeto exige relevancia": "NO_ESPECIFICADO"
```

---

### `src/tendermod/retrieval/vectorstore.py`

Agregar parámetro opcional `collection_name` a `read_vectorstore()`:
```python
def read_vectorstore(embeddings, path=CHROMA_PERSIST_DIR, collection_name=None):
    kwargs = {"persist_directory": path, "embedding_function": embeddings}
    if collection_name:
        kwargs["collection_name"] = collection_name
    return Chroma(**kwargs)
```
Cambio backward compatible — callers existentes sin `collection_name` no se ven afectados.

---

### `src/tendermod/evaluation/compare_experience.py`

**Nueva función `filter_rups_by_object()`** (reemplaza el bucle individual de `check_object_compliance`):

- Consulta ChromaDB una sola vez con `k = max(20, len(rups) * 4)` para cubrir todo el pool
- Especifica `collection_name="rup"` al llamar `read_vectorstore()`
- Agrupa scores por `numero_rup`, toma el máximo por contrato
- Conserva RUPs sin datos en ChromaDB (score=None → no penalizar)
- Excluye RUPs con `score < similarity_threshold` (default: 0.75)

**Reordenar `check_compliance_experience()`:**
- Insertar llamada a `filter_rups_by_object()` entre `select_top_n_rups()` y `check_value_compliance()`
- Activar filtro solo si `objeto_exige_relevancia == "SI"`
- Si `"NO_ESPECIFICADO"`: calcular scores para auditoría pero no excluir ningún RUP
- `check_value_compliance()` recibe `rups_filtrados` (no `rups_top_n`)

---

## Reglas de activación del filtro

| `objeto_exige_relevancia` | Comportamiento |
|---|---|
| `"SI"` | Excluir RUPs con score < 0.75. Si RUP no está en ChromaDB → conservarlo |
| `"NO"` | No filtrar. Calcular scores para auditoría |
| `"NO_ESPECIFICADO"` | No filtrar. Calcular scores para auditoría |
| `"SI"` + ChromaDB vacío | Advertencia crítica en log + tratar como `"NO_ESPECIFICADO"` |

---

## Casos edge

| Caso | Comportamiento esperado |
|---|---|
| `objeto` = `"None"` o vacío | No ejecutar `filter_rups_by_object()`. Retornar pool sin cambios |
| RUP no tiene registros en ChromaDB experiencia | Score = None → conservar (no penalizar por falta de datos) |
| Todos los top-N fallan el filtro de objeto | `rups_filtrados` vacío → `cumple=False` |
| Pool top-N tiene 3 RUPs, k=20 cubre todos | Sin problema; k dinámico = max(20, 3*4)=20 |

---

## Verificación

```bash
source .venv/bin/activate && python -m tendermod.main
```

Validar en el output:
1. El campo `objeto_exige_relevancia` aparece en la respuesta de experiencia
2. Si es `"SI"`, los RUPs excluidos se listan en `rups_excluidos_por_objeto`
3. `total_valor_cop` refleja solo los RUPs que pasaron el filtro de objeto
4. No hay `None` por bug de `collection_name` en vectorstore de experiencia

---

## Archivos a modificar

| Archivo | Tipo de cambio |
|---|---|
| `src/tendermod/evaluation/schemas.py` | 3 campos nuevos en 3 schemas |
| `src/tendermod/evaluation/prompts.py` | Pregunta 7 en system prompt de experiencia |
| `src/tendermod/retrieval/vectorstore.py` | Parámetro `collection_name` en `read_vectorstore()` |
| `src/tendermod/evaluation/compare_experience.py` | Nueva `filter_rups_by_object()`, reordenar flujo |
