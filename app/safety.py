import re
import unicodedata

# characters that are invisible but can hide text
INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"]

# Cyrillic letters that look like English letters
LOOKALIKES = {
    "\u043e": "o", "\u0435": "e", "\u0430": "a",
    "\u0440": "p", "\u0441": "c", "\u0445": "x", "\u0456": "i",
}

# numbers and symbols people use in place of letters, like 1gn0re
LEET = str.maketrans("013457@$", "oieastas")

# phrases that try to give orders to the AI
STRONG_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|your|these) (instructions|rules|prompts?|directions)",
    r"disregard .{0,40}(instructions|question|rules|above|context)",
    r"forget (everything|all|what).{0,20}(above|before|previous|said)",
    r"(new|updated) (system )?(instructions?|prompt)\s*[:#]",
    r"do not answer from the context",
    r"(note|message|instruction) (to|for) (the )?(ai|assistant|llm|model)",
    r"you are (now|no longer)\b",
    r"(developer|admin) mode",
    r"admin(istrator)? override",
    r"bypass (your|the|all) (rules|restrictions|guidelines|safety)",
    r"(print|reveal|show|repeat|output|display|leak) (me )?(your|the|any|all) .{0,30}(system prompt|api keys?|passwords?|secrets?)",
    r"repeat .{0,30}(context|passages).{0,20}(word for word|verbatim)",
    r"!\[[^\]]*\]\(https?://",
    r"(send|post|forward|transmit|include) .{0,60}https?://",
    r"decode .{0,40}(and|then) (do|follow|execute|obey)",
]


def looks_like_injection(sentence):
    if re.search(r"^\s*(SYSTEM|ASSISTANT|ADMIN)\s*:", sentence):
        return True
    # we check a cleaned-up copy; the stored text itself is not changed here
    check = unicodedata.normalize("NFKC", sentence).lower()
    for fake, real in LOOKALIKES.items():
        check = check.replace(fake, real)
    check = check.translate(LEET)
    for pattern in STRONG_PATTERNS:
        if re.search(pattern, check):
            return True
    return False


def trust_score(strong_hits, weak_hits):
    # Layer 2: a strong signal caps the score at 0.0 (a hard cap)
    if strong_hits > 0:
        return 0.0
    if weak_hits > 0:
        return 0.5
    return 1.0


def sanitize(text):
    # Layer 1: clean the text.  Layer 2: give it a trust score.
    reasons = []
    strong = 0
    weak = 0
    cleaned = text

    # remove invisible characters
    for ch in INVISIBLE:
        if ch in cleaned:
            cleaned = cleaned.replace(ch, "")
            weak += 1
            reasons.append("invisible characters")

    # drop every sentence that contains an injection phrase
    sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    kept = []
    for sentence in sentences:
        if looks_like_injection(sentence):
            strong += 1
            reasons.append("injection phrase: " + sentence[:60])
        else:
            kept.append(sentence)
    if strong > 0:
        cleaned = " ".join(kept)

    # remove hidden HTML comments
    if "<!--" in cleaned:
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        weak += 1
        reasons.append("html comment")

    # long encoded-looking blobs (a warning only, the text stays)
    if re.search(r"[A-Za-z0-9+/]{40,}={0,2}", cleaned):
        weak += 1
        reasons.append("long encoded blob")

    return cleaned, trust_score(strong, weak), reasons

def is_blocked(text, trust):
    # Layer 3: decide at search time whether a chunk may reach the model
    if trust is None:
        trust = 1.0
    if trust < 0.5:
        return True

    # check again, in case the stored score is missing or out of date
    for ch in INVISIBLE:
        text = text.replace(ch, "")
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if looks_like_injection(sentence):
            return True
    return False