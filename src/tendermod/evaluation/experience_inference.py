


from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import run_llm_indices
from tendermod.evaluation.prompts import qna_system_message_experience, qna_user_message_experience
from tendermod.evaluation.schemas import ExperienceResponse
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever, create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore


def get_experience(user_input: str, k):
    

    # Load docs and chunking
    docs = load_docs()
    #chunks = []
    chunks = chunk_docs(docs)

    # Embeddings and vectorStore
    #vectorStore = create_vectorstore(chunks, embed_docs())
    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)

    retriever = create_retriever_experience(vectorStore, k)
    #print(f"\n --- --- --- --- El vector store tiene {vectorStore._collection.count()} registros")

    # Evaluation
    #before = vectorStore._collection.count()
    #print(f"Count before retriever is {before}")
    context_for_query = build_context(retriever, chunks, user_input, k=k )
    #after = vectorStore._collection.count()
    #print(f"Context_for_query is: \n{context_for_query}")
    user_message = qna_user_message_experience
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)


    #print(f"Context for query: \n {context_for_query}")
    #print(f"User message: \n {user_message}")

    llm_response =  run_llm_indices(qna_system_message_experience, 
                    user_message)

    # Parsing
    try:
            parsed_response = ExperienceResponse.model_validate_json(llm_response)

    except Exception as e:
            print(e)
            response = f'Sorry, I encountered the following error: \n {e}'
            return None
            #parsed_response = {"answer": [{"indicador": "Null", "valor": "Null"}]}

    return parsed_response
