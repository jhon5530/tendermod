



from chromadb.api.types import Document
from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
from tendermod.ingestion.experience_db_loader import ingest_and_chunk
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import create_vectorstor_from_text, create_vectorstore


def ingest_experience_data():
    print("Ingesting Experience from db\n")

    # Load docs and chunking
    chunks = ingest_and_chunk()

    # Embeddings and vectorStore
    vectorStore = create_vectorstor_from_text(chunks, embed_docs(), path=CHROMA_EXPERIENCE_PERSIST_DIR)
    
    print("Vectorstore creada con exito")

    return vectorStore
    
    