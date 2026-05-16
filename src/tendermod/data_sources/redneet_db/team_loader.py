import logging
import sqlite3
from pathlib import Path

import pandas as pd

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR

logger = logging.getLogger(__name__)


def load_team_db(file_name: str) -> None:
    """Carga las hojas Personas y Certificaciones del Excel a SQLite."""
    db_path = Path(REDNEET_DB_PERSIST_DIR) / "redneet_database.db"
    file_path = Path(REDNEET_DB_PERSIST_DIR) / file_name

    logger.info("[team_loader] Leyendo %s", file_path)
    sheets = pd.read_excel(file_path, sheet_name=None)

    with sqlite3.connect(str(db_path)) as conn:
        if "Personas" in sheets:
            df = sheets["Personas"]
            df.to_sql("personas", conn, if_exists="replace", index=False)
            logger.info("[team_loader] Tabla 'personas' cargada: %d filas", len(df))
        else:
            logger.warning("[team_loader] Hoja 'Personas' no encontrada en %s", file_name)

        if "Certificaciones" in sheets:
            df = sheets["Certificaciones"]
            df.to_sql("certificaciones", conn, if_exists="replace", index=False)
            logger.info("[team_loader] Tabla 'certificaciones' cargada: %d filas", len(df))
        else:
            logger.warning("[team_loader] Hoja 'Certificaciones' no encontrada en %s", file_name)
