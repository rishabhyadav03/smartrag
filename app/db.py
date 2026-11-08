import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # reads the .env file


def get_connection():
    # opens a connection to the Render Postgres database
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    # one row per uploaded PDF
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            num_pages INTEGER
        )
    """)

    # one row per chunk of text
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER REFERENCES documents(id),
            page_number INTEGER,
            chunk_text TEXT NOT NULL,
            trust_score REAL DEFAULT 1.0
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Tables created")


if __name__ == "__main__":
    create_tables()