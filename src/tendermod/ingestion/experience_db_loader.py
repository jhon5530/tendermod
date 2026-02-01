#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea "chunks" (1 por registro) desde SQLite, usando solo:
- numero_rup/id  -> "NUMERO RUP"
- objeto         -> "OBJETO "  (nota: tiene espacio al final en tu DB)
- descripcion    -> "DESCRIPCION GENERAL"
- cliente        -> "CLIENTE"
- fecha          -> "FECHA FINALIZACION"
- valor          -> "VALOR"

Salida: JSONL (un objeto JSON por línea), listo para alimentar un RAG.
"""

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import os

from langchain_core.documents import Document

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR

DB_PATH = os.path.join(
        REDNEET_DB_PERSIST_DIR,
        "redneet_database.db"
    )
TABLE_NAME = "experiencia"
OUTPUT_JSONL = "experiencia_chunks.jsonl"


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _format_date(x: Any) -> Optional[str]:
    """
    Devuelve fecha en ISO8601 si se puede, o el string original si no.
    SQLite puede almacenar timestamps como texto/número; lo tratamos defensivamente.
    """
    if x is None:
        return None

    # Si ya viene como string
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        # Intento simple de parseo; si falla, regreso el string tal cual
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                pass
        return s

    # Si viene como número (epoch)
    if isinstance(x, (int, float)):
        try:
            return datetime.utcfromtimestamp(x).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return str(x)

    return _safe_str(x)


def build_chunk(record: Dict[str, Any]) -> Dict[str, Any]:
    numero_rup = record.get("NUMERO RUP")
    objeto = _normalize_whitespace(_safe_str(record.get("OBJETO")))
    descripcion = _normalize_whitespace(_safe_str(record.get("DESCRIPCION GENERAL")))
    cliente = _normalize_whitespace(_safe_str(record.get("CLIENTE")))
    fecha = _format_date(record.get("FECHA FINALIZACION"))

    # VALOR puede venir como float/int; lo dejamos como número si se puede
    valor_raw = record.get("VALOR")
    valor = None
    if valor_raw is not None:
        try:
            valor = float(valor_raw)
        except (TypeError, ValueError):
            valor = _safe_str(valor_raw)

    # Texto principal para embedding
    text_parts = [
        f"Cliente: {cliente}" if cliente else "",
        f"Objeto: {objeto}" if objeto else "",
        f"Descripción: {descripcion}" if descripcion else "",
        f"Fecha finalización: {fecha}" if fecha else "",
        f"Valor: {valor}" if valor is not None else "",
        f"Numero RUP: {numero_rup}" if numero_rup else "",
    ]
    text = _normalize_whitespace("\n".join([p for p in text_parts if p]))

    pc = build_page_content(cliente, objeto, descripcion, fecha, valor, numero_rup)


    chunk = {
        "id": numero_rup,  # úsalo como ID estable en tu RAG
        "metadata": {
            "numero_rup": numero_rup,
            "objeto": objeto,
            "descripcion": descripcion,
            "cliente": cliente,
            "fecha_finalizacion": fecha,
            "valor": valor,
        },
        "text": text,
        "page_content": pc,
    }


    return chunk

def build_page_content(cliente, objeto, descripcion, fecha, valor, numero_rup):
    return "\n".join([
        f"Cliente: {cliente}",
        f"Objeto: {objeto}",
        f"Descripción: {descripcion}",
        f"Fecha finalización: {fecha}",
        f"Valor: {valor}",
        f"Número RUP: {numero_rup}",
    ])

def ingest_and_chunk():
    

    db_path = DB_PATH
    

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = """
    SELECT
        "NUMERO RUP",
        "OBJETO",
        "DESCRIPCION GENERAL",
        "CLIENTE",
        "FECHA FINALIZACION",
        "VALOR"
    FROM experiencia
    WHERE "NUMERO RUP" IS NOT NULL
    """
    

    out_path = Path(OUTPUT_JSONL)
    n = 0
    result = []
    with out_path.open("w", encoding="utf-8") as f:
        for row in cur.execute(sql):
            record = dict(row)
            chunk = build_chunk(record)
            #print(chunk["page_content"])
            #raise Exception("!!!!!!")
            chunk_in_document = Document(
                page_content=chunk["page_content"],
                metadata=chunk["metadata"]
            )
            result.append(chunk_in_document)
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            n += 1

    conn.close()
    print(f"OK: exporté {n} chunks a {out_path.resolve()}")

    return result
    #return[item["text"] for item in result]
   



