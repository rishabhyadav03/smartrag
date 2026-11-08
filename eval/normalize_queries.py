import json
import re
import unicodedata

with open("eval/queries_clean.json", encoding="utf-8") as f:
    queries = json.load(f)

# these sit inside words, so we delete them
DELETE = {"\u00ad", "\u200c", "\u200d", "\u2060"}

fixes = {
    "mostdifficult": "most difficult",
    "fewexamples": "few examples",
    "verifythe": "verify the",
    "themost": "the most",
    "asinput": "as input",
    "LegislativeCouncil": "Legislative Council",
}


def clean(text):
    text = unicodedata.normalize("NFKC", text)
    result = ""
    for ch in text:
        if ch in DELETE:
            continue
        category = unicodedata.category(ch)
        if category[0] in ("Z", "C", "M"):
            result += " "   # invisible separator becomes a real space
        else:
            result += ch
    return " ".join(result.split())   # collapse repeated spaces


changed = 0
for item in queries:
    old = item["question"]
    new = clean(old)
    for wrong, right in fixes.items():
        new = re.sub(rf"\b{wrong}\b", right, new)
    if new != old:
        changed += 1
        item["question"] = new

with open("eval/queries_clean.json", "w", encoding="utf-8") as f:
    json.dump(queries, f, indent=2, ensure_ascii=False)

print(f"Changed {changed} of {len(queries)} questions")

# if a fused word survives, show its exact characters so we can see what it is
for item in queries:
    if "mostdifficult" in item["question"]:
        print("STILL FUSED:", ascii(item["question"]))