import logging

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import run_llm_general_requirements, run_llm_indices
from tendermod.evaluation.prompts import (
    PLIEGO_QA_SYSTEM_PROMPT,
    qna_user_message_pliego_qa,
)
from tendermod.evaluation.schemas import GeneralRequirementList
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore
from tendermod.retrieval.context_builder import build_context

logger = logging.getLogger(__name__)

HABILITANTES_QUERIES: list[str] = [
    # --- JURÍDICOS (4.1.1.x) ---
    "carta presentación propuesta firma representante legal declaración juramento",
    "certificado existencia representación legal cámara comercio objeto social",
    "documento identificación cédula ciudadanía representante legal",
    "constitución consorcio unión temporal porcentaje participación integrantes",
    "registro único proponentes RUP inscripción vigente firme",
    "registro único tributario RUT DIAN",
    "garantía seriedad oferta póliza valor presupuesto oficial",
    "certificación pagos seguridad social parafiscales aportes salud pensión ARL SENA ICBF",
    "antecedentes fiscales contraloría general república boletín responsables",
    "antecedentes disciplinarios procuraduría SIRI sistema información sanciones",
    "antecedentes judiciales policía nacional ministerio defensa",
    "medidas correctivas registro nacional código nacional policía convivencia",
    "deudores alimentarios morosos REDAM",
    "compromiso anticorrupción transparencia ética pública",
    "autorización notificación electrónica comunicaciones",
    "acuerdo confidencialidad información reservada",
    "lavado activos financiación terrorismo prevención verificación participación accionaria",
    "poder apoderado facultades suscribir presentación personal",
    "habeas data autorización tratamiento datos personales Ley 1581",
    "firma transaccional SECOP plataforma electrónica suscripción contrato",
    # --- TÉCNICOS (4.1.2.x) ---
    "certificación fabricante distribuidor partner canal autorizado solución",
    "manifestación aceptación requerimientos mínimos obligatorios anexo técnico",
    "personal mínimo requerido perfiles profesional especialista tecnólogo experiencia certificaciones",
    "experiencia general específica habilitante contratos UNSPSC clasificador bienes servicios",
]

_QA_QUERY = (
    "requisitos habilitantes jurídicos técnicos documentación capacidad financieros del pliego"
)

# Expansión de vecinos por chunk recuperado (igual que wide_context)
_NEIGHBOR_BACK = 2
_NEIGHBOR_FRONT = 3


def get_general_requirements(k: int = 3) -> GeneralRequirementList:
    docs = load_docs()
    all_chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k=k)

    # Deduplicar recuperaciones por chunk_id exacto, no por texto
    retrieved_ids: set[int] = set()
    for query in HABILITANTES_QUERIES:
        for doc in retriever.invoke(query):
            cid = doc.metadata.get("chunk_id")
            if cid is not None:
                retrieved_ids.add(cid)

    if not retrieved_ids:
        logger.warning("[get_general_requirements] No se recuperaron chunks del vectorstore")
        return GeneralRequirementList(requisitos=[])

    # Expandir vecinos y ordenar por posición en el documento
    expanded: set[int] = set()
    for cid in retrieved_ids:
        for offset in range(-_NEIGHBOR_BACK, _NEIGHBOR_FRONT + 1):
            neighbor = cid + offset
            if 0 <= neighbor < len(all_chunks):
                expanded.add(neighbor)

    context_parts = [all_chunks[i].page_content for i in sorted(expanded)]
    combined_context = "\n".join(context_parts)

    logger.info(
        "[get_general_requirements] %d queries → %d chunks únicos → %d con vecinos → %d chars (~%d tokens)",
        len(HABILITANTES_QUERIES),
        len(retrieved_ids),
        len(expanded),
        len(combined_context),
        len(combined_context) // 4,
    )

    try:
        parsed = run_llm_general_requirements(combined_context, _QA_QUERY)
    except Exception as e:
        logger.error("[get_general_requirements] Error llamando LLM: %s", e)
        return GeneralRequirementList(requisitos=[])

    logger.info("[get_general_requirements] Extraidos %d requisitos", len(parsed.requisitos))
    return parsed


def ask_pliego(question: str, k: int = 8) -> str:
    """Responde preguntas en lenguaje natural sobre el pliego. Retorna string."""
    docs = load_docs()
    chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k)

    context_for_query = build_context(retriever, chunks, question, k=k)

    user_message = qna_user_message_pliego_qa
    user_message = user_message.replace("{context}", context_for_query)
    user_message = user_message.replace("{question}", question)

    response = run_llm_indices(PLIEGO_QA_SYSTEM_PROMPT, user_message)
    return response
