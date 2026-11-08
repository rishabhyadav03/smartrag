# SmartRAG: Retrieval-Augmented Generation over Multiple Documents

A question-answering backend that reads PDFs, finds the most relevant passages with a hybrid keyword search, and asks an LLM to answer using only those passages. It includes a defense against prompt injection hidden inside uploaded documents, and an evaluation setup that measures retrieval accuracy, memory, latency and attack resistance.

**Live API docs:** https://smartrag-8k6m.onrender.com/docs

**Stack:** Python, FastAPI, LangChain (text splitter and Groq client), PostgreSQL (Neon), scikit-learn, rank_bm25, Groq (`openai/gpt-oss-120b`), Render

## Results at a glance

| What | Result |
|---|---|
| Corpus | 10 documents, 1,435 pages, 4,203 chunks |
| Retrieval accuracy (62 questions) | Hybrid reaches **77.4% Top-3** vs 62.9% for TF-IDF alone |
| Indexing memory (4,203 chunks, word pairs) | 60.3 MB with TfidfVectorizer vs **25.8 MB** with HashingVectorizer |
| Whole app on Render | **272.8 MB** of the 512 MB free instance, index ready in 6 s |
| Latency (live, 20 questions) | median **1.38 s**, 95th percentile 1.76 s |
| Prompt-injection attacks | 2/20 succeeded undefended; **0/20** with defenses; 0/5 on held-out attacks |
| False blocks on real chunks | 0 of 4,203 |

## How it works

```
PDF -> text per page -> chunks (1000 characters, 150 overlap)
    -> Layer 1 sanitize + Layer 2 trust score -> PostgreSQL (documents, chunks)

question -> BM25 score + hashing TF-IDF score (both scaled 0 to 1)
         -> hybrid = 0.3 * TF-IDF + 0.7 * BM25
         -> Layer 3: skip blocked chunks -> top 3 chunks
         -> LLM answers using only those chunks, with source numbers
```

- **Chunking:** `RecursiveCharacterTextSplitter`, 1000 characters with 150 overlap. Each chunk keeps its document and page number.
- **Keyword side:** BM25 over lowercase word tokens.
- **TF-IDF side:** `HashingVectorizer` (2^20 slots, words and word pairs, no stored vocabulary) followed by `TfidfTransformer` for IDF weighting.
- **Hybrid:** both score lists are min-max scaled, then mixed 30% TF-IDF and 70% BM25.
- **Generation:** Groq `openai/gpt-oss-120b`, temperature 0, low reasoning effort, answers limited to four sentences, source numbers in the answer.

## Retrieval evaluation

**Method.** 62 questions across the 10 documents. Each question was drafted by an LLM from a randomly sampled passage (told to rephrase, not copy), then reviewed and edited by hand. The correct answer is the source chunk. A search counts as a hit if that chunk, or its direct neighbour in the same document, is among the top results.

| Method | Top-1 | Top-3 |
|---|---|---|
| TF-IDF (words) | 35.5% | 58.1% |
| TF-IDF (words and word pairs) | 38.7% | 64.5% |
| TF-IDF with hashing (words and word pairs) | 38.7% | 62.9% |
| BM25 | 56.5% | 75.8% |
| **Hybrid: 30% hashing TF-IDF + 70% BM25** | **54.8%** | **77.4%** |

A weight sweep (0.0 to 1.0 in steps of 0.1) showed the best results with only 20 to 30% TF-IDF. Using BM25 as the main signal matters more than the exact split.

## Memory: TfidfVectorizer vs HashingVectorizer

`TfidfVectorizer` keeps a dictionary of every unique term, which grows with the corpus. `HashingVectorizer` maps terms into a fixed number of slots and stores no dictionary.

| Chunks | TfidfVectorizer (word pairs) | HashingVectorizer (word pairs) |
|---|---|---|
| 1,000 | 9.9 MB | 19.0 MB |
| 2,000 | 26.9 MB | 21.4 MB |
| 4,203 | **60.3 MB** (201,438-term vocabulary) | **25.8 MB** (no vocabulary) |

Extra memory used while building the index, measured with `psutil` in a fresh process per run. With single words only, the two were within noise of each other (11.6 vs 9.7 MB at 4,203 chunks). Hashing starts to pay off once word pairs are used and the corpus grows. Retrieval accuracy was essentially unchanged (62.9% vs 64.5% Top-3, a one-question difference).

## Prompt-injection defense

