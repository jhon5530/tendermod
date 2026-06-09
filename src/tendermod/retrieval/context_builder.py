from tendermod.ingestion.chunking import wide_context


def build_context(retriever, relevant_document_chunks, user_input, back = -1, front = 3, k=5):
    
    #relevant_document_chunks = wide_context(relevant_document_chunks, retriever.get_relevant_documents(query=user_input,k=k))
    relevant_document_chunks = wide_context(relevant_document_chunks, retriever.invoke(user_input))
    #print("----- ------ ------ LLM Context ----- ------ ------ ")
    #print(f"Relevant Documents: {relevant_document_chunks[0]}")
    #print("----- ------ ------ LLM Context end ----- ------ ------ ")
    
    # Prepare the context for the model — incluir metadata de página para mejorar trazabilidad
    seen_contents = set()
    context_list = []
    for d in relevant_document_chunks:
        if d.page_content not in seen_contents:
            seen_contents.add(d.page_content)
            page = d.metadata.get("page", "")
            chapter = d.metadata.get("chapter_title", "")
            if page != "":
                page_label = f"[Página {page + 1}"
                if chapter:
                    page_label += f" — {chapter[:50]}"
                page_label += "] "
            else:
                page_label = ""
            context_list.append(page_label + d.page_content)

    context_for_query = ". ".join(context_list)

    return context_for_query