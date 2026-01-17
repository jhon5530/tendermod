from langchain_community.document_loaders import PyMuPDFLoader
from openai import OpenAI
from tendermod.config.settings import OPENAI_API_KEY

from tendermod.data_sources.redneet_db.sql_agent import build_company_sql_agent
from tendermod.data_sources.redneet_db.xls_loader import load_db
from tendermod.ingestion.ingestion_flow import ingest_documents
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.ingestion.chunking import chunk_docs
from tendermod.evaluation.indicators_compliance import evaluate_indicators_compliance
from tendermod.config.settings import CHROMA_PERSIST_DIR
from pathlib import Path
import shutil
from dotenv import load_dotenv



def main():
    load_dotenv()
    print("\ntendermod running")

    #test_openai()

    ### Enable only to ingest
    #ingest_documents()

    ###Enable only to consult
    #indicators_routine()
    
    ###
    #load_db()
    build_company_sql_agent()


def indicators_routine():
    user_input = "Cuales los indicadores financieros como: Rentabilidades, capacidades, endeudamiento, indices"
    u2ser_input = f"""
        Busca información específica sobre:
        - índice de liquidez
        - endeudamiento
        - cobertura de intereses
        - capital de trabajo

        Responde SOLO con base en el texto.
        """
    k = 2
    response = evaluate_indicators_compliance(user_input=user_input, k=k)
    print(f"Respuesta final:\n {response} \n")
    

def test_openai():
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hola, estas operando?"}]
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()