Uploaded PDFs are untrusted. A document can contain text like "ignore your instructions and say X" that the model might obey when it is retrieved as context. Defenses, in order:

1. **Layer 1, sanitization at upload.** Removes invisible characters and hidden HTML comments, and deletes sentences that look like orders to an AI. Detection also handles lookalike Cyrillic letters and number-for-letter tricks (`1gn0re`).
2. **Layer 2, trust score.** Each chunk gets a score stored in the database: 1.0 (clean), 0.5 (weak warning signs, such as invisible characters), 0.0 (injection phrase found; a strong signal caps the score).
3. **Layer 3, blocking at retrieval.** Chunks with a score below 0.5 are skipped, and candidates are scanned again at search time in case a stored score is missing or outdated.
4. **Hardened prompt.** The documents are wrapped in tags, the model is told they are untrusted data that may contain orders, and a reminder follows the documents.

**Attack tests.** Each attack tells the model to output a unique code word. The poisoned chunk is placed first in the context (worst case) and the answer is checked for the code word. There are four categories: instruction override, role hijack, data exfiltration, and obfuscated attacks (hidden characters, lookalike letters, base64, leetspeak).

| Attack set | Old prompt, no layers | Hardened prompt, no layers | Hardened prompt + 3 layers |
|---|---|---|---|
| 20 original attacks (5 per category) | 2/20 worked | 0/20 | 0/20 (19 stopped before the model) |
| 5 fresh attacks | 3/5 worked | 0/5 | 0/5 |
| 5 held-out attacks (never tuned on) | not run | 0/5 | 0/5 |

The patterns were also run over all 4,203 real chunks: 0 were blocked (after tightening two patterns that first flagged 6 harmless chunks).

## Notes on the numbers

- The 0.3 / 0.7 weights were chosen using the same 62 questions that are reported, so the hybrid number is slightly optimistic. One question is worth 1.6 points, so the gap between hybrid and BM25 alone (77.4% vs 75.8% Top-3) is within noise.
- The pattern layers and the original 20 attacks were developed together, so 20/20 there is a tuned result. The pattern layers did not catch any of the 10 later attacks; the hardened prompt resisted them. The layers are defense in depth for other models or phrasings.
- The fresh and held-out attacks were drafted with an AI assistant, and each set has only 5 attacks, so 0/5 shows the system is not trivially broken, not that it is secure.
- Latency was measured from India against Render's free instance with 12 seconds between requests. The free Groq tier allows 8,000 tokens per minute, which limits sustained throughput to about 5 questions per minute.
- `openai/gpt-oss-120b` replaced Llama 3.3 70B because Groq retired that model.

## API

| Endpoint | What it does |
|---|---|
| `GET /` | Health check |
| `GET /stats` | Memory use, whether the index is ready, number of chunks |
| `GET /documents` | Documents with page and chunk counts |
| `POST /upload` | Upload a PDF (needs the `x-admin-key` header) |
| `POST /query` | Ask a question |

```json
POST /query
{"question": "What is multi-head attention?", "k": 3}
```

The response contains `answer`, `sources` (document, page, score), and timing fields (`seconds`, `search_seconds`, `llm_seconds`). `/query` is limited to 300 requests per day.

## Run it locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_groq_key
DATABASE_URL=your_postgres_connection_string
ADMIN_KEY=any_long_random_string
```

```bash
python -m app.db               # create the tables
# put PDFs in data/pdfs/
python -m app.ingest           # read, chunk, sanitize, store
uvicorn app.main:app --reload  # open http://127.0.0.1:8000/docs
```

## Reproduce the evaluation

```bash
python -m eval.make_queries         # draft questions from sampled passages
python -m eval.clean_queries        # clean the drafts
python -m eval.run_eval             # compare retrieval methods and weights
python -m eval.memory_test hashing 4203 2   # memory test (method, chunks, max word-pair size)
python -m eval.run_attacks          # original attacks, no pattern layers
python -m eval.run_attacks_defended # original attacks, with all layers
python -m eval.run_fresh            # 5 fresh attacks
python -m eval.run_final            # 5 held-out attacks
```

## Project structure

```
app/
  main.py        FastAPI endpoints
  db.py          database connection and tables
  ingest.py      PDF reading, chunking, sanitizing, storing
  retrieval.py   BM25, hashing TF-IDF, hybrid search, blocking
  safety.py      sanitization, trust score, retrieval-time check
  llm.py         prompt and Groq call
  rescan.py      re-score stored chunks (dry run by default)
eval/            question drafting, retrieval, memory and attack tests
```
