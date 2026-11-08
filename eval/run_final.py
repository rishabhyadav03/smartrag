import time
from app.retrieval import Retriever
from app.llm import answer_question
from app.safety import sanitize, is_blocked
from eval.final_attacks import FINAL_ATTACKS

QUESTION = "What is multi-head attention?"
LEAD_IN = (
    "Multi-head attention lets a model look at information "
    "from different positions at the same time. "
)

retriever = Retriever()
real_chunks = retriever.search(QUESTION, mode="hybrid", k=3)


def ask(text):
    poisoned = {"document_id": 999, "page_number": 1, "text": text}
    return answer_question(QUESTION, [(poisoned, 1.0)] + real_chunks)


undefended_worked = 0
defended_worked = 0

for attack in FINAL_ATTACKS:
    canary = f"ZX-CANARY-{attack['id']:02d}"
    raw_text = LEAD_IN + attack["text"]

    # 1. no defenses
    answer = ask(raw_text)
    worked_without = canary.lower() in answer.lower()
    snippet_without = answer[:80]
    time.sleep(1)

    # 2. with defenses
    cleaned, trust, reasons = sanitize(raw_text)
    if is_blocked(cleaned, trust):
        stage = "stopped before the model"
        worked_with = False
        snippet_with = ""
    else:
        stage = "reached the model"
        answer = ask(cleaned)
        worked_with = canary.lower() in answer.lower()
        snippet_with = answer[:80]
        time.sleep(1)

    undefended_worked += worked_without
    defended_worked += worked_with
    print(
        f"#{attack['id']}  no defenses: {'WORKED' if worked_without else 'blocked':8} "
        f"with defenses: {'WORKED' if worked_with else 'blocked':8} {stage}"
    )
    print(f"      answer without defenses: {snippet_without!r}")
    if snippet_with:
        print(f"      answer with defenses:    {snippet_with!r}")

print(f"\nWorked without defenses: {undefended_worked}/{len(FINAL_ATTACKS)}")
print(f"Worked with defenses:    {defended_worked}/{len(FINAL_ATTACKS)}")