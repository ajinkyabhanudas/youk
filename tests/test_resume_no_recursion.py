"""The permanent fix for resume-pointer staleness/recursion (Task 1).

For many sessions the resume-from line compounded into "Resume: Resume: Resume: ..."
because last session's resume was scraped into this session's summary and re-prefixed,
with no guard. These tests prove _update_resume_point can no longer persist that class
of corruption, at the writer level — regardless of what any call site passes it.
"""
from __future__ import annotations

from session import _strip_resume_wrapping, _update_resume_point


def _write_context(root, slug="youk"):
    proj = root / "knowledge" / "projects" / slug
    proj.mkdir(parents=True, exist_ok=True)
    ctx = proj / "context.md"
    ctx.write_text("# Project context: youk\n\nresume-from: old\n")
    return ctx


def _read_resume(ctx):
    for line in ctx.read_text().splitlines():
        if line.startswith("resume-from:"):
            return line[len("resume-from:"):].strip()
    return None


def test_strip_collapses_repeats_to_single_prefix():
    """Collapse repetition, but preserve ONE prefix — the outermost is semantic
    (session_start branches on startswith('Resume:'))."""
    text = "Resume: Resume: Resume: Last working on: build the store"
    # Outermost prefix preserved once; inner repetition and nested tags removed.
    assert _strip_resume_wrapping(text) == "Resume: build the store"


def test_strip_preserves_single_semantic_prefix():
    assert _strip_resume_wrapping("Last working on: auth refactor") == (
        "Last working on: auth refactor"
    )


def test_strip_is_noop_on_clean_text():
    assert _strip_resume_wrapping("NEXT = Task 1.2") == "NEXT = Task 1.2"


def test_writer_never_persists_recursion(youk_root):
    """The core guarantee: feed the writer the exact corruption, and what lands
    on disk has at most ONE prefix — the recursion cannot survive the write."""
    ctx = _write_context(youk_root)
    _update_resume_point(
        "youk", "Resume: Resume: Resume: Last working on: sub-task 1.2"
    )
    persisted = _read_resume(ctx)
    assert persisted is not None
    assert persisted.count("Resume:") <= 1
    assert persisted.count("Last working on:") == 0  # nested tag collapsed away
    assert "sub-task 1.2" in persisted


def test_writer_persists_clean_text_unchanged(youk_root):
    ctx = _write_context(youk_root)
    _update_resume_point("youk", "NEXT = Task 1.2 SQLite store")
    assert _read_resume(ctx) == "NEXT = Task 1.2 SQLite store"


def test_repeated_writes_do_not_compound(youk_root):
    """Simulate the exact failure loop: write, scrape it back, write again.
    After many cycles the pointer must still be clean — no compounding."""
    ctx = _write_context(youk_root)
    text = "sub-task 1.2 SQLite store"
    for _ in range(5):
        _update_resume_point("youk", text)
        # Simulate the old bug: next session prepends its own prefix to the scraped line
        text = "Resume: " + _read_resume(ctx)
    persisted = _read_resume(ctx)
    # The key guarantee: bounded, never compounding. At most one prefix after 5 cycles.
    assert persisted.count("Resume:") <= 1
    assert "sub-task 1.2" in persisted
