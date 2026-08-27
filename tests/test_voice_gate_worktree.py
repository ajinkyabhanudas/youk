"""The voice gate must inspect the message it is given, and never pass silently.

The gate existed, check_text was correct, and it caught nothing for an entire session.
It guessed the message path as root/".git"/"COMMIT_EDITMSG". In a worktree .git is a
FILE holding a gitdir pointer, so the guess missed, and the script exited 0 — which is
indistinguishable from a clean message.

Every commit in that session was made from a worktree. The message that reached main in
PR #95 contained an em dash and the gate reported nothing.

Two defects, and the second is the one worth keeping in mind: the gate ignored the path
git hands a commit-msg hook as argv[1], and it treated "cannot find my input" as "pass".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
_GATE = _REPO / "scripts" / "voice_gate_precommit.py"


def _run(msg_file: Path | None, break_git: bool = False) -> subprocess.CompletedProcess:
    import os

    args = [sys.executable, str(_GATE)]
    if msg_file is not None:
        args.append(str(msg_file))
    env = dict(os.environ)
    if break_git:
        # Force every resolution attempt to fail so the not-found branch is reached.
        # Without this, `git rev-parse --git-path` succeeds from inside the repo and
        # finds a real message, which is the fallback working correctly.
        env["GIT_DIR"] = "/nonexistent-gitdir"
    return subprocess.run(args, capture_output=True, text=True, cwd=str(_REPO),
                          timeout=30, env=env)


class TestGateReadsTheMessageItIsGiven:
    def test_em_dash_message_is_blocked(self, tmp_path):
        f = tmp_path / "COMMIT_EDITMSG"
        f.write_text("fix: a subject with an em dash — right here\n")
        r = _run(f)
        assert r.returncode == 1, f"gate passed an em dash: {r.stdout}"
        assert "em_dash" in r.stdout

    def test_clean_message_passes(self, tmp_path):
        f = tmp_path / "COMMIT_EDITMSG"
        f.write_text("fix: resolve the commit message path from argv\n\n"
                     "The gate guessed a path that does not exist in a worktree.\n")
        r = _run(f)
        assert r.returncode == 0, f"gate blocked a clean message: {r.stdout}"

    def test_comment_lines_are_ignored(self, tmp_path):
        """git's template comments must not be scored as prose."""
        f = tmp_path / "COMMIT_EDITMSG"
        f.write_text("fix: resolve the path from argv\n\n# comment with an em dash — here\n")
        assert _run(f).returncode == 0


class TestCannotPassSilently:
    def test_unresolvable_message_blocks(self, tmp_path):
        """The defect that let an entire session through.

        A gate that exits 0 when it cannot find its input reports the same thing as a
        gate that found nothing wrong. Blocking is recoverable in one command; a silent
        pass is not detectable at all.
        """
        r = _run(tmp_path / "does-not-exist", break_git=True)
        assert r.returncode == 1
        assert "could not locate" in r.stdout.lower()

    def test_block_message_names_what_was_tried(self, tmp_path):
        r = _run(tmp_path / "does-not-exist", break_git=True)
        assert "argv[1]" in r.stdout
        assert "rev-parse" in r.stdout


class TestHookForwardsTheArgument:
    def test_generated_hook_passes_dollar_one(self):
        """Without "$1" the script falls back to guessing, which is how this broke."""
        gen = (_REPO / "scripts" / "generate_commitmsg_hook.py").read_text()
        assert 'voice_gate_precommit.py "$1"' in gen

    def test_generated_hook_uses_python3(self):
        """`python` is absent on many systems; the hook must not depend on it."""
        gen = (_REPO / "scripts" / "generate_commitmsg_hook.py").read_text()
        assert "python3 scripts/voice_gate_precommit.py" in gen

    def test_hook_installs_into_the_shared_hooks_dir(self):
        """A worktree .git is a file and cannot hold a hooks directory."""
        gen = (_REPO / "scripts" / "generate_commitmsg_hook.py").read_text()
        assert "--git-common-dir" in gen


class TestFallbackChain:
    def test_bad_argv_falls_back_to_git_rev_parse(self, tmp_path):
        """A wrong argv[1] must not mean unchecked.

        Resolution order is argv[1], then `git rev-parse --git-path`, then the legacy
        guess. Only when all three fail does the gate block as unresolvable.
        """
        r = _run(tmp_path / "does-not-exist")
        assert "could not locate" not in r.stdout.lower(), (
            "fallback did not run; the gate gave up at argv[1]"
        )
