from tendermod.ingestion.pdf_loader import load_docs
from tendermod.ingestion.chunking import chunk_docs
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import create_vectorstore

def ingest_documents():
    print("Ingesting Documents\n")

    # Load docs and chunking
    docs = load_docs()
    chunks = chunk_docs(docs)

    # Embeddings and vectorStore
    vectorStore = create_vectorstore(chunks, embed_docs())
    #vectorStore.persist()
    
    return vectorStore 
    