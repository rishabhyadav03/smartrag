import json
import re

with open("eval/queries.json", encoding="utf-8") as f:
    queries = json.load(f)

# 1. fix words stuck together by PDF line breaks
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
}
for item in queries:
    for wrong, right in fixes.items():
        item["question"] = re.sub(rf"\b{wrong}\b", right, item["question"])

# 2. drop weak questions (each text must match exactly one question)
drop_list = [
    "1993 study",
    "attained the highest reported results",
    "first conversion system",
    "prohibited from getting involved in disputes",
    "performance graph",
    "short instruction or a few examples",
    "flavor qualities",
    "flavor descriptors",
    "starting a vehicle",
    "fraud organizers",
    "How many lines of output does the function produce",
    "filename of the notebook",
    "Kaiser",
    "size of the training set",
]
for text in drop_list:
    matches = [q for q in queries if text in q["question"]]
    if len(matches) != 1:
        print(f"WARNING: '{text}' matched {len(matches)} questions")
    queries = [q for q in queries if text not in q["question"]]

# 3. rewrite vague questions so they make sense on their own
rewrites = {
    "What BLEU score did the model obtain":
        "What BLEU score did the Transformer reach on the WMT 2014 English-to-German translation task?",
    "uses only one attention head":
        "In the Transformer paper's ablation study, how does the BLEU score change when only one attention head is used compared to the best configuration?",
    "Around how many":
        "Around how many source-language tokens were in each training batch when training the Transformer?",
    "How many layers are stacked in the encoder":
        "How many layers are stacked in the Transformer's encoder, and which two sub-layers does each layer contain?",
    "what name is typically used for the initial argument":
        "In Python, what name is conventionally used for the first parameter of a method?",
    "complete book titles":
        "In the RAG paper, what lets the model complete a book title after its first word is generated, instead of relying on a particular retrieved document?",
}
for text, new_question in rewrites.items():
    matches = [q for q in queries if text in q["question"]]
    if len(matches) != 1:
        print(f"WARNING: '{text}' matched {len(matches)} questions")
    for q in matches:
        q["question"] = new_question

# 4. keep at most 7 questions per document
kept = []
count_per_doc = {}
for q in queries:
    name = q["filename"]
    if count_per_doc.get(name, 0) < 7:
        kept.append(q)
        count_per_doc[name] = count_per_doc.get(name, 0) + 1

with open("eval/queries_clean.json", "w", encoding="utf-8") as f:
    json.dump(kept, f, indent=2, ensure_ascii=False)

print(f"Saved {len(kept)} questions to eval/queries_clean.json")
for name, n in count_per_doc.items():
    print(f"  {name}: {n}")