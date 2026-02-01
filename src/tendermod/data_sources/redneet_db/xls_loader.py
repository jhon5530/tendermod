import pandas as pd
import sqlite3
from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
import os


def load_db(tab_name, file_name):
    db_path = os.path.join(
        REDNEET_DB_PERSIST_DIR,
        "redneet_database.db"
    )
    conn = sqlite3.connect(db_path)

    # 2. Read all sheets into a dict of DataFrames
    excel_path = os.path.join(
        REDNEET_DB_PERSIST_DIR,
        file_name
    )
    excel_data = pd.read_excel(excel_path, sheet_name=None)

    # 3. Loop over each sheet
    for sheet_name, df in excel_data.items():
        title = df.columns[0]
        print(f"Processing sheet: {sheet_name}, first column: {title}")

        # Save to database
        df.to_sql(name=tab_name, con=conn, if_exists="replace", index=False)

    # 4. Commit and close
    conn.commit()
    conn.close()

    print("Data successfully transferred from Excel to my_database.db!")
