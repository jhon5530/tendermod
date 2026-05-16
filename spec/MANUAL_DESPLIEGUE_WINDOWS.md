# Manual de Despliegue — Windows

## Requisitos previos

| Componente | Versión mínima | Descarga |
|---|---|---|
| Python | 3.12 | https://www.python.org/downloads/ |
| Poetry | 1.8+ | https://python-poetry.org/docs/#installation |
| Git | cualquiera | https://git-scm.com/download/win |
| Redis (via WSL2) | 7+ | ver paso 3 |
| Tesseract OCR | 5+ | https://github.com/UB-Mannheim/tesseract/wiki |

> Redis no tiene distribución nativa para Windows. La forma recomendada es instalarlo dentro de WSL2 (Windows Subsystem for Linux).

---

## Paso 1 — Clonar el repositorio

```powershell
git clone <URL_DEL_REPO> tendermod
cd tendermod
```

---

## Paso 2 — Configurar variables de entorno

Crea el archivo `.env` en la raíz del proyecto (mismo nivel que `pyproject.toml`):

```env
OPENAI_API_KEY=sk-...tu-clave-aqui...
CHROMA_PERSIST_DIR=./data/chroma
CHROMA_EXPERIENCE_PERSIST_DIR=./data/chroma_experience
REDNEET_DB_PERSIST_DIR=./data/redneet_db
ENV=local
```

---

## Paso 3 — Instalar y levantar Redis en WSL2

Abre una terminal de WSL2 (Ubuntu) y ejecuta:

```bash
sudo apt update && sudo apt install -y redis-server
sudo service redis-server start
# Verificar que corre
redis-cli ping   # debe responder: PONG
```

Deja esta terminal abierta. Redis debe estar corriendo antes de iniciar Celery.

---

## Paso 4 — Instalar Tesseract OCR

1. Descargar el instalador de https://github.com/UB-Mannheim/tesseract/wiki
2. Ejecutar el instalador. Durante la instalación:
   - Marcar **"Additional language data"** → seleccionar **Spanish**
3. Agregar Tesseract al PATH del sistema:
   - `C:\Program Files\Tesseract-OCR` (o donde se instaló)
4. Verificar en PowerShell:

```powershell
tesseract --version
```

---

## Paso 5 — Instalar dependencias Python

En PowerShell, desde la raíz del proyecto:

```powershell
# Instalar dependencias del backend (tendermod)
poetry install

# Instalar dependencias del frontend Django
poetry run pip install -r web/requirements.txt
```

---

## Paso 6 — Preparar datos iniciales

Coloca los archivos Excel en `data/redneet_db/`:
- `rib.xlsx` — indicadores financieros de la empresa
- `experiencia_rup.xlsx` — experiencia RUP de la empresa

Crea las carpetas necesarias (si no existen):

```powershell
mkdir data\chroma
mkdir data\chroma_experience
mkdir data\ocr
```

---

## Paso 7 — Migraciones Django

```powershell
cd web
poetry run python manage.py migrate
cd ..
```

---

## Paso 8 — Levantar los tres servicios

Abre **3 ventanas de PowerShell** separadas. Desde la raíz del proyecto en cada una:

**Ventana 1 — Django (servidor web):**
```powershell
cd web
poetry run python manage.py runserver
```
Accede en el navegador: http://127.0.0.1:8000

**Ventana 2 — Celery (tareas en background):**
```powershell
cd web
poetry run celery -A tendermod_web worker --loglevel=info --pool=solo
```
> En Windows, Celery requiere `--pool=solo` para funcionar correctamente.

**Ventana 3 — Redis (ya levantado en WSL2 — ver Paso 3).**

---

## Estructura de carpetas esperada

```
tendermod/
├── .env                        ← creado en Paso 2
├── pyproject.toml
├── data/
│   ├── chroma/                 ← se crea al ingestar el primer PDF
│   ├── chroma_experience/      ← se crea al ingestar experiencia
│   ├── ocr/                    ← se crea al procesar PDFs escaneados
│   └── redneet_db/
│       ├── rib.xlsx            ← colocar antes de iniciar
│       └── experiencia_rup.xlsx← colocar antes de iniciar
├── src/tendermod/
└── web/
```

---

## Flujo de uso

1. Abrir http://127.0.0.1:8000
2. Crear nueva sesión y subir el PDF de licitación
3. Esperar que termine la ingesta (barra de progreso)
4. Extraer experiencia, indicadores y requisitos generales
5. Continuar al Paso 2 para ver resultados y descargar Excel

---

## Solución de problemas comunes

| Error | Causa | Solución |
|---|---|---|
| `redis.exceptions.ConnectionError` | Redis no está corriendo | Iniciar Redis en WSL2: `sudo service redis-server start` |
| `Error: celery worker did not start` | Pool incorrecto | Usar `--pool=solo` en Windows |
| `tesseract is not installed` | Tesseract no en PATH | Agregar `C:\Program Files\Tesseract-OCR` al PATH del sistema |
| `OPENAI_API_KEY not found` | Falta `.env` | Verificar que `.env` existe en la raíz del proyecto |
| `No module named 'tendermod'` | Poetry no activo | Usar `poetry run` antes de cada comando |
