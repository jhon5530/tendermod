


from tendermod.evaluation.prompts import qna_system_message_indices, qna_user_message_indices
from tendermod.evaluation.schemas import MultipleIndicatorResponse
from tendermod.evaluation.llm_client import run_llm_indices
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.ingestion.chunking import chunk_docs, wide_context
from tendermod.retrieval.context_builder import build_context
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever
from tendermod.retrieval.vectorstore import create_vectorstore, read_vectorstore

def evaluate_indicators_compliance(user_input: str, k) -> MultipleIndicatorResponse:
    print("Evaluate_indicator_compliance\n")

    # Load docs and chunking
    docs = load_docs()
    #chunks = []
    chunks = chunk_docs(docs)

    # Embeddings and vectorStore
    #vectorStore = create_vectorstore(chunks, embed_docs())
    vectorStore = read_vectorstore(embed_docs())

    retriever = create_retriever(vectorStore, k)
    #print(f"\n --- --- --- --- El vector store tiene {vectorStore._collection.count()} registros")

    # Evaluation
    #before = vectorStore._collection.count()
    #print(f"Count before retriever is {before}")
    context_for_query = build_context(retriever, chunks, user_input, k=k )
    #after = vectorStore._collection.count()
    #print(f"Count after retriever is {after}")
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

    


    

    #prompt = COMPLIANCE_PROMPT.format(
    #    context=docs,
    #    question=user_input
    #)

    #raw_response = run_llm_indices(prompt)
    #parsed = MultipleIndicatorResponse.model_validate_json(raw_response)

    return None

    return parsed