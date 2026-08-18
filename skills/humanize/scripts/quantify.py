#!/usr/bin/env python3
"""
Deterministic AI-tell check for long-form documents.

Runs every check accumulated in ai-tell-taxonomy.md and distributional-realism.md,
in a fixed order, every time. This exists because checking ad hoc (whatever the
reviewer happens to remember) produced a non-deterministic loop: a document would
pass one check and still contain a violation of a different, previously-documented
one. Running this script IS the check. Don't substitute memory for it.

Usage: python3 quantify.py <path-to-markdown-file>

Extend this file, don't work around it: if a new pattern gets caught by a human
that this script doesn't catch, add it here AND to ai-tell-taxonomy.md, in the
same sitting. A pattern that's fixed once but not added here will reappear.
"""
import re
import statistics
import sys
from collections import Counter


def load_prose(path):
    text = open(path).read()
    # strip raw openxml blocks (page breaks etc.) and markdown scaffolding
    text = re.sub(r"```\{=openxml\}.*?```", "", text, flags=re.S)
    text = re.sub(r"\*\(word count:.*?\)\*", "", text)
    idx = text.find("## Abstract")
    if idx == -1:
        idx = 0
    end = text.find("## Running word count")
    if end == -1:
        end = len(text)
    body = text[idx:end]
    prose = re.sub(r"\*\*|##|!\[\]\([^)]*\)|\*\[.*?\]\*", "", body)
    return body, prose


def check_1_burstiness(prose):
    print("\n[1] SENTENCE-LENGTH BURSTINESS")
    sentences = re.split(r"(?<=[.!?])\s+", prose.replace("\n", " "))
    lengths = [len(s.split()) for s in sentences if len(s.split()) > 1]
    if not lengths:
        print("  no sentences found")
        return
    mean = statistics.mean(lengths)
    stdev = statistics.stdev(lengths)
    print(f"  mean {mean:.1f}, stdev {stdev:.1f}, range {min(lengths)}-{max(lengths)}")
    print("  reference: AI ~2.7 stdev, human general ~7, formal writing runs a bit lower than casual")
    if stdev < 5:
        print("  FLAG: stdev below 5 — uniform sentence length, AI-tell risk")
    else:
        print("  OK — well above the AI reference")


def check_2_colons(body):
    print("\n[2] COLONS")
    n = body.count(":")
    words = len(re.findall(r"[a-zA-Z']+", body))
    rate = n / words * 1000 if words else 0
    print(f"  {n} colons, {rate:.2f}/1000 words")
    if n > 0:
        for m in re.finditer(r".{25}:.{35}", body):
            print(f"    ...{m.group(0)}...")
    print("  target: only genuine 3+ item parallel lists, or an unavoidable published title. Everything else -> period or comma.")


def check_3_emdash(body):
    print("\n[3] EM DASHES")
    n = body.count("—")
    print(f"  {n} found" + (" — FLAG, must be zero in prose" if n else " — OK"))


def check_4_antithesis(prose):
    print("\n[4] ANTITHESIS / NEGATION-REVEAL")
    hits = re.findall(r".{20}, not [a-z].{30}", prose, re.I)
    hits += re.findall(r".{20}isn't [a-z].{10}it's.{20}", prose, re.I)
    hits += re.findall(r".{20}rather than.{30}", prose, re.I)
    if hits:
        for h in hits:
            print(f"    FLAG: ...{h}...")
    else:
        print("  none found — OK")


def check_5_clefts(prose):
    print("\n[5] WH-CLEFTS / EPIPHANY-ANNOUNCING")
    hits = re.findall(r"\bWhat [a-zA-Z' ]{3,40}? was .{20}", prose)
    hits += re.findall(r"\bWhat [a-zA-Z' ]{3,40}? is .{20}", prose)
    hits += re.findall(r"\bI (?:recognized|realized|understood|came to see) that\b.{20}", prose, re.I)
    hits += re.findall(r"\b[a-z]+ I (?:hadn't|had not) (?:thought to|considered|realized|known to)\b.{10}", prose, re.I)
    if hits:
        for h in hits:
            print(f"    FLAG: {h}")
    else:
        print("  none found — OK")


VOCAB_TELLS = [
    "load-bearing", "lands", "landed", "compounding", "unpack", "crux", "grapple",
    "seamless", "holistic", "nuanced", "multifaceted", "underscore", "resonate",
    "elevate", "foster", "harness", "unlock", "paradigm", "landscape", "ecosystem",
    "testament", "shed light", "dive into", "keystone", "tapestry", "delve",
    "optimize", "leverage", "streamline", "furthermore", "moreover", "additionally",
    "shape", "shapes", "narrow", "narrower", "underneath", "honest", "honestly",
    "quietly", "entirely", "exactly",
]


