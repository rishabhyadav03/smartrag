import re
import numpy as np
import psutil
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from app.db import get_connection
from app.safety import is_blocked

TFIDF_WEIGHT = 0.3  # share of the hashing TF-IDF score
BM25_WEIGHT = 0.7   # share of the BM25 score


def load_chunks():
    # read every chunk from the database
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, document_id, page_number, chunk_text, trust_score FROM chunks ORDER BY id"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    chunks = []
    for row in rows:
        chunks.append(
            {
                "id": row[0],
                "document_id": row[1],
                "page_number": row[2],
                "text": row[3],
                "trust": row[4],
            }
        )
    return chunks

def log(message):
    memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    print(f"[index] {message} - memory {memory_mb:.0f} MB", flush=True)


def tokenize(text):
    # lowercase and split into words
    return re.findall(r"\w+", text.lower())


class Retriever:
    def __init__(self):
        self.chunks = load_chunks()
        if len(self.chunks) == 0:
            raise ValueError("No chunks in database. Run: python -m app.ingest")
        log("chunks loaded")

        texts = [c["text"] for c in self.chunks]

        # BM25 index
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])
        log("BM25 built")

        # TF-IDF index using hashing: no vocabulary dictionary is stored
        self.hasher = HashingVectorizer(
            n_features=2**20,
            alternate_sign=False,
            norm=None,
            stop_words="english",
            ngram_range=(1, 2),  # single words and word pairs
        )
        self.transformer = TfidfTransformer()
        counts = self.hasher.transform(texts)
        self.tfidf_matrix = self.transformer.fit_transform(counts)
        log("TF-IDF built")

    def bm25_scores(self, query):
        # one score per chunk
        return np.array(self.bm25.get_scores(tokenize(query)))

    def tfidf_scores(self, query):
        # similarity between the query and every chunk
        counts = self.hasher.transform([query])
        query_vector = self.transformer.transform(counts)
        return (self.tfidf_matrix @ query_vector.T).toarray().ravel()

    def normalize(self, scores):
        # scale scores to the 0 to 1 range
        low = scores.min()
        high = scores.max()
        return (scores - low) / (high - low + 1e-9)

    def hybrid_scores(self, query, tfidf_weight=TFIDF_WEIGHT, bm25_weight=BM25_WEIGHT):
        tfidf = self.normalize(self.tfidf_scores(query))
        bm25 = self.normalize(self.bm25_scores(query))
        return tfidf_weight * tfidf + bm25_weight * bm25

    def top_k(self, scores, k=3):
        # go through chunks from best to worst, skipping blocked ones
        best = np.argsort(scores)[::-1]
        results = []
        for i in best:
            chunk = self.chunks[i]
            if is_blocked(chunk["text"], chunk["trust"]):
                continue  # Layer 3: an untrusted chunk never reaches the model
            results.append((chunk, float(scores[i])))
            if len(results) == k:
                break
        return results

    def search(self, query, mode="hybrid", k=3):
        # one function to pick which method to use
        if mode == "bm25":
            scores = self.bm25_scores(query)
        elif mode == "tfidf":
            scores = self.tfidf_scores(query)
        else:
            scores = self.hybrid_scores(query)
        return self.top_k(scores, k)


if __name__ == "__main__":
    retriever = Retriever()
    print("Chunks loaded:", len(retriever.chunks))

    queries = [
        "What is multi-head attention?",
        "How does the NIST framework define risk?",
        "How does RAG combine a retriever with a generator?",
    ]

    for query in queries:
        print("\nQUESTION:", query)
        for chunk, score in retriever.search(query, mode="hybrid", k=3):
            print(f"  doc {chunk['document_id']}, page {chunk['page_number']}, score {score:.2f}")
            print("  ", chunk["text"][:120].replace("\n", " "))