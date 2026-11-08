import os
import time
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import date

import psutil
from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from pydantic import BaseModel

from app.db import get_connection
from app.ingest import ingest_pdf
from app.retrieval import Retriever
from app.llm import answer_question

ADMIN_KEY = os.getenv("ADMIN_KEY")
MAX_QUERIES_PER_DAY = 300

retriever = None
retriever_lock = threading.Lock()
queries_today = {"day": date.today(), "count": 0}


def get_retriever():
    global retriever
    with retriever_lock:
        if retriever is None:
            retriever = Retriever()
    return retriever


def warm_up():
    start = time.time()
    print("[startup] index build started", flush=True)
    try:
        get_retriever()
        memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        print(f"[startup] index ready in {time.time() - start:.0f}s, memory {memory_mb:.0f} MB", flush=True)
    except ValueError:
        print("[startup] no documents yet", flush=True)
    except Exception as error:
        print("[startup] index build failed:", error, flush=True)


@asynccontextmanager
async def lifespan(app):
    # build the search index in the background so the server starts quickly
    threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(title="SmartRAG", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str
    k: int = 4


@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    return {
        "memory_mb": round(memory_mb, 1),
        "index_ready": retriever is not None,
        "chunks": len(retriever.chunks) if retriever else 0,
    }


@app.get("/documents")
def list_documents():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.filename, d.num_pages, COUNT(c.id)
        FROM documents d
        LEFT JOIN chunks c ON c.document_id = d.id
        GROUP BY d.id
        ORDER BY d.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    documents = []
    for row in rows:
        documents.append(
            {"id": row[0], "filename": row[1], "pages": row[2], "chunks": row[3]}
        )
    return documents


@app.post("/upload")
def upload_pdf(file: UploadFile = File(...), x_admin_key: str = Header(default="")):
    global retriever

    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Uploads need the admin key")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # save the file to data/pdfs
    os.makedirs("data/pdfs", exist_ok=True)
    save_path = os.path.join("data", "pdfs", os.path.basename(file.filename))
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    new_chunks = ingest_pdf(save_path)

    # forget the old search index so it is rebuilt with the new chunks
    with retriever_lock:
        retriever = None

    return {"filename": file.filename, "new_chunks": new_chunks}


@app.post("/query")
def query(request: QueryRequest):
    # simple daily limit so strangers cannot use up the Groq quota
    today = date.today()
    if queries_today["day"] != today:
        queries_today["day"] = today
        queries_today["count"] = 0
    if queries_today["count"] >= MAX_QUERIES_PER_DAY:
        raise HTTPException(status_code=429, detail="Daily limit reached, try again tomorrow")
    queries_today["count"] += 1

    if len(request.question) > 500:
        raise HTTPException(status_code=400, detail="Question is too long")
    k = max(1, min(request.k, 8))

    start = time.time()

    try:
        search = get_retriever()
    except ValueError:
        raise HTTPException(status_code=400, detail="No documents yet. Upload a PDF first.")

    top_chunks = search.search(request.question, mode="hybrid", k=k)
    answer = answer_question(request.question, top_chunks)

    sources = []
    for chunk, score in top_chunks:
        sources.append(
            {
                "document_id": chunk["document_id"],
                "page": chunk["page_number"],
                "score": round(score, 3),
            }
        )

    return {
        "answer": answer,
        "sources": sources,
        "seconds": round(time.time() - start, 2),
    }