def check_6_vocab(prose):
    print("\n[6] FULL VOCABULARY-TELL LIST (ai-tell-taxonomy.md §1)")
    found_any = False
    for w in VOCAB_TELLS:
        n = len(re.findall(r"\b" + re.escape(w) + r"\b", prose, re.I))
        if n:
            found_any = True
            print(f"    FLAG: '{w}' x{n}")
    if not found_any:
        print("  none found — OK")


# words with an established general-English baseline rate (per 1000 words),
# used to catch project-specific crutch words even below the fixed list above
BASELINE = {
    "same": 0.25, "already": 0.35, "instead": 0.25, "rather": 0.3, "before": 1.1,
    "because": 0.9, "against": 0.2, "actually": 0.4, "directly": 0.4,
    "specific": 0.3, "journey": 0.1, "real": 0.4, "matter": 0.2, "not": 5.5,
    "one": 2.9, "would": 3.5,
}


def check_7_frequency(prose):
    print("\n[7] WORD-FREQUENCY VS BASELINE")
    words = re.findall(r"[a-zA-Z']+", prose.lower())
    total = len(words)
    freq = Counter(words)
    rows = []
    for w, b in BASELINE.items():
        c = freq.get(w, 0)
        rate = c / total * 1000 if total else 0
        mult = rate / b if b else 0
        rows.append((w, c, mult))
    rows.sort(key=lambda x: -x[2])
    for w, c, mult in rows:
        flag = "  <-- CHECK (count>=3 and >=4x)" if (mult >= 4 and c >= 3) else ""
        print(f"    {w:10s} count={c:3d}  {mult:5.1f}x{flag}")


def check_8_rule_of_three(prose):
    print("\n[8] RULE-OF-THREE (adjective/adjective/and-adjective, phrase/phrase/and-phrase)")
    hits = re.findall(r"[a-z]+, [a-z]+, and [a-z]+", prose)
    if hits:
        for h in hits:
            print(f"    check (may be legitimate list, judge on content): {h}")
    else:
        print("  none found")


def check_9_false_intimacy(prose):
    print("\n[9] FALSE-INTIMACY / TONE-REGISTER TELLS")
    phrases = ["here's the part", "but here's the truth", "i'm going to state this",
               "nobody's saying", "it's important to remember that", "at its core",
               "the real truth is"]
    found_any = False
    for p in phrases:
        if p in prose.lower():
            found_any = True
            print(f"    FLAG: '{p}'")
    if not found_any:
        print("  none found — OK")


def check_10_proof_beat(prose):
    print("\n[10] PROOF-BEAT FRAGMENTS (short sentence + colon-stat)")
    hits = re.findall(r"[A-Z][a-z]*\. [A-Z][a-z]*:", prose)
    if hits:
        for h in hits:
            print(f"    FLAG: {h}")
    else:
        print("  none found — OK")


CONNECTIVE_STARTS = (
    "but ", "and ", "so ", "because ", "while ", "though ", "since ", "when ",
    "if ", "after ", "before ", "once ", "yet ", "still ", "then ",
)


def check_12_bullet_fusion(prose):
    print("\n[12] BULLET-FUSION (runs of short, atomic, unconnected declarative sentences)")
    paragraphs = [p for p in prose.split("\n\n") if p.strip()]
    found_any = False
    for para in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", para.replace("\n", " ").strip())
        run = []
        for s in sentences:
            words = s.split()
            n = len(words)
            starts_connective = s.lower().startswith(CONNECTIVE_STARTS)
            has_subordination = "," in s or ";" in s
            is_atomic = 0 < n <= 12 and not starts_connective and not has_subordination
            if is_atomic:
                run.append(s)
            else:
                if len(run) >= 3:
                    found_any = True
                    print(f"    FLAG: {' / '.join(run)}")
                run = []
        if len(run) >= 3:
            found_any = True
            print(f"    FLAG: {' / '.join(run)}")
    if not found_any:
        print("  none found — OK")


def check_11_word_count(prose):
    print("\n[11] WORD COUNT (Abstract through Conclusion)")
    words = re.findall(r"[a-zA-Z']+", prose)
    print(f"  {len(words)} words (target 4,000-5,000)")


