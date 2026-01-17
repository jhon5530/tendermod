from langchain_community.document_loaders import PyMuPDFLoader
from openai import OpenAI
from tendermod.config.settings import OPENAI_API_KEY
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.ingestion.chunking import chunk_docs
from tendermod.evaluation.indicators_compliance import evaluate_indicators_compliance
from tendermod.config.settings import CHROMA_PERSIST_DIR
from pathlib import Path
import shutil


def main():
    print("\ntendermod running")

    #test_openai()
    indicators_routine()


def indicators_routine():
    user_input = "Cuales los indicadores financieros como: Rentabilidades, capacidades, endeudamiento, indices"
    k = 5
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