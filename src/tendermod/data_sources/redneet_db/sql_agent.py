from openai import OpenAI
from dotenv import load_dotenv
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
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}")

    # Initialize a SQL agent to interact with the customer database using the LLM
    
    
    db_agent = create_sql_agent(
        llm,
        db=db,
        agent_type="openai-tools",
        verbose=True
    )