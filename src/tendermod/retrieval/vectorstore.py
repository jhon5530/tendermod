from tendermod.config.settings import CHROMA_PERSIST_DIR
from langchain_chroma import Chroma
import shutil
from pathlib import Path
from dotenv import load_dotenv





def create_vectorstore(document_chunks, embeddings, path = CHROMA_PERSIST_DIR):

    delete_current_vectorStore(path)    
    vectorstore = Chroma.from_documents(
        documents=document_chunks,
        embedding=embeddings,
        persist_directory=path
    )
    
    return vectorstore

def create_vectorstor_from_text(document_chunks, embeddings, path = CHROMA_PERSIST_DIR):

    delete_current_vectorStore(path)    
    
    ids = [str(d.metadata["numero_rup"]) for d in document_chunks]

    vectorstore = Chroma(
        collection_name="rup",
        embedding_function=embeddings,
        persist_directory=path,
    )

    vectorstore.add_documents(document_chunks, ids=ids)
    #vectorstore.persist()
    
    return vectorstore

def delete_current_vectorStore(path = CHROMA_PERSIST_DIR):

    chroma_path = Path(path)
    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        print("Chroma DB eliminada correctamente")
    else:
        print("Chroma DB no existe")

def read_vectorstore(embeddings, path = CHROMA_PERSIST_DIR):
    vectorstore = Chroma(
    persist_directory=path,
    embedding_function=embeddings
    )

    return vectorstore
