
from tendermod.data_sources.redneet_db.sql_agent import build_company_sql_agent


def get_specific_gold_indicator(query: str):
    return build_company_sql_agent().invoke(query)
