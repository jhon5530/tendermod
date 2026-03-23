from dotenv import load_dotenv
import os
from pathlib import Path

# Cargar .env desde la raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ENV = os.getenv("ENV", "local")


def _resolve_path(env_key: str, default: Path) -> str:
    raw = os.getenv(env_key)
    if not raw:
        return str(default)
    p = Path(raw)
    return str(p if p.is_absolute() else ROOT_DIR / p)


CHROMA_PERSIST_DIR = _resolve_path("CHROMA_PERSIST_DIR", ROOT_DIR / "data" / "chroma")
CHROMA_EXPERIENCE_PERSIST_DIR = _resolve_path("CHROMA_EXPERIENCE_PERSIST_DIR", ROOT_DIR / "data" / "chroma_experience")
REDNEET_DB_PERSIST_DIR = _resolve_path("REDNEET_DB_PERSIST_DIR", ROOT_DIR / "data" / "redneet_db")