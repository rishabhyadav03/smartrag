import sys
from collections import Counter
from app.db import get_connection
from app.safety import sanitize

apply_changes = "--apply" in sys.argv

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT c.id, d.filename, c.page_number, c.chunk_text
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    ORDER BY c.id
""")
rows = cur.fetchall()

strong_by_doc = Counter()
weak_by_doc = Counter()
changes = []
examples = []

for chunk_id, filename, page, text in rows:
    cleaned, trust, reasons = sanitize(text)
    if trust == 0.0:
        strong_by_doc[filename] += 1
        if len(examples) < 8:
            examples.append((filename, page, reasons[0]))
    elif trust == 0.5:
        weak_by_doc[filename] += 1
    if cleaned != text or trust != 1.0:
        changes.append((cleaned, trust, chunk_id))

print(f"Chunks scanned: {len(rows)}")
print(f"Trust 0.0 (would be blocked): {sum(strong_by_doc.values())}")
print(f"Trust 0.5 (weak signals):     {sum(weak_by_doc.values())}")
print("\nTrust 0.0 by document:", dict(strong_by_doc))
print("Trust 0.5 by document:", dict(weak_by_doc))
print("\nExamples of trust 0.0 chunks:")
for filename, page, reason in examples:
    print(f"  {filename} p{page}: {reason}")

if apply_changes:
    for cleaned, trust, chunk_id in changes:
        cur.execute(
            "UPDATE chunks SET chunk_text = %s, trust_score = %s WHERE id = %s",
            (cleaned, trust, chunk_id),
        )
    conn.commit()
    print(f"\nUpdated {len(changes)} chunks in the database")
else:
    print(f"\nDry run only. {len(changes)} chunks would change. Add --apply to save.")

cur.close()
conn.close()