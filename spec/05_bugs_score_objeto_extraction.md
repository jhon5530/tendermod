# Plan: Bugs de Score Objeto y Extracción de Objeto Requerido

## Fecha
2026-03-22

## Contexto
Durante revisión de resultados de evaluación rápida se identificaron dos bugs relacionados que
hacen que el filtro semántico de objeto (Fase 2) sea inoperable en la práctica:

1. El LLM extrae un objeto incorrecto del pliego (ej. "Venta de frutas y hortalizas"
   para un proceso de tecnología con UNSPSC 432217/432233/432226/811617).
2. Los RUPs del top-N muestran Score "N/A" aunque `objeto_exige_relevancia = "SI"`,
   y todos CUMPLEN sin validación real de objeto.

---

## Bug A — Extracción incorrecta del objeto requerido

### Síntoma
`exp_result.objeto_requerido` contiene texto no relacionado con el proceso
(ej. "Venta de frutas y hortalizas" en un pliego de cómputo).

### Causa
El retriever de `experience_inference.py` trae chunks del PDF que pueden
pertenecer a secciones distintas a la de experiencia (ejemplos, tablas, anexos).
El LLM toma ese texto y lo asigna al campo `objeto` sin cuestionarlo.

### Archivos implicados
- `src/tendermod/evaluation/experience_inference.py` — query de retrieval
- `src/tendermod/evaluation/prompts.py` — prompt de extracción de experiencia

### Fix propuesto
1. Reforzar el prompt para que el LLM ancle el campo `objeto` al **objeto del proceso**
   (primera sección del pliego) y no a un contrato de ejemplo.
2. Incluir instrucción explícita: "Si el chunk no describe requisitos de experiencia
   del proponente, devuelve `objeto = 'None'`".
3. Evaluar si se debe hacer un retrieval separado para el objeto del proceso
   (usando `indicators_inference.get_general_info()`) y pasarlo como contexto
   al prompt de experiencia.

---

## Bug B — "Sin datos en top-k" tratado igual que "Sin datos en ChromaDB"

### Síntoma
Con `objeto_exige_relevancia = "SI"`, todos los RUPs del top-N muestran
`Score Obj. = N/A` en la UI y TODOS CUMPLEN sin validación de objeto.

### Causa raíz (trazado en compare_experience.py)

```
filter_rups_by_object("Venta de frutas y hortalizas", k=max(20, 4*4)=20)
    → ChromaDB devuelve top-20 documentos similares a "frutas"
    → Los RUPs 167/191/196/138 tienen contratos de tecnología → NO aparecen
      en los top-20 (alta disimilitud, no ausencia de datos)
    → scores_por_rup no contiene 167/191/196/138

En el loop (línea 376-383):
    score = scores_objeto.get(rup)  # → None
    if score is None:
        rups_aprobados.append(rup)  # ← conservado por política conservadora

En la construcción del resultado (línea 536-537):
    elif score_obj is None:
        cumple_objeto = None

En cumple_total (línea 545):
    (cumple_objeto if cumple_objeto is not None else True)  # None → True
```

**Conclusión:** "no apareció en el top-k" (RUP existe en ChromaDB pero es
disímil) es tratado como "no tiene datos en ChromaDB" (RUP no existe).
Ambos devuelven `score = None`, pero su semántica es opuesta.

### Fix propuesto — `filter_rups_by_object()` en compare_experience.py

Cuando el filtro está **activo** (`objeto_exige_relevancia = "SI"`), distinguir
entre las dos causas de `score = None`:

**Opción A (recomendada): aumentar k hasta cubrir todos los RUPs**
```python
# En lugar de k = max(20, len(rups) * 4), usar k = total_docs
# para garantizar que si el RUP tiene datos, aparecerá.
k_dinamico = total_docs  # consulta completa, ordenada por score
```
Con esto, si un RUP tiene datos en ChromaDB pero score bajo,
aparecerá en los resultados con su score real y será excluido
correctamente. Solo recibirá `score = None` si genuinamente no tiene
ningún documento en la colección.

**Opción B (alternativa): verificar existencia del RUP antes de conservar**
```python
# Verificar si el RUP tiene al menos 1 documento en ChromaDB
rup_existe = vectorstore._collection.get(
    where={"numero_rup": str(rup)}, limit=1
)
if not rup_existe["ids"]:
    # genuinamente sin datos → conservar
else:
    # tiene datos pero score bajo → excluir
```

La Opción A es más simple y robusta (sin overhead de queries adicionales).
El único costo es devolver más resultados de ChromaDB, lo cual es aceptable
dado el tamaño típico de la colección.

---

## Bug C (UI) — Score no visible para RUPs que CUMPLEN sin filtro activo

### Síntoma
En la tabla de resultados (`results.html`) los RUPs que CUMPLEN
muestran "N/A" en Score Obj. aunque `objeto_exige_relevancia = "SI"`.

### Causa
Deriva directamente de Bug B: `score_objeto = None` porque los RUPs
no aparecen en el top-k. La UI no puede mostrar un score que no existe.

**Este bug se resuelve automáticamente al resolver Bug B.**

---

## Orden de implementación

1. **Bug B primero** (fix en `filter_rups_by_object`): con k = total_docs,
   los scores aparecerán correctamente y el filtro excluirá RUPs disímiles.
2. **Bug A segundo** (fix en prompt/retrieval de objeto): con el objeto
   extraído correctamente, el filtro semántico operará sobre la query correcta.
3. **Verificación**: ejecutar evaluación rápida con el PDF de DIAN y confirmar:
   - `objeto_requerido` describe tecnología/cómputo (no frutas)
   - Score Obj. muestra valores numéricos para los RUPs del top-N
   - RUPs con score < 0.75 son excluidos cuando `objeto_exige_relevancia = "SI"`

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `src/tendermod/evaluation/compare_experience.py` | `filter_rups_by_object()`: usar `k = total_docs` |
| `src/tendermod/evaluation/prompts.py` | Reforzar instrucción del campo `objeto` |
| `src/tendermod/evaluation/experience_inference.py` | Evaluar retrieval separado para objeto |
