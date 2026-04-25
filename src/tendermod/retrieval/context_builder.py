from tendermod.ingestion.chunking import wide_context


def build_context(retriever, relevant_document_chunks, user_input, back = -1, front = 3, k=5):
    
    #relevant_document_chunks = wide_context(relevant_document_chunks, retriever.get_relevant_documents(query=user_input,k=k))
    relevant_document_chunks = wide_context(relevant_document_chunks, retriever.invoke(user_input))
    #print("----- ------ ------ LLM Context ----- ------ ------ ")
    #print(f"Relevant Documents: {relevant_document_chunks[0]}")
    #print("----- ------ ------ LLM Context end ----- ------ ------ ")
    
    # Prepare the context for the model — deduplicar por contenido como guardia defensiva
    seen_contents = set()
    context_list = []
    for d in relevant_document_chunks:
        if d.page_content not in seen_contents:
            seen_contents.add(d.page_content)
            context_list.append(d.page_content)

    context_for_query = ". ".join(context_list)

    return context_for_query