"""Local semantic similarity, replacing exact-text matching for cross-project
pattern/contract recurrence detection. Scores below are the real calibration
run against actual contract text, not invented numbers -- the threshold in
semantic_similarity.py was set from this data.
"""
from __future__ import annotations

import pytest

from semantic_similarity import similarity, is_same_lesson, find_most_similar, cluster_by_similarity


def test_identical_text_scores_near_one():
    assert similarity("always run ruff before committing", "always run ruff before committing") > 0.99


def test_unrelated_statements_score_low():
    assert similarity(
        "use tuple instead of list for frozen dataclass fields",
        "PR descriptions must never include an AI attribution footer",
    ) < 0.2


def test_close_paraphrase_is_recognized_as_same_lesson():
    assert is_same_lesson(
        "never commit screenshot files from Playwright testing",
        "Playwright test screenshots should never be checked into the repo",
    )


def test_distinct_but_thematically_related_lessons_are_not_merged():
    """Both statements are about verifying before concluding, but they are
    two different lessons -- merging them would corrupt the knowledge base.
    This is the real failure mode semantic matching must avoid, not just
    the exact-match recall gap it's meant to close."""
    assert not is_same_lesson(
        "always verify root cause empirically before guessing",
        "before stating a conclusion, find the evidence that resolves it",
    )


def test_heavily_reworded_paraphrase_may_score_below_threshold():
    """Named limit, not a bug: a general-purpose embedding model can miss a
    true paraphrase when lexical overlap is very low. Exact-match would
    always miss this case too; this is not a regression, just an
    acknowledged ceiling."""
    score = similarity(
        "always verify root cause empirically before guessing",
        "reproduce the bug with and without the suspected factor before asking",
    )
    assert 0.3 < score < 0.55


def test_find_most_similar_picks_the_real_best_match():
    best, score = find_most_similar(
        "never commit screenshot files from Playwright testing",
        [
            "use tuple instead of list for frozen dataclass fields",
            "Playwright test screenshots should never be checked into the repo",
            "PR descriptions must never include an AI attribution footer",
        ],
    )
    assert best == "Playwright test screenshots should never be checked into the repo"
    assert score > 0.5


def test_find_most_similar_with_empty_candidates():
    assert find_most_similar("anything", []) == (None, 0.0)


def test_is_same_lesson_respects_custom_threshold():
    a = "always verify root cause empirically before guessing"
    b = "before stating a conclusion, find the evidence that resolves it"
    assert not is_same_lesson(a, b, threshold=0.55)
    assert is_same_lesson(a, b, threshold=0.1)  # trivially true at a low enough bar


class TestClusterBySimilarity:
    """Found 2026-10-04: a pairwise is_same_lesson loop re-encodes text on
    every single comparison. Real cross-project contract counts (dozens
    across 10+ real projects) made that unusably slow -- a live call never
    returned within 60s. cluster_by_similarity batch-encodes once; these
    tests prove the clustering result is still correct, not just faster."""

    def test_empty_input_returns_empty(self):
        assert cluster_by_similarity([]) == []

    def test_single_text_is_its_own_cluster(self):
        assert cluster_by_similarity(["one statement"]) == [[0]]

    def test_identical_texts_cluster_together(self):
        result = cluster_by_similarity(["same text", "same text", "unrelated entirely"])
        clusters_as_sets = [set(c) for c in result]
        assert {0, 1} in clusters_as_sets

    def test_paraphrases_cluster_distinct_lessons_do_not(self):
        texts = [
            "never commit screenshot files from Playwright testing",
            "Playwright test screenshots should never be checked into the repo",
            "always verify root cause empirically before guessing",
        ]
        result = cluster_by_similarity(texts)
        clusters_as_sets = [set(c) for c in result]
        assert {0, 1} in clusters_as_sets
        assert any(c == {2} for c in clusters_as_sets)

    def test_every_index_appears_exactly_once(self):
        texts = ["a", "b totally different concept", "c yet another idea", "a"]
        result = cluster_by_similarity(texts)
        all_indices = [i for cluster in result for i in cluster]
        assert sorted(all_indices) == list(range(len(texts)))

    def test_handles_dozens_of_contracts_quickly(self):
        """The real scale that exposed the pairwise-loop bug: dozens of
        contracts across many projects must cluster in well under a
        minute, not time out."""
        import time
        texts = [f"contract number {i} about topic {i % 7}" for i in range(60)]
        t0 = time.time()
        result = cluster_by_similarity(texts)
        elapsed = time.time() - t0
        assert elapsed < 15  # batched encode + matrix ops, not 60 individual model calls
        assert sum(len(c) for c in result) == 60
