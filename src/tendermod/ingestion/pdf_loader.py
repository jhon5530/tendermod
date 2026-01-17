from glob import glob
from langchain_community.document_loaders import PyMuPDFLoader
from tendermod.config.settings import ROOT_DIR

def load_docs():
    all_documents = []
    #pdf_files = glob(str(ROOT_DIR / "data" / "pdf" / "*.pdf"))
    pdf_files = glob(str(ROOT_DIR / "data" / "*.pdf"))
    print (f"Los archivos a leer son: {pdf_files}")
    for pdf_file in pdf_files:
        loader = PyMuPDFLoader(pdf_file)
        documents = loader.load()
        all_documents.extend(documents)
    return all_documents

