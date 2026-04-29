from tendermod.config.settings import CHROMA_PERSIST_DIR
from langchain_chroma import Chroma
from chromadb.api.shared_system_client import SharedSystemClient
import shutil
from pathlib import Path
from dotenv import load_dotenv


def create_vectorstore(document_chunks, embeddings, path=CHROMA_PERSIST_DIR):
    delete_current_vectorStore(path)
    # SharedSystemClient caches System instances keyed by persist_directory.
    # After shutil.rmtree() the cached System still holds the old Rust/SQLite
    # connection; the next PersistentClient call re-uses it and gets
    # SQLITE_CANTOPEN (code 14) or SQLITE_READONLY_CANTINIT (code 1032).
    # clear_system_cache() resets the dict so the next call creates a fresh System.
    SharedSystemClient.clear_system_cache()
    vectorstore = Chroma.from_documents(
        documents=document_chunks,
        embedding=embeddings,
        persist_directory=path
    )
    return vectorstore


def create_vectorstor_from_text(document_chunks, embeddings, path=CHROMA_PERSIST_DIR):
    delete_current_vectorStore(path)
    SharedSystemClient.clear_system_cache()

    ids = [str(d.metadata["numero_rup"]) for d in document_chunks]

    vectorstore = Chroma(
        collection_name="rup",
        embedding_function=embeddings,
        persist_directory=path,
        collection_metadata={"hnsw:space": "cosine"},
    )
    vectorstore.add_documents(document_chunks, ids=ids)
    return vectorstore


def delete_current_vectorStore(path=CHROMA_PERSIST_DIR):
    chroma_path = Path(path)
    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        print("Chroma DB eliminada correctamente")
    else:
        print("Chroma DB no existe")


def read_vectorstore(embeddings, path=CHROMA_PERSIST_DIR, collection_name=None):
    """
    Lee un vectorstore persistido en `path`.

    - Si `collection_name` es None, usa la colección default de Chroma.
    - Pasar `collection_name="rup"` para leer la colección de experiencia
      creada por `create_vectorstor_from_text()`.
    """
    kwargs = {
        "persist_directory": path,
        "embedding_function": embeddings,
    }
    if collection_name:
        kwargs["collection_name"] = collection_name
    return Chroma(**kwargs)
