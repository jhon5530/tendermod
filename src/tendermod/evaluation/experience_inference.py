


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
    context_for_query = build_context(retriever, chunks, user_input, k=k)

    # Segunda búsqueda dirigida para capturar sub-requisitos de experiencia específica
    # (patrón "al menos un contrato con X" que puede estar en chunks distintos a la sección general)
    specific_query = "experiencia específica al menos un contrato"
    context_specific = build_context(retriever, chunks, specific_query, k=5)
    if context_specific:
        # Deduplicar a nivel de fragmentos individuales (no comparación de string completo)
        existing_fragments = set(
            fragment.strip()
            for fragment in context_for_query.split(". ")
            if fragment.strip()
        )
        new_fragments = [
            fragment
            for fragment in context_specific.split(". ")
            if fragment.strip() and fragment.strip() not in existing_fragments
        ]
        if new_fragments:
            context_for_query = (
                context_for_query
                + "\n\n--- Sección de Experiencia Específica ---\n"
                + ". ".join(new_fragments)
            )

    #after = vectorStore._collection.count()
    #print(f"Context_for_query is: \n{context_for_query}")
    user_message = qna_user_message_experience
    user_message = user_message.replace('{context}', context_for_query)
    user_message = user_message.replace('{question}', user_input)


    #print(f"Context for query: \n {context_for_query}")
    #print(f"User message: \n {user_message}")

    llm_response =  run_llm_indices(qna_system_message_experience,
                    user_message)

    if "sorry" in llm_response.lower():
        print("[get_experience] El retriever no encontró contexto de experiencia relevante")
        return None, ""

    # Parsing
    try:
            parsed_response = ExperienceResponse.model_validate_json(llm_response)

    except Exception as e:
            print(e)
            response = f'Sorry, I encountered the following error: \n {e}'
            return None, ""
            #parsed_response = {"answer": [{"indicador": "Null", "valor": "Null"}]}

    return parsed_response, context_for_query
