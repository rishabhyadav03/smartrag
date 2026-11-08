import json
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import (
    TfidfVectorizer,
    HashingVectorizer,
    TfidfTransformer,
)
from app.retrieval import load_chunks, tokenize

with open("eval/queries_clean.json", encoding="utf-8") as f:
    queries = json.load(f)

chunks = load_chunks()
texts = [c["text"] for c in chunks]

# ---- build all the search indexes once ----
tfidf_words = TfidfVectorizer(stop_words="english")
words_matrix = tfidf_words.fit_transform(texts)

tfidf_pairs = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
pairs_matrix = tfidf_pairs.fit_transform(texts)

hasher = HashingVectorizer(
    n_features=2**20, alternate_sign=False, norm=None,
    stop_words="english", ngram_range=(1, 2),
)
transformer = TfidfTransformer()
hash_matrix = transformer.fit_transform(hasher.transform(texts))

bm25 = BM25Okapi([tokenize(t) for t in texts])


# ---- one scoring function per method: question in, one score per chunk out ----
def scores_tfidf_words(q):
    return (words_matrix @ tfidf_words.transform([q]).T).toarray().ravel()


def scores_tfidf_pairs(q):
    return (pairs_matrix @ tfidf_pairs.transform([q]).T).toarray().ravel()


def scores_hashing(q):
    vector = transformer.transform(hasher.transform([q]))
    return (hash_matrix @ vector.T).toarray().ravel()


def scores_bm25(q):
    return np.array(bm25.get_scores(tokenize(q)))


def normalize(s):
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


def make_hybrid(tfidf_function, weight):
    # weight = share of the TF-IDF score, the rest comes from BM25
    def hybrid(q):
        return weight * normalize(tfidf_function(q)) + (1 - weight) * normalize(scores_bm25(q))
    return hybrid


# ---- scoring ----
def is_hit(chunk_index, item):
    chunk = chunks[chunk_index]
    same_document = chunk["document_id"] == item["document_id"]
    close_to_gold = abs(chunk["id"] - item["gold_chunk_id"]) <= 1
    return same_document and close_to_gold


def evaluate(score_function):
    hit1 = 0
    hit3 = 0
    missed = []
    for item in queries:
        scores = score_function(item["question"])
        top = np.argsort(scores)[::-1][:3]
        if is_hit(top[0], item):
            hit1 += 1
        if any(is_hit(i, item) for i in top):
            hit3 += 1
        else:
            missed.append(item)
    total = len(queries)
    return hit1 / total, hit3 / total, missed


methods = {
    "TF-IDF (words)": scores_tfidf_words,
    "TF-IDF (word pairs)": scores_tfidf_pairs,
    "TF-IDF hashing (word pairs)": scores_hashing,
    "BM25": scores_bm25,
    "Hybrid 70/30 (TF-IDF words + BM25)": make_hybrid(scores_tfidf_words, 0.7),
    "Hybrid 70/30 (hashing + BM25)": make_hybrid(scores_hashing, 0.7),
}

print(f"Questions: {len(queries)}   Chunks: {len(chunks)}\n")
print(f"{'Method':40} {'Top-1':>7} {'Top-3':>7}")
for name, function in methods.items():
    top1, top3, _ = evaluate(function)
    print(f"{name:40} {top1 * 100:6.1f}% {top3 * 100:6.1f}%")

print("\nWeight sweep, hashing + BM25 (weight = TF-IDF share):")
for weight in np.arange(0, 1.01, 0.1):
    top1, top3, _ = evaluate(make_hybrid(scores_hashing, weight))
    print(f"  weight {weight:.1f}:  Top-1 {top1 * 100:5.1f}%   Top-3 {top3 * 100:5.1f}%")

_, _, missed = evaluate(make_hybrid(scores_hashing, 0.7))
print(f"\nMissed by Hybrid 70/30 (hashing + BM25): {len(missed)} questions")
for item in missed:
    print(f"  - {item['filename']} p{item['page']}: {item['question']}")