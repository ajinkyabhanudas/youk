"""Local semantic similarity for cross-project pattern/contract matching.

Exact-match text comparison is the wrong tool for a meaning question. This
module is the right one -- a small, local, offline sentence-embedding model
(all-MiniLM-L6-v2, 22.7M parameters, ~90MB), not a call to any LLM vendor's API. No network
access at runtime: the model weights are baked into the Docker image at
build time.
"""
from __future__ import annotations

from functools import lru_cache

_MODEL_NAME = "all-MiniLM-L6-v2"

# Calibrated against real contract pairs, not guessed: identical text scores
# 1.0, unrelated pairs score 0.01-0.19, true paraphrases score 0.39-0.77
# depending on lexical overlap. 0.55 catches close paraphrases while
# keeping genuinely distinct lessons (which scored up to 0.32) unmerged --
# erring toward missing a repeat over wrongly merging two different ones.
# A heavily reworded paraphrase (low lexical overlap) can still score below
# this; that's a real limit of a general-purpose embedding model, not a bug.
_SIMILARITY_THRESHOLD = 0.55


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_MODEL_NAME)


def similarity(text_a: str, text_b: str) -> float:
    """Cosine similarity between two statements, 0.0-1.0. Identical text
    returns 1.0; unrelated text returns close to 0.0."""
    from sentence_transformers import util
    model = _model()
    emb = model.encode([text_a, text_b])
    return float(util.cos_sim(emb[0], emb[1])[0][0])


def find_most_similar(text: str, candidates: list[str]) -> tuple[str | None, float]:
    """Return (best_match, score) from candidates, or (None, 0.0) if
    candidates is empty. Does not apply the threshold -- callers decide
    what counts as a match for their own use case."""
    if not candidates:
        return None, 0.0
    from sentence_transformers import util
    model = _model()
    text_emb = model.encode([text])[0]
    cand_emb = model.encode(candidates)
    scores = util.cos_sim(text_emb, cand_emb)[0]
    best_idx = int(scores.argmax())
    return candidates[best_idx], float(scores[best_idx])


def is_same_lesson(text_a: str, text_b: str, threshold: float = _SIMILARITY_THRESHOLD) -> bool:
    """True if text_a and text_b express the same lesson closely enough to
    be treated as a repeat, not two distinct patterns."""
    return similarity(text_a, text_b) >= threshold


def cluster_by_similarity(texts: list[str], threshold: float = _SIMILARITY_THRESHOLD) -> list[list[int]]:
    """Group texts whose pairwise similarity meets threshold, returning each
    group as a list of indices into `texts`.

    Encodes every text ONCE in a single batched call, then clusters via a
    precomputed similarity matrix. Calling similarity()/is_same_lesson() in
    an O(n^2) loop instead re-encodes text on every comparison -- fine for a
    handful of pairs, unusably slow (minutes, not seconds) once real
    cross-project contract counts reach the dozens. This is the real fix for
    that, not a micro-optimization: callers clustering more than a few
    texts must use this, not a pairwise loop over is_same_lesson.
    """
    if not texts:
        return []
    from sentence_transformers import util
    model = _model()
    embeddings = model.encode(texts)
    sim_matrix = util.cos_sim(embeddings, embeddings)

    assigned = [-1] * len(texts)
    clusters: list[list[int]] = []
    for i in range(len(texts)):
        if assigned[i] != -1:
            continue
        cluster_idx = len(clusters)
        clusters.append([i])
        assigned[i] = cluster_idx
        for j in range(i + 1, len(texts)):
            if assigned[j] == -1 and float(sim_matrix[i][j]) >= threshold:
                assigned[j] = cluster_idx
                clusters[cluster_idx].append(j)
    return clusters


# Relevance floor for "is this past task about the same kind of work", used by
# retrieval-grounding (sizing precedent). Sits between the calibration figures
# recorded above for this model: unrelated pairs scored 0.01-0.19, true
# paraphrases 0.39-0.77. Task descriptions about the same kind of work are
# looser than paraphrases of one lesson, so this is deliberately below
# _SIMILARITY_THRESHOLD. tests/test_task_relevance_floor.py checks that it separates 8 related
# from 8 unrelated task pairs; retune it from state/sizing-decisions.jsonl as real rows accumulate.
TASK_RELEVANCE_FLOOR = 0.30


# Relevance floor for "does this cross-project lesson bear on this task". A
# lesson is abstracted and a task is concrete, so their scores run lower than
# task-to-task pairs; this sits at the lowest true-paraphrase score recorded
# above (0.39) to favour leaving a lesson out over showing an unrelated one.
# Recall is unmeasured: it may be too strict. tests/test_task_relevance_floor.py
# checks precision (no unrelated pair clears it) wherever the model exists.
LESSON_RELEVANCE_FLOOR = 0.40


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def rank_by_similarity(
    text: str, candidates: list[str], *, min_score: float = 0.0, limit: int | None = None
) -> list[tuple[int, float]]:
    """(candidate_index, score) pairs, best first, dropping scores below
    min_score. Encodes the query and every candidate in one batched call.
    Raises if the embedding model is unavailable -- callers decide how to
    report that; this never returns an empty list to hide a failure."""
    if not candidates:
        return []
    embeddings = _model().encode([text, *candidates])
    query = [float(x) for x in embeddings[0]]
    scored = [
        (i, _cosine(query, [float(x) for x in emb]))
        for i, emb in enumerate(embeddings[1:])
    ]
    scored = sorted((s for s in scored if s[1] >= min_score), key=lambda s: -s[1])
    return scored[:limit] if limit else scored
