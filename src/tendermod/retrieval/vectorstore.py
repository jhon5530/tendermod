from tendermod.config.settings import CHROMA_PERSIST_DIR
from langchain_chroma import Chroma
import shutil
from pathlib import Path
from dotenv import load_dotenv





def create_vectorstore(document_chunks, embeddings):

    delete_current_vectorStore()    
    vectorstore = Chroma.from_documents(
        documents=document_chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR
    )
    
    return vectorstore

def delete_current_vectorStore():

    chroma_path = Path(CHROMA_PERSIST_DIR)
    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        print("Chroma DB eliminada correctamente")
    else:
        print("Chroma DB no existe")

def read_vectorstore(embeddings):
    vectorstore = Chroma(
    persist_directory=CHROMA_PERSIST_DIR,
    embedding_function=embeddings
    )

    return vectorstore
