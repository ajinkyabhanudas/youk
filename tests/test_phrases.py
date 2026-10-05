"""Each phrase list is defined once (servers/shared/phrases.py).

Three copies had drifted into three different jobs: the user-pushback list in the hook utils
(imported by a shared module, an inverted dependency), a loop-correction list inside session_end,
and a pasted copy of that one in a test, so the test checked the copy and not the code.
"""
from __future__ import annotations

import ast
from pathlib import Path

import phrases

REPO = Path(__file__).parent.parent


class TestPushback:
    def test_short_prompt_matches_anywhere(self):
        assert phrases.is_pushback("hmm, you missed the second case")
        assert phrases.is_pushback("Are you sure?")

    def test_long_prompt_matches_only_in_the_first_sixty_characters(self):
        padding = "please review this snippet of code that i pasted below for me. " * 3
        assert not phrases.is_pushback(padding + "are you sure")
        assert phrases.is_pushback("you missed one thing. " + padding)

    def test_neutral_prompt_does_not_match(self):
        assert not phrases.is_pushback("please add a docstring to the parser module")


class TestLoopCorrection:
    def test_detects_post_verdict_language(self):
        assert phrases.has_loop_correction("Developer said: you missed the rate-limit angle")
        assert phrases.has_loop_correction("the loop not dry after all")

    def test_ignores_an_ordinary_summary(self):
        assert not phrases.has_loop_correction("added the retry wrapper and tests")

    def test_is_a_different_list_from_pushback(self):
        """They overlap on a few phrases but are not the same list."""
        assert "unchallenged" in phrases.LOOP_CORRECTION_PHRASES
        assert "unchallenged" not in phrases.PUSHBACK_PHRASES
        assert "that's wrong" in phrases.PUSHBACK_PHRASES
        assert "that's wrong" not in phrases.LOOP_CORRECTION_PHRASES


class TestDefinedOnce:
    def test_no_other_file_defines_a_phrase_list(self):
        """A list literal holding these distinctive phrases anywhere else is a copy that will
        drift. Docstrings and comments that merely quote a phrase are fine; only list, tuple and
        set literals of three or more strings count."""
        markers = {"you missed", "angle unchallenged", "from now on", "that's wrong"}
        offenders = []
        for root in ("servers", "plugin", "scripts", "tests"):
            for path in (REPO / root).rglob("*.py"):
                if path.name in ("phrases.py", "test_phrases.py"):
                    continue
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if not isinstance(node, ast.List | ast.Tuple | ast.Set):
                        continue
                    strings = {e.value for e in node.elts
                               if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                    if len(strings) >= 3 and strings & markers:
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        assert offenders == [], f"phrase lists defined outside servers/shared/phrases.py: {offenders}"

    def test_the_old_names_still_resolve_to_the_shared_lists(self):
        import sys
        sys.path.insert(0, str(REPO / "plugin" / "scripts"))
        import youk_hook_utils
        import reaction_classifier
        assert youk_hook_utils._CORRECTION_PHRASES is phrases.PUSHBACK_PHRASES
        assert youk_hook_utils._is_correction is phrases.is_pushback
        assert reaction_classifier._CORRECTION_PHRASES is phrases.PUSHBACK_PHRASES