def check_13_short_decl_pair(prose):
    print("\n[13] SHORT DECLARATIVE PAIR (adjacent sentences both <=8 words)")
    sentences = re.split(r"(?<=[.!?])\s+", prose.replace("\n", " "))
    words_total = max(len(re.findall(r"[a-zA-Z']+", prose)), 1)
    pairs = []
    for i in range(len(sentences) - 1):
        a, b = sentences[i].split(), sentences[i + 1].split()
        if len(a) <= 8 and len(b) <= 8:
            pairs.append((sentences[i], sentences[i + 1]))
    rate = 1000 * len(pairs) / words_total
    print(f"  {len(pairs)} pair(s), rate {rate:.1f}/1k words (limit 0.5/1k = 1 per 2000w)")
    for a, b in pairs[:5]:
        print(f"    FLAG: {a!r} / {b!r}")
    if not pairs:
        print("  none found — OK")


def check_14_appositive_definition(prose):
    print("\n[14] REPEATED APPOSITIVE DEFINITION (, the/which/how X)")
    hits = re.findall(
        r",\s+(?:the\s+\w+(?:\s+\w+){1,8}|which\s+\w+(?:\s+\w+){1,8}|how\s+\w+(?:\s+\w+){1,8})",
        prose, re.I,
    )
    print(f"  {len(hits)} instance(s) (limit 3 per doc)")
    if len(hits) > 3:
        for h in hits[:5]:
            print(f"    FLAG: ...{h}...")
    elif hits:
        print("  within limit — OK")
    else:
        print("  none found — OK")


def check_15_section_endings(body):
    print("\n[15] SECTION ENDINGS (aphorism-landing check)")
    APHORISM_SIGNALS = [
        r"\bthe only\b", r"\bwhat (really )?matters\b", r"\bthe point\b",
        r"\bthe real\b", r"\balways\b", r"\bnever\b", r"\bis the currency\b",
        r"\bis what\b.*\bmatters\b", r"\bthat is (the|what)\b",
    ]
    sections = re.split(r"\n#{1,3} ", body)
    aphorism_endings = 0
    flat_endings = 0
    for sec in sections:
        paras = [p.strip() for p in sec.strip().split("\n\n") if p.strip()]
        if not paras:
            continue
        last_para = paras[-1]
        sents = re.split(r"(?<=[.!?])\s+", last_para.replace("\n", " "))
        last = sents[-1] if sents else ""
        is_aphorism = any(re.search(p, last, re.I) for p in APHORISM_SIGNALS)
        if is_aphorism:
            aphorism_endings += 1
            print(f"    FLAG (aphorism): {last[:80]}")
        else:
            flat_endings += 1
    total = aphorism_endings + flat_endings
    if total:
        pct = 100 * aphorism_endings // total
        print(f"  {aphorism_endings}/{total} sections end on aphorism ({pct}%) — target: <33%")
    else:
        print("  no sections found")


def check_voice_gate(prose):
    """Run voice_fingerprint.check_text if available."""
    print("\n[VOICE GATE] check_text (voice_fingerprint)")
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "servers", "core", "src"))
        from voice_fingerprint import check_text
        r = check_text(prose)
        print(f"  gate: {r['gate']}")
        for t in r["tells_hard"]:
            print(f"  HARD: {t}")
        for t in r["tells_soft"]:
            print(f"  SOFT: {t}")
        if not r["tells_hard"] and not r["tells_soft"]:
            print("  clean")
    except ImportError:
        print("  voice_fingerprint not on path — skipped")


def main():
    if len(sys.argv) != 2:
        print("usage: python3 quantify.py <path-to-markdown-file>")
        sys.exit(1)
    path = sys.argv[1]
    body, prose = load_prose(path)
    print(f"=== QUANTIFY: {path} ===")
    check_voice_gate(prose)
    check_1_burstiness(prose)
    check_2_colons(body)
    check_3_emdash(body)
    check_4_antithesis(prose)
    check_5_clefts(prose)
    check_6_vocab(prose)
    check_7_frequency(prose)
    check_8_rule_of_three(prose)
    check_9_false_intimacy(prose)
    check_10_proof_beat(prose)
    check_12_bullet_fusion(prose)
    check_13_short_decl_pair(prose)
    check_14_appositive_definition(prose)
    check_15_section_endings(body)
    check_11_word_count(prose)
    print("\n=== end of pass. Fix every FLAG, then re-run. Do not present as done until a full pass has zero new flags. ===")


if __name__ == "__main__":
    main()
