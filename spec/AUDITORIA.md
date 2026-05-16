# Spec 13 — Framework de Auditoría tendermod vs Gold Standard

## Propósito

Comparar automáticamente los resultados de extracción de tendermod contra un "Gold Standard"
generado manualmente con Claude Cowork, para detectar:
- Gaps de cobertura (requisitos que tendermod no extrae)
- Ruido (requisitos extraídos por tendermod sin correspondencia en Gold)
- Precisión de indicadores financieros (nombres y umbrales)
- Efectividad y tiempos de extracción

---

## Prerequisitos

```bash
# 1. Activar entorno Poetry
source .venv/bin/activate

# 2. OPENAI_API_KEY debe estar en .env
cat .env | grep OPENAI_API_KEY

# 3. Verificar que openpyxl y numpy están disponibles
python -c "import openpyxl, numpy; print('OK')"
```

---

## Convención de nombres para Gold Standard Excel

Los archivos Gold Standard van en `GOLD EXAMPLES/` con **exactamente el mismo nombre** que el PDF
correspondiente, pero con extensión `.xlsx`:

```
GOLD EXAMPLES/
├── ANE - PLIEGO DE CONDICIONES.pdf
├── ANE - PLIEGO DE CONDICIONES.xlsx      ← Gold Standard
├── FNA test9.pdf
├── FNA test9.xlsx                         ← Gold Standard
└── ...
```

---

## Formato del Excel Gold Standard

El parser busca automáticamente las sheets por nombre (case-insensitive):

### Sheet `Requerimientos`

| Columna | Descripción |
|---------|-------------|
| `ID` | Número de requisito (opcional) |
| `Categoría` | Jurídico, Técnico, Documentación, Financiero, Experiencia, etc. |
| `Tipo` | Habilitante, Puntuable, Documental |
| `Sección Pliego` | Número de sección o numeral |
| `Requerimiento` | Nombre corto del requisito |
| `Descripción` | Texto completo — **usado para matching semántico** |
| `Documento / Formato Exigido` | Formato que debe presentarse (opcional) |

Columnas `Cumple`, `Observaciones` y similares se ignoran.

### Sheet `Indicadores`

Puede tener múltiples tablas. El parser detecta filas con:
- Primera celda = nombre del indicador (no vacía, no es encabezado)
- Al menos una celda con patrón de umbral: `≥ 1,13`, `≤ 0,84`, `>= 1.00`

Columnas relevantes: `Indicador`, `Fórmula`, `Umbral exigido`

### Sheet `Experiencia`

El parser extrae filas con nombre de segmento o actividad y valor en SMMLV.
Formato flexible — funciona con tablas de segmentos (como ciberseguridad) o requisitos narrativos.

---

## Comandos de ejecución

```bash
# Procesar todos los PDFs con Gold Standard disponible
python audit/run_audit.py --all

# Procesar un solo PDF
python audit/run_audit.py --pdf "GOLD EXAMPLES/ANE - PLIEGO DE CONDICIONES.pdf"

# Solo conteos, sin embeddings (más rápido, sin costo de API adicional)
python audit/run_audit.py --all --no-semantic

# Con logs detallados
python audit/run_audit.py --all 2>&1 | tee audit/audit_log.txt
```

### Tiempo estimado por PDF

| Modo | Tiempo aprox. |
|------|---------------|
| `--no-semantic` (solo extracción) | 2-5 min / PDF |
| Con semántico (`--all` normal) | 5-8 min / PDF |

El paso más lento es la ingesta + extracción de requisitos generales (LLM por capítulos).

---

## Archivos generados

Todos los reportes se guardan en `audit/`:

```
audit/
├── INFORME_AUDITORIA_2026-05-09_1430.md    ← informe narrativo
└── resultados_auditoria_2026-05-09_1430.xlsx  ← detalle por requisito
```

### Excel de resultados

Una sheet por PDF + sheet "Resumen". Cada fila tiene columna `Status`:

| Status | Color | Significado |
|--------|-------|-------------|
| `MATCHED` | Verde | Requisito Gold capturado por tendermod (score ≥ 0.78) |
| `GOLD_ONLY` | Rojo | Requisito Gold NO encontrado en tendermod — **gap** |
| `TM_ONLY` | Amarillo | Requisito tendermod sin match en Gold — posible ruido |

---

## Cómo interpretar las métricas

### Recall (cobertura)
`% de requisitos Gold capturados por tendermod`
- **Alto (>85%)**: tendermod extrae la mayoría de lo que Gold tiene. ✓
- **Bajo (<70%)**: hay categorías enteras que tendermod pierde — revisar prompts o keywords de capítulos.

### Precision (precisión)
`% de requisitos tendermod que tienen correspondencia en Gold`
- **Alto (>85%)**: tendermod no genera mucho ruido. ✓
- **Bajo (<70%)**: tendermod extrae cosas que Gold no considera requisitos — revisar criterios de extracción.

### F1 (balance)
Métrica principal. Penaliza tanto gaps como ruido. Objetivo: **F1 > 0.80**.

### Indicadores
Si el nombre del indicador no matchea (score < 0.85), tendermod lo está llamando diferente o no lo extrae.
Si el umbral difiere >5%, hay un bug de parseo o el LLM extrajo el valor incorrecto.

---

## Cuándo ejecutar

- **Después de cambios en `prompts.py`** (especialmente el prompt de extracción de requisitos generales)
- **Al agregar un nuevo Gold Standard** para un PDF no evaluado antes
- **Antes de un release** para verificar que no hay regresión en cobertura

---

## Solución de problemas

### "Sin Gold Standard para: XXX.pdf"
El archivo `.xlsx` no existe en `GOLD EXAMPLES/`. Verifica el nombre exacto (case-sensitive).

### Error en ingesta
El script restaura `data/` automáticamente aunque falle la ingesta. Si hay archivos en
`data/.audit_backup/`, el restore falló — muévalos manualmente de vuelta a `data/`.

### ChromaDB corrupto tras la auditoría
La auditoría modifica ChromaDB (es el comportamiento normal). Para restaurar el estado anterior,
re-ingesta el PDF de la sesión activa desde la interfaz web.
