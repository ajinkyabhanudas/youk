"""TASK_RELEVANCE_FLOOR is a number that decides whether a past task counts as
precedent. This runs the real embedding model over labelled pairs and fails if
the floor does not separate related tasks from unrelated ones, so the constant
is checked on every run where the model exists rather than asserted in a
comment. Skipped where the model cannot load (offline sandboxes)."""
from __future__ import annotations

import pytest

import semantic_similarity

# (a, b): the same kind of work on the same part of a system.
RELATED = [
    ("design a new architecture for the payment system", "redesign the architecture for the billing system"),
    ("add retry logic to the file uploader", "rework the retry behaviour of the uploader"),
    ("fix a typo in the README", "correct a spelling mistake in the readme"),
    ("add a unit test for the login handler", "write tests covering the login handler"),
    ("migrate the user table to a new schema", "change the database schema for users"),
    ("speed up the search endpoint", "optimise the slow search query"),
    ("rename a variable in the parser", "rename a function in the parser module"),
    ("add a dark mode toggle to settings", "implement a dark theme switch on the settings page"),
]

# Different kind of work on different parts of a system.
UNRELATED = [
    ("design a new architecture for the payment system", "rotate the log files weekly"),
    ("fix a typo in the README", "build a distributed task queue with leader election"),
    ("add retry logic to the file uploader", "update the colour of the footer links"),
    ("migrate the user table to a new schema", "write the release announcement for v2"),
    ("speed up the search endpoint", "rename a variable in the parser"),
    ("add a dark mode toggle to settings", "set up continuous deployment for the API"),
    ("add a unit test for the login handler", "choose a vendor for payment processing"),
    ("rename a variable in the parser", "plan the quarterly roadmap"),
]


@pytest.fixture(scope="module")
def scores():
    pytest.importorskip("sentence_transformers")
    try:
        semantic_similarity._model()
    except Exception as e:  # weights not downloadable here
        pytest.skip(f"embedding model unavailable: {e}")
    sim = semantic_similarity.similarity
    return [sim(a, b) for a, b in RELATED], [sim(a, b) for a, b in UNRELATED]


def test_floor_separates_related_from_unrelated_tasks(scores):
    related, unrelated = scores
    floor = semantic_similarity.TASK_RELEVANCE_FLOOR
    detail = f"related min={min(related):.2f} unrelated max={max(unrelated):.2f} floor={floor}"
    assert min(related) >= floor, f"floor drops a related task: {detail}"
    assert max(unrelated) < floor, f"floor admits an unrelated task: {detail}"


# (task, lesson): an abstracted lesson that does NOT bear on the task.
UNRELATED_LESSONS = [
    ("add a dark mode toggle to settings", "Retrying a flaky test without root-causing it hides a real bug."),
    ("rename a variable in the parser", "Rotate credentials on a fixed schedule, not only after an incident."),
    ("fix a typo in the README", "A database migration must be reversible before it ships."),
    ("speed up the search endpoint", "Release notes should name the user-visible change first."),
    ("write tests for the login handler", "Pin the base image digest, not just its tag."),
    ("update the footer link colours", "Idempotency keys must be stored before the side effect runs."),
]


def test_lesson_floor_admits_no_unrelated_lesson(scores):
    sim = semantic_similarity.similarity
    worst = max(sim(task, lesson) for task, lesson in UNRELATED_LESSONS)
    assert worst < semantic_similarity.LESSON_RELEVANCE_FLOOR, (
        f"an unrelated lesson scores {worst:.2f}, at or above LESSON_RELEVANCE_FLOOR "
        f"{semantic_similarity.LESSON_RELEVANCE_FLOOR}"
    )
