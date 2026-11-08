import json
import random
import time
from app.db import get_connection
from app.llm import llm

PER_DOC = 8
random.seed(42)  # same random picks every time we run it

PROMPT = (
    "Write ONE question that can be answered using only the passage below. "
    "Rules: do not copy rare words or phrases from the passage, rephrase them. "
    "The question must make sense on its own, so never say 'the passage' or 'the text'. "
    "Reply with only the question.\n\nPassage:\n"
)


def load_rows():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.document_id, d.filename, c.page_number, c.chunk_text
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        ORDER BY c.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def looks_good(text):
    # keep long chunks that are mostly letters (skips tables and reference lists)
    if len(text) < 600:
        return False
    letters = sum(ch.isalpha() or ch == " " for ch in text)
    return letters / len(text) > 0.85


rows = load_rows()

# group chunks by document
by_document = {}
for row in rows:
    by_document.setdefault(row[1], []).append(row)

queries = []
for document_id, doc_rows in by_document.items():
    good_rows = [r for r in doc_rows if looks_good(r[4])]
    picked = random.sample(good_rows, min(PER_DOC, len(good_rows)))

    for chunk_id, doc_id, filename, page, text in picked:
        response = llm.invoke([("human", PROMPT + text)])
        question = response.content.strip()
        queries.append(
            {
                "question": question,
                "document_id": doc_id,
                "filename": filename,
                "page": page,
                "gold_chunk_id": chunk_id,
                "passage": text,
            }
        )
        print(f"{filename} page {page}: {question}")
        time.sleep(1)  # be gentle with the free API limits

with open("eval/queries.json", "w", encoding="utf-8") as f:
    json.dump(queries, f, indent=2, ensure_ascii=False)

print(f"\nSaved {len(queries)} draft questions to eval/queries.json")