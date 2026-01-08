from langchain_community.document_loaders import PyMuPDFLoader
from openai import OpenAI
from tendermod.config.settings import OPENAI_API_KEY



def main():
    print("\ntendermod running")
    print("API KEY loaded:", bool(OPENAI_API_KEY))
    test_openai()


def test_openai():
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hola, estas operando?"}]
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()