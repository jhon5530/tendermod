# Manual de Despliegue — Linux (Ubuntu / Debian)

## Requisitos previos

| Componente | Versión mínima |
|---|---|
| Python | 3.12 |
| Poetry | 1.8+ |
| Git | cualquiera |
| Redis | 7+ |
| Tesseract OCR | 5+ |

---

## Paso 1 — Instalar dependencias del sistema

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.12
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Redis
sudo apt install -y redis-server

# Tesseract con idioma español
sudo apt install -y tesseract-ocr tesseract-ocr-spa

# Dependencias de compilación (necesarias para algunos paquetes Python)
sudo apt install -y build-essential git curl
```

Verificar versiones:
```bash
python3.12 --version
redis-cli ping        # debe responder: PONG
tesseract --version
```

---

## Paso 2 — Instalar Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
# Agregar al PATH (agregar al ~/.bashrc o ~/.zshrc para que persista)
export PATH="$HOME/.local/bin:$PATH"

# Verificar
poetry --version
```

---

## Paso 3 — Clonar el repositorio

```bash
git clone <URL_DEL_REPO> tendermod
cd tendermod
```

---

## Paso 4 — Configurar variables de entorno

Crea el archivo `.env` en la raíz del proyecto (mismo nivel que `pyproject.toml`):

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-...tu-clave-aqui...
CHROMA_PERSIST_DIR=./data/chroma
CHROMA_EXPERIENCE_PERSIST_DIR=./data/chroma_experience
REDNEET_DB_PERSIST_DIR=./data/redneet_db
ENV=local
EOF
```

---

## Paso 5 — Instalar dependencias Python

```bash
# Dependencias del backend (tendermod)
poetry install

# Dependencias del frontend Django
poetry run pip install -r web/requirements.txt
```

---

## Paso 6 — Preparar datos iniciales

Coloca los archivos Excel en `data/redneet_db/`:
- `rib.xlsx` — indicadores financieros de la empresa
- `experiencia_rup.xlsx` — experiencia RUP de la empresa

Crea las carpetas necesarias:

```bash
mkdir -p data/chroma data/chroma_experience data/ocr
```

---

## Paso 7 — Migraciones Django

```bash
cd web
poetry run python manage.py migrate
cd ..
```

---

## Paso 8 — Levantar los tres servicios

Abre **3 terminales** separadas. Desde la raíz del proyecto en cada una:

**Terminal 1 — Redis:**
```bash
sudo service redis-server start
# o en distribuciones con systemd:
sudo systemctl start redis
```

**Terminal 2 — Django (servidor web):**
```bash
cd web
poetry run python manage.py runserver
```
Accede en el navegador: http://127.0.0.1:8000

**Terminal 3 — Celery (tareas en background):**
```bash
cd web
poetry run celery -A tendermod_web worker --loglevel=info
```

---

## Estructura de carpetas esperada

```
tendermod/
├── .env                        ← creado en Paso 4
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

## Iniciar automáticamente con systemd (opcional)

Para que Redis y los servicios inicien al arrancar el servidor:

**Redis:**
```bash
sudo systemctl enable redis
sudo systemctl start redis
```

**Celery** — crea `/etc/systemd/system/tendermod-celery.service`:
```ini
[Unit]
Description=Tendermod Celery Worker
After=network.target redis.service

[Service]
User=<tu-usuario>
WorkingDirectory=/ruta/al/proyecto/web
ExecStart=/ruta/al/proyecto/.venv/bin/celery -A tendermod_web worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tendermod-celery
sudo systemctl start tendermod-celery
```

---

## Solución de problemas comunes

| Error | Causa | Solución |
|---|---|---|
| `redis.exceptions.ConnectionError` | Redis no está corriendo | `sudo systemctl start redis` |
| `tesseract is not installed` | Tesseract no instalado | `sudo apt install tesseract-ocr tesseract-ocr-spa` |
| `OPENAI_API_KEY not found` | Falta `.env` | Verificar que `.env` existe en la raíz del proyecto |
| `No module named 'tendermod'` | Poetry no activo | Usar `poetry run` antes de cada comando |
| Permiso denegado en `data/` | Permisos de carpeta | `chmod -R 755 data/` |
