from openai import OpenAI
from tendermod.config.settings import OPENAI_API_KEY
#from langchain.embeddings import OpenAIEmbeddings
from langchain_openai import OpenAIEmbeddings



def embed_docs():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=OPENAI_API_KEY)
    return embeddings