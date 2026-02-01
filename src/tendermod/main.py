from langchain_community.document_loaders import PyMuPDFLoader
from openai import OpenAI
from tendermod.config.settings import OPENAI_API_KEY

from tendermod.data_sources.redneet_db.sql_agent import build_company_sql_agent
from tendermod.data_sources.redneet_db.xls_loader import load_db
from tendermod.evaluation.compare_indicators import indicators_comparation
from tendermod.evaluation.indicators_inference import get_general_info, get_indicators
from tendermod.ingestion.ingestion_experience_flow import ingest_experience_data
from tendermod.ingestion.db_loader import get_specific_gold_indicator
from tendermod.ingestion.ingestion_flow import ingest_documents
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.ingestion.chunking import chunk_docs


from tendermod.config.settings import CHROMA_PERSIST_DIR
from pathlib import Path
import shutil
from dotenv import load_dotenv



def main():
    load_dotenv()
    print("\ntendermod running")

    #test_openai()

    """Enable only to ingest"""
    #ingest_documents()
    #load_db(tab_name="indicadores", file_name="rib.xlsx") # load from xls to db
    #load_db(tab_name="experiencia", file_name="experiencia_rup.xlsx") # load from xls to db

    """Enable only to test"""
    #query="Que experiencia se tiene cuyo objeto este relacionado con Obras electrica, solo entregame el objeto"
    #get_specific_gold_indicator(query)
    
    vs = ingest_experience_data() # Ingesta de datos
    res = vs.similarity_search("Equipos de red", k=10) # Validacion por similaridad
    for r in res: #Impresion de datos
        print(r.metadata["numero_rup"], r.metadata["cliente"], r.metadata["objeto"], r.metadata["valor"])
    #[print(r, "\n\n\n") for r in result]
    #raise Exception("Analiza!!!")


    """Enable only to consult"""
    

    #indicators_comparation()
    #print(f"Respuesta final:\n {response} \n")
    #print(f"Respuesta final:\n {response.answer[0].indicador} \n")
    
    """SQL Agent"""
    
    #get_specific_gold_indicator(f"valor de capital de trabajo")


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