

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import run_llm_indices
from tendermod.evaluation.prompts import qna_general_info, qna_system_message_indices, qna_user_message_indices
from tendermod.evaluation.schemas import MultipleIndicatorResponse
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever
from tendermod.retrieval.vectorstore import read_vectorstore


def get_indicators(user_input: str, k) -> MultipleIndicatorResponse:
    

    # Load docs and chunking
    docs = load_docs()
    #chunks = []
    chunks = chunk_docs(docs)

    # Embeddings and vectorStore
    #vectorStore = create_vectorstore(chunks, embed_docs())
    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)

    retriever = create_retriever(vectorStore, k)
    #print(f"\n --- --- --- --- El vector store tiene {vectorStore._collection.count()} registros")

    # Evaluation
    #before = vectorStore._collection.count()
    #print(f"Count before retriever is {before}")
    context_for_query = build_context(retriever, chunks, user_input, k=k )
    #after = vectorStore._collection.count()
    #print(f"Context_for_query is: \n{context_for_query}")
    user_message = qna_user_message_indices
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)
    llm_response =  run_llm_indices(qna_system_message_indices, 
                    user_message)

    # Parsing
    try:
            parsed_response = MultipleIndicatorResponse.model_validate_json(llm_response)

    except Exception as e:
            print(e)
            parsed_response = {"answer": [{"indicador": "Null", "valor": "Null"}]}

    return parsed_response


def get_general_info(user_input: str, k) -> MultipleIndicatorResponse:
    print("Getting general Info\n")

    # Load docs and chunking
    docs = load_docs()
    chunks = chunk_docs(docs)


    vectorStore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever(vectorStore, k)
    context_for_query = build_context(retriever, chunks, user_input, k=k )

    user_message = qna_user_message_indices
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)
    llm_response =  run_llm_indices(qna_general_info, 
                    user_message)


    return llm_response