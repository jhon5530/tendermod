# Spec 16 — Mejoras de efectividad y precisión

## Contexto

Tras completar las Fases 1 y 2 de trazabilidad (chunk overlap, metadata de página/capítulo, campos `citation_verified`/`confidence`, mejora de modelos LLM), el análisis del codebase revela un segundo conjunto de mejoras concretas. Algunas ya tienen infraestructura hecha pero no expuesta al usuario (`citation_verified` y `confidence` se calculan pero son invisibles). Otras son bugs silenciosos que afectan la precisión de la evaluación.

---

## TODO-LIST

### TIER 1 — Correcciones puntuales (< 1 día total)

- [x] **1. SQL Agent: system prompt de dominio**
  - Archivo: `src/tendermod/data_sources/redneet_db/sql_agent.py`
  - Añadir `prefix=` a `create_sql_agent()`: "Consultas KPIs financieros en COP. Retorna solo valores numéricos o NULL. Nunca inventes columnas."

- [x] **2. `extract_compliance_bool`: regex más robusto**
  - Archivo: `src/tendermod/evaluation/compare_indicators.py`
  - Buscar "No cumple" ANTES de "Cumple". Retornar `None` si ambos están presentes.

- [x] **3. SMMLV dinámico por año**
  - Archivo: `src/tendermod/evaluation/compare_experience.py`
  - Reemplazar `SMMLV_2026 = 1_423_500` por dict `SMMLV_BY_YEAR` + función `get_current_smmlv()`.
  - Actualizar: editar este dict cada diciembre con el valor oficial del año siguiente.

- [x] **4. Team Query Builder: búsqueda case-insensitive**
  - Archivo: `src/tendermod/data_sources/redneet_db/team_query_builder.py`
  - Cambiar `LIKE ?` → `LOWER(campo) LIKE LOWER(?)` en filtros de certificación y categoría.

- [x] **5. ChromaDB experience: cap del k_dinámico**
  - Archivo: `src/tendermod/evaluation/compare_experience.py`
  - `k_dinamico = min(total_docs, max(200, len(rups_candidatos_codigos) * 10))`

### TIER 2 — Visibilidad de calidad (1-2 días)

- [x] **6. Mostrar `confidence` y `citation_verified` en resultados HTML + Excel**
  - Archivos: `web/apps/analysis/views.py`, `web/templates/analysis/results.html`
  - View: pasar campos al contexto del template
  - Template: badge de confianza por colores (verde ≥0.8, amarillo 0.5–0.8, gris <0.5) + ícono de cita verificada
  - Excel hoja "Checklist General": añadir columnas `Confianza` y `Cita Verificada`

- [x] **7. Expandir checklist HTML con campos ocultos**
  - Archivo: `web/templates/analysis/results.html`
  - Añadir bloque colapsable (Bootstrap collapse) por requisito con: `extracto_pliego`, `seccion`, `documento_formato`, `obligatorio`

- [x] **8. Tabla de desglose de indicadores en resultados HTML**
  - Archivo: `web/templates/analysis/results.html`
  - Usar `indicators_detalle` (ya existe en `IndicatorComplianceResult`) para renderizar tabla: `Indicador | Valor Empresa | Condición | Umbral | Cumple`

### TIER 3 — Robustez de prompts (1-2 días)

- [x] **9. Prompts de indicadores: few-shot examples + regla de decimales**
  - Archivo: `src/tendermod/evaluation/prompts.py`
  - Añadir 2-3 ejemplos JSON al final de `qna_system_message_indices`
  - Regla explícita: el pliego puede usar coma ("1,13") pero el output JSON usa siempre punto ("1.13")

- [x] **10. `basic_comparation_system_prompt`: manejo de `valor_empresa = None`**
  - Archivo: `src/tendermod/evaluation/prompts.py`
  - Añadir instrucción: "Si `valor_empresa` es null, el indicador no es evaluable. No penalices al proponente por datos faltantes del sistema."

- [x] **11. `auto.html`: timeout en polling**
  - Archivo: `web/templates/analysis/auto.html`
  - Añadir timeout de 10 minutos con mensaje: "El análisis está tardando. Puedes cerrar esta página — el resultado se guardará cuando termine."

---

## Archivos afectados

| Archivo | Items |
|---------|-------|
| `src/tendermod/data_sources/redneet_db/sql_agent.py` | 1 |
| `src/tendermod/evaluation/compare_indicators.py` | 2 |
| `src/tendermod/evaluation/compare_experience.py` | 3, 5 |
| `src/tendermod/data_sources/redneet_db/team_query_builder.py` | 4 |
| `web/apps/analysis/views.py` | 6 |
| `web/templates/analysis/results.html` | 6, 7, 8 |
| `src/tendermod/evaluation/prompts.py` | 9, 10 |
| `web/templates/analysis/auto.html` | 11 |

---

## Verificación

- Correr análisis completo con un pliego real y verificar:
  - Checklist muestra badges de confianza y citas verificadas
  - Tabla de indicadores muestra desglose estructurado (valor empresa vs umbral)
  - Excel exportado incluye columnas `Confianza` y `Cita Verificada`
  - Búsqueda de certificación en minúsculas retorna resultados
  - SMMLV se resuelve dinámicamente por año
  - Auto-eval muestra timeout si la tarea se cuelga
