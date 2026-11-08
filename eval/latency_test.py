import json
import statistics
import time
import requests

URL = "https://smartrag-8k6m.onrender.com"
PAUSE = 1   # seconds between requests

with open("eval/queries_clean.json", encoding="utf-8") as f:
    questions = [q["question"] for q in json.load(f)][:20]

# warm-up request, not counted
requests.post(
    f"{URL}/query",
    json={"question": "What is multi-head attention?", "k": 4},
    timeout=120,
)

times = []
for question in questions:
    start = time.time()
    response = requests.post(f"{URL}/query", json={"question": question, "k": 4}, timeout=120)
    seconds = time.time() - start
    if response.status_code == 200:
        data = response.json()
        times.append(seconds)
        print(
            f"{seconds:5.2f}s total | search {data['search_seconds']:.2f}s | "
            f"model {data['llm_seconds']:.2f}s | {data['answer_chars']} chars | {question[:35]}"
        )
    else:
        print(f"{seconds:5.2f}s ERROR {response.status_code} {response.text[:80]}")
    time.sleep(PAUSE)

times.sort()
p95_index = max(0, round(0.95 * len(times)) - 1)
print(f"\nSuccessful requests: {len(times)}")
print(f"Median: {statistics.median(times):.2f}s")
print(f"95th percentile: {times[p95_index]:.2f}s")
print(f"Slowest: {times[-1]:.2f}s")