import os
import glob
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg2.extras import execute_values
from app.db import get_connection
from app.safety import sanitize

# splits long text into ~1000 character pieces with 150 characters of overlap
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def ingest_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    conn = get_connection()
    cur = conn.cursor()

    # skip the file if it was already ingested
    cur.execute("SELECT id FROM documents WHERE filename = %s", (filename,))
    if cur.fetchone():
        print(f"Skipping {filename} (already ingested)")
        cur.close()
        conn.close()
        return 0

    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)

    # save the document and get its id back
    cur.execute(
        "INSERT INTO documents (filename, num_pages) VALUES (%s, %s) RETURNING id",
        (filename, num_pages),
    )
    document_id = cur.fetchone()[0]

    # go page by page, split each page into chunks
    rows = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.replace("\x00", "")  # Postgres cannot store null characters
        for piece in splitter.split_text(text):
            cleaned, trust, reasons = sanitize(piece)
            rows.append((document_id, page_number, cleaned, trust))

    # insert all chunks in one go (much faster than one by one)
    execute_values(
        cur,
        "INSERT INTO chunks (document_id, page_number, chunk_text, trust_score) VALUES %s",
        rows,
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"{filename}: {num_pages} pages, {len(rows)} chunks")
    return len(rows)


if __name__ == "__main__":
    total_chunks = 0
    for path in sorted(glob.glob("data/pdfs/*.pdf")):
        total_chunks += ingest_pdf(path)
    print(f"Done. New chunks added: {total_chunks}")