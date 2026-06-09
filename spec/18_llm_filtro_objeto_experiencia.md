# Spec 18 — LLM como filtro de relevancia de objeto (reemplaza ChromaDB en filter_rups_by_object)

## Contexto

El filtro semántico de experiencia usaba `text-embedding-3-small` + ChromaDB. El diagnóstico de sesión #99 confirmó que el modelo asigna score 0.636 a "video conferencia" y 0.615 a "SISTEMA HIPERCONVERGENTE" para el mismo query — el contrato incorrecto puntúa más alto. Ningún ajuste de threshold puede resolver esto.

Se reemplaza el search vectorial por un LLM que razona sobre relevancia de negocio, igual que el Consultor Redneet.

---

## TODO-LIST

- [x] **1. Añadir `EXPERIENCE_OBJECT_RELEVANCE_SYSTEM` en `prompts.py`**

- [x] **2. Añadir `_fetch_rup_data_for_llm(rups)` en `compare_experience.py`**
  - Query SQLite para OBJETO y DESCRIPCION GENERAL de los RUPs del pool

- [x] **3. Añadir `_filter_rups_by_object_llm(rups, objeto_requerido)` en `compare_experience.py`**
  - Carga datos del pool desde SQLite
  - Llama gpt-4.1-mini con prompt de evaluación
  - Parsea JSON `{rup: score_0_10}`
  - Retorna misma firma que función actual: `(rups_aprobados, scores_por_rup, objetos_por_rup)`
  - Threshold: score >= 7 → cumple
  - Scores normalizados /10 para compatibilidad con display

- [x] **4. Modificar `filter_rups_by_object()` en `compare_experience.py`**
  - Renombrar implementación actual a `_filter_rups_by_object_chromadb()`
  - `filter_rups_by_object()` llama LLM y hace fallback a ChromaDB si falla

---

## Lo que NO cambia

- Firma de `filter_rups_by_object()` — idéntica
- Campos `score_objeto` y `cumple_objeto` en `RupExperienceResult`
- ChromaDB experiencia — fallback
- Flujo MULTI_CONDICION — recibe el beneficio automáticamente
- `check_object_compliance()` — no cambia
