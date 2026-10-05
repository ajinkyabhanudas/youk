"""A worktree belongs to the repository it was made from; everything else keeps its basename."""
from __future__ import annotations

import subprocess
from pathlib import Path

import project_identity as pi


def _repo_with_worktree(tmp_path):
    main = tmp_path / "youk"
    main.mkdir()
    run = lambda *a, cwd=main: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (main / "f").write_text("x")
    run("add", "-A")
    run("commit", "-q", "-m", "c")
    tree = tmp_path / "youk-vp"
    run("worktree", "add", "-q", "-b", "side", str(tree))
    return main, tree


class TestWorktree:
    def test_a_worktree_has_its_repositorys_slug(self, tmp_path):
        main, tree = _repo_with_worktree(tmp_path)
        assert pi.project_slug(str(tree)) == "youk"
        assert pi.project_root(str(tree)) == str(main.resolve()) or pi.project_root(str(tree)) == str(main)

    def test_the_main_checkout_is_unchanged(self, tmp_path):
        main, _ = _repo_with_worktree(tmp_path)
        assert pi.project_slug(str(main)) == "youk"
        assert pi.project_root(str(main)) == str(main)

    def test_an_ordinary_directory_keeps_its_basename(self, tmp_path):
        plain = tmp_path / "stencil"
        plain.mkdir()
        assert pi.project_slug(str(plain)) == "stencil"

    def test_a_submodule_style_gitfile_is_not_mistaken_for_a_worktree(self, tmp_path):
        sub = tmp_path / "libfoo"
        sub.mkdir()
        (sub / ".git").write_text("gitdir: ../.git/modules/libfoo\n")
        assert pi.project_slug(str(sub)) == "libfoo"

    def test_garbage_gitfile_and_empty_inputs_fall_back_quietly(self, tmp_path):
        odd = tmp_path / "odd"
        odd.mkdir()
        (odd / ".git").write_text("")
        assert pi.project_slug(str(odd)) == "odd"
        assert pi.project_slug("") == "unknown"


class TestContainerPaths:
    def test_the_resolver_is_used_to_read_the_gitfile_but_the_root_stays_a_host_path(self, tmp_path):
        """In a container the host path does not exist; the mount lives under another prefix."""
        mount = tmp_path / "mount" / "youk-vp"
        mount.mkdir(parents=True)
        (mount / ".git").write_text("gitdir: /Users/me/code/youk/.git/worktrees/youk-vp\n")
        resolve = lambda p: mount  # noqa: E731
        assert pi.project_root("/Users/me/code/youk-vp", resolve) == "/Users/me/code/youk"
        assert pi.project_slug("/Users/me/code/youk-vp", resolve) == "youk"


class TestEveryCallerUsesIt:
    def test_no_code_derives_a_slug_from_a_basename_any_more(self):
        repo = Path(__file__).parent.parent
        offenders = []
        for root in ("servers", "plugin"):
            for path in (repo / root).rglob("*.py"):
                if path.name == "project_identity.py":
                    continue
                text = path.read_text(encoding="utf-8")
                if ".name or \"unknown\"" in text:
                    offenders.append(str(path.relative_to(repo)))
        assert offenders == [], f"derive the slug with project_identity.project_slug: {offenders}"
