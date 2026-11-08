import sys
import psutil
from sklearn.feature_extraction.text import (
    TfidfVectorizer,
    HashingVectorizer,
    TfidfTransformer,
)
from app.retrieval import load_chunks


def current_mb():
    return psutil.Process().memory_info().rss / (1024 * 1024)


def peak_mb():
    # peak memory used so far (this value exists on Windows)
    info = psutil.Process().memory_info()
    return getattr(info, "peak_wset", info.rss) / (1024 * 1024)


method = sys.argv[1]                                  # "tfidf" or "hashing"
limit = int(sys.argv[2])                              # how many chunks to use
max_ngram = int(sys.argv[3]) if len(sys.argv) > 3 else 1   # 1 = words, 2 = words + word pairs
ngrams = (1, max_ngram)

chunks = load_chunks()[:limit]
texts = [c["text"] for c in chunks]

baseline = current_mb()  # memory before building anything

if method == "tfidf":
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=ngrams)
    matrix = vectorizer.fit_transform(texts)
    vocab_size = len(vectorizer.vocabulary_)
else:
    # more slots when we use word pairs, so fewer words collide
    slots = 2**18 if max_ngram == 1 else 2**20
    hasher = HashingVectorizer(
        n_features=slots,
        alternate_sign=False,
        norm=None,
        stop_words="english",
        ngram_range=ngrams,
    )
    counts = hasher.transform(texts)
    matrix = TfidfTransformer().fit_transform(counts)
    vocab_size = 0  # hashing keeps no vocabulary

peak = peak_mb()
print(
    f"{method:8} ngram={max_ngram} chunks={len(texts):5}  "
    f"baseline={baseline:6.1f} MB  peak={peak:6.1f} MB  "
    f"extra={peak - baseline:6.1f} MB  vocab stored={vocab_size}"
)