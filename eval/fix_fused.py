import json
import re
import shutil

shutil.copy("eval/queries_clean.json", "eval/queries_clean_backup.json")

with open("eval/queries_clean.json", encoding="utf-8") as f:
    queries = json.load(f)

invisible = "[\u200b\u200c\u200d\u2060\u00ad\ufeff]"

fixes = {
    "controversiesrelated": "controversies related",
    "underthe": "under the",
    "appointmentfor": "appointment for",
    "mostdifficult": "most difficult",
    "onthe": "on the",
    "fewexamples": "few examples",
    "languagemodel": "language model",
    "makewithin": "make within",
    "verifythe": "verify the",
    "reasonsare": "reasons are",
    "themost": "the most",
    "aduration": "a duration",
    "asinput": "as input",
    "executedon": "executed on",
    "ona": "on a",
    "LegislativeCouncil": "Legislative Council",
}

for item in queries:
    question = re.sub(invisible, "", item["question"])
    for wrong, right in fixes.items():
        question = re.sub(rf"\b{wrong}\b", right, question)
    item["question"] = question

with open("eval/queries_clean.json", "w", encoding="utf-8") as f:
    json.dump(queries, f, indent=2, ensure_ascii=False)

# report anything that still looks fused
for item in queries:
    q = item["question"]
    for wrong in fixes:
        if wrong.lower() in q.lower():
            print("STILL FUSED:", wrong, "->", q)
    for word in re.findall(r"\b\w*[a-z][A-Z]\w*\b", q):
        print("CHECK THIS WORD:", word, "->", q)

print("Done.", len(queries), "questions")