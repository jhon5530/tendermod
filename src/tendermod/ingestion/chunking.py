from langchain_text_splitters import RecursiveCharacterTextSplitter
import copy



def chunk_docs(docs):
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name='cl100k_base',                                                # Encoding used by popular LLMs
    chunk_size=512,                                                             # Each chunk will have up to 512 character
    #chunk_overlap=50
    )

    document_chunks = text_splitter.split_documents(docs)

    for i, chunk in enumerate(document_chunks):
        chunk.metadata["chunk_id"] = i

    return document_chunks

""" Funcion to wide the context window from -1 chunk to +2 chunks"""
def wide_context(document_chunks, relevant_document_chunks, back = -2, front = 3):
    
    chunk_list = []
    for chunk in relevant_document_chunks:
        chunk_number = chunk.metadata["chunk_id"]
        print (f"chunk_number included {chunk_number}")
        chunk_list.append(chunk_number)

    #OPC 2
    print (f"Cantidad de chunks {len(chunk_list)}")
    initial_idx = chunk_list[0] + back
    if initial_idx < 0:
        initial_idx = chunk_list[0]
    wcc = copy.deepcopy(document_chunks[initial_idx])

    seen_ids = set()
    seen_ids.add(initial_idx)

    for cn in chunk_list:
        for offset_idx in [cn+back+1, cn, cn+front-2, cn+front-1, cn+front]:
            if offset_idx < 0 or offset_idx >= len(document_chunks):
                continue
            if offset_idx in seen_ids:
                continue
            seen_ids.add(offset_idx)
            wcc.page_content = wcc.page_content + document_chunks[offset_idx].page_content

    return [wcc]