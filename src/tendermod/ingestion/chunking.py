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
    wcc = copy.deepcopy(document_chunks[chunk_list[0] + back])

    for cn in chunk_list:
        wcc.page_content = wcc.page_content + document_chunks[cn+back+1].page_content
        wcc.page_content = wcc.page_content + document_chunks[cn].page_content
        wcc.page_content = wcc.page_content + document_chunks[cn+front -2].page_content
        wcc.page_content = wcc.page_content + document_chunks[cn+front -1].page_content
        wcc.page_content = wcc.page_content + document_chunks[cn+front].page_content

    return [wcc]