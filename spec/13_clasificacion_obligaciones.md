# Spec 13 — Nuevos tipos de clasificación: OBLIGACION e IDIOMA

## Contexto

Al extraer requisitos generales del pliego, dos categorías de ítems no tienen clasificación
adecuada:

1. **Obligaciones del contratista**: ítems de capítulos de OBLIGACIONES DEL CONTRATISTA
   se mezclan con habilitantes sin distinción. Deben clasificarse como `tipo="OBLIGACION"`.

2. **Idioma/lenguaje de presentación**: requisitos sobre el idioma en que debe presentarse
   la oferta (ej. "la oferta debe redactarse en español", "documentos en idioma oficial")
   no tienen tipo propio y caen en `HABILITANTE` genérico o `NO_ESPECIFICADO`.
   Deben clasificarse como `tipo="IDIOMA"`.

**Bug crítico activo (OBLIGACION):** El prompt ya instruye al LLM a usar `tipo="OTRO"` para
ítems de obligaciones, pero `"OTRO"` no existe en el Literal de `schemas.py`. Pydantic falla
silenciosamente y todos caen a `NO_ESPECIFICADO`.

---

## Archivos a modificar

### 1. `src/tendermod/evaluation/schemas.py` — Agregar dos valores al Literal de `tipo`

```python
# ANTES
tipo: Literal[
    "HABILITANTE", "HABILITANTE-EXPERIENCIA", "HABILITANTE-INDICADORES",
    "PUNTUABLE", "DOCUMENTAL", "GARANTIA", "CAUSAL_RECHAZO", "NO_ESPECIFICADO",
] = "NO_ESPECIFICADO"

# DESPUÉS
tipo: Literal[
    "HABILITANTE", "HABILITANTE-EXPERIENCIA", "HABILITANTE-INDICADORES",
    "PUNTUABLE", "DOCUMENTAL", "GARANTIA", "CAUSAL_RECHAZO",
    "OBLIGACION",   # obligación del contratista durante ejecución (post-adjudicación)
    "IDIOMA",       # requisito sobre idioma/lenguaje de presentación de la oferta
    "NO_ESPECIFICADO",
] = "NO_ESPECIFICADO"
```

### 2. `src/tendermod/evaluation/prompts.py` — Documentar los nuevos tipos en el system prompt

En `qna_system_message_general_requirements`, añadir a la lista de tipos:
```
- OBLIGACION     : obligación del contratista durante la ejecución del contrato
                   (post-adjudicación). No es criterio de oferta ni de evaluación de propuesta.
- IDIOMA         : requisito sobre el idioma o lenguaje de presentación de la oferta
                   (ej. "la oferta debe redactarse en español", "documentos en idioma oficial").
```
Cambiar la regla de obligaciones de `tipo="OTRO"` a `tipo="OBLIGACION"`.

Añadir regla de idioma:
```
- Si el ítem describe el idioma en que debe presentarse la oferta o sus documentos → tipo="IDIOMA"
```

### 3. `src/tendermod/evaluation/llm_client.py` — Corregir nota de obligaciones

```python
# ANTES
"son tipo='OTRO'. NUNCA uses tipo='PUNTUABLE' ..."

# DESPUÉS
"son tipo='OBLIGACION'. NUNCA uses tipo='PUNTUABLE' ..."
```

### 4. `src/tendermod/evaluation/general_requirements_inference.py` — Override determinístico

No depender solo de que el LLM siga la instrucción. Forzar el tipo después de la respuesta:

```python
# En _fetch_chapter_requirements(), tras extender results:
if is_obligation:
    for req in results:
        req.tipo = "OBLIGACION"
```

**Por qué post-proceso:** el LLM puede ignorar la nota cuando el texto del capítulo
parece contener criterios puntuables. El override es determinístico y garantiza el resultado.

### 5. `src/tendermod/evaluation/general_requirements_inference.py` — Ampliar keywords

```python
_OBLIGATION_CHAPTER_KEYWORDS = [
    "OBLIGACION", "CLAUSULA", "SUPERVISION", "SEGUIMIENTO",
    "ANS", "EJECUCION DEL CONTRATO", "DEBER",
    "OBLIGACIONES ESPECIALES",   # ← nuevo
    "OBLIGACIONES GENERALES",    # ← nuevo
    "COMPROMISOS",               # ← nuevo
]
```

### 6. `src/tendermod/evaluation/general_requirements_inference.py` — Detección de capítulos de idioma

A diferencia de OBLIGACION (que se detecta por título de capítulo), `IDIOMA` se detecta
a nivel de ítem por el LLM basándose en el contenido. No requiere override determinístico
porque el LLM puede identificarlo correctamente con la instrucción del prompt.

Sin embargo, agregar keywords opcionales para forzarlo si el capítulo completo es de idioma:

```python
_LANGUAGE_CHAPTER_KEYWORDS = [
    "IDIOMA", "LENGUAJE", "LINGUA", "LANGUAGE",
    "PRESENTACION DE LA OFERTA",   # capítulos con instrucciones generales de presentación
]
```

Si `_is_language_chapter(title)` → override `tipo="IDIOMA"` para todos los ítems del capítulo
(mismo patrón que OBLIGACION).

---

## Impacto en el sistema

| Área | Impacto |
|------|---------|
| Extracción | Obligaciones → `OBLIGACION`; ítems de idioma → `IDIOMA`; resto sin cambio |
| Exportación Excel | Verificar que los nuevos tipos no rompan formato de colores/agrupación |
| Vista de resultados | Verificar que `results.html` muestre los tipos correctamente |
| Lógica de evaluación | Sin cambios — solo clasificación, no afecta cumplimiento |

---

## Verificación

1. Subir un pliego con capítulo "OBLIGACIONES DEL CONTRATISTA" y cláusula de idioma.
2. Correr extracción de requisitos generales.
3. Confirmar que ítems de capítulo de obligaciones → `tipo=OBLIGACION`.
4. Confirmar que el requisito "la oferta debe presentarse en español" → `tipo=IDIOMA`.
5. Confirmar que ítems de capítulos habilitantes conservan sus tipos originales.
6. Confirmar que la exportación Excel no produce error con los nuevos tipos.
