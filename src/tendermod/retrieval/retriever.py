



def create_retriever(vectorstore, k, lambda_mult=1.0):
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k,
            "fetch_k": 15,
            "lambda_mult": lambda_mult,
        }
    )
    return retriever



def create_retriever_experience(vectorstore, k):
    retriever = vectorstore.as_retriever(
        search_type='similarity',                                                   # Use similarity search (based on vector distance)
        search_kwargs={'k': k}                                                      # Retrieve top 5 most relevant documents
    )
    return retriever    
