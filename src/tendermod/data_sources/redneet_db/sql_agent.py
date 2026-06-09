from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent


#from langchain.agents import create_sql_agent
import os

from tendermod.config.settings import REDNEET_DB_PERSIST_DIR


def build_company_sql_agent():
    llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
    db_path = os.path.join(
        REDNEET_DB_PERSIST_DIR,
        "redneet_database.db"
    )

     #Defining a SQL Database object from custom_orders.db
    #db = SQLDatabase.from_uri("sqlite:////content/redneet_database.db")
    print("sqlite:////"+db_path)
    #db = SQLDatabase.from_uri("sqlite:/data/redneet_db/redneet_database.db")
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}", sample_rows_in_table_info=500)

    # Initialize a SQL agent to interact with the customer database using the LLM
    
    
    db_agent = create_sql_agent(
        llm,
        db=db,
        agent_type="openai-tools",
        verbose=False,
        top_k=500,
        prefix=(
            "Eres un agente SQL que consulta una base de datos SQLite con KPIs financieros "
            "y experiencia de una empresa colombiana. "
            "Reglas estrictas: (1) Retorna SOLO valores numéricos o NULL — nunca texto narrativo. "
            "(2) Nunca inventes columnas ni tablas que no existan en el esquema. "
            "(3) Los valores monetarios están en COP (pesos colombianos). "
            "(4) Si una columna no existe, retorna NULL para ese campo."
        ),
    )

    return db_agent


def build_team_sql_agent():
    """SQL Agent focalizado en las tablas personas y certificaciones del equipo."""
    llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
    db_path = os.path.join(REDNEET_DB_PERSIST_DIR, "redneet_database.db")
    db = SQLDatabase.from_uri(
        f"sqlite:///{db_path}",
        include_tables=["personas", "certificaciones"],
        sample_rows_in_table_info=30,
    )
    return create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=False, top_k=500)
