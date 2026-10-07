#!/usr/bin/env python3
"""Mine replayable tasks from a repo's git history (S08).

A task is a commit that changed source and tests together, small enough to be one
unit of work, whose tests fail on the parent code and pass at the commit. Its prompt is the
commit message's problem statement (subject and first paragraph), plus the new names the hidden
tests call (without them no agent could pass). A commit whose prompt names other identifiers the
commit introduces is rejected, since that describes the solution. The agent
gets the parent checkout with the commit's new tests removed and a prompt taken from
the commit message. Success is the hidden tests passing after the agent's change.

    python3 scripts/sim/mine_tasks.py                 mine every repo in bench/repos.yaml
    python3 scripts/sim/mine_tasks.py --repo youk     one repo
    python3 scripts/sim/mine_tasks.py --no-verify     list candidates without running tests
    python3 scripts/sim/mine_tasks.py --review        print prompts for the fairness review
"""
from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPOS_FILE = REPO_ROOT / "bench" / "repos.yaml"
TASKS_DIR = REPO_ROOT / "bench" / "tasks"

MAX_FILES = 4
MAX_LINES = 200
# tier m is the multi-file band above the small tier, where a workflow has room to matter
TIERS = {"s": (0, MAX_FILES, MAX_LINES), "m": (1, 12, 500)}
MIN_PROMPT_CHARS = 15
VERIFY_TIMEOUT_S = 300

CODE_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
}
DOC_EXT = {".md", ".txt", ".rst"}

_TEST_DIR = re.compile(r"(^|/)(tests?|__tests__|spec)/")
_TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.(py|go)|[^/]*\.(test|spec)\.[jt]sx?)$")
_TRAILER = re.compile(r"^(co-authored-by|signed-off-by|generated with|claude-session)\b.*$",
                      re.I | re.M)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_DEFINED = re.compile(r"\b(?:def|class|function|const|fn|func)\s+([A-Za-z_][A-Za-z0-9_]*)")
# snake_case, camelCase or PascalCase: shapes that mark code, so prose words in comments and
# strings do not count as leaks
_CODE_SHAPE = re.compile(r"_|[a-z][A-Z]|[A-Z][a-z]+[A-Z]")
_PR_REF = re.compile(r"\s*\(#\d+\)")
_EXTS = "|".join(e.lstrip(".") for e in [*CODE_EXT, *DOC_EXT])
_PATHLIKE = re.compile(rf"[\w./-]+\.(?:{_EXTS})\b")


@dataclass
class Candidate:
    sha: str
    parent: str
    message: str
    files: list[tuple[str, int, int]]  # path, added, deleted

    @property
    def lines(self) -> int:
        return sum(a + d for _, a, d in self.files)


@dataclass
class Task:
    id: str
    repo: str
    language: str
    sha: str
    parent_sha: str
    prompt: str
    test_cmd: str
    hidden_tests: list[str]      # every test-side file the commit touched; restored before grading
    runnable_tests: list[str]    # the subset the test command runs
    added_tests: list[str]       # removed from the agent's checkout
    interface: list[str]         # new names the hidden tests use; appended to the prompt
    source_files: list[str]
    files: int
    lines: int
    review: dict = field(default_factory=lambda: {"fair": None, "note": ""})


def is_test_path(path: str) -> bool:
    return bool(_TEST_DIR.search(path) or _TEST_FILE.search(path))


def is_runnable_test(path: str) -> bool:
    return bool(_TEST_FILE.search(path))


def language_of(path: str) -> str | None:
    return CODE_EXT.get(Path(path).suffix)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def history(repo: Path, limit: int | None = None) -> list[Candidate]:
    """Non-merge commits with one parent, newest first, with per-file line counts."""
    args = ["log", "--no-merges", "--no-renames", "--numstat",
            "--format=%x1e%H%x1f%P%x1f%B%x1f"]
    if limit:
        args.insert(1, f"-n{limit}")
    raw = _git(repo, *args)
    found: list[Candidate] = []
    for record in raw.split("\x1e")[1:]:
        sha, parents, message, stats = record.split("\x1f", 3)
        parent_list = parents.split()
        if len(parent_list) != 1:
            continue
        files = []
        for line in stats.strip().splitlines():
            added, deleted, path = line.split("\t", 2)
            # binary files report "-"; count them as a reject signal through a huge size
            files.append((path, int(added) if added != "-" else MAX_LINES + 1,
                          int(deleted) if deleted != "-" else MAX_LINES + 1))
        found.append(Candidate(sha, parent_list[0], message.strip(), files))
    return found


def select(cand: Candidate, tier: str = "s") -> str | None:
    """None if the commit qualifies, else the reason it does not."""
    _, max_files, max_lines = TIERS[tier]
    if not cand.files:
        return "no files"
    if len(cand.files) > max_files:
        return f"{len(cand.files)} files"
    if cand.lines > max_lines:
        return f"{cand.lines} lines"
    if tier != "s" and len(cand.files) <= MAX_FILES and cand.lines <= MAX_LINES:
        return "fits the small tier"
    tests = [p for p, _, _ in cand.files if is_test_path(p)]
    sources = [p for p, _, _ in cand.files if not is_test_path(p) and language_of(p)]
    others = [p for p, _, _ in cand.files
              if not is_test_path(p) and not language_of(p) and Path(p).suffix not in DOC_EXT]
    if others:
        return f"non-code file {others[0]}"
    if not sources:
        return "no source change"
    if not any(is_runnable_test(p) for p in tests):
        return "no runnable test change"
    if len(clean_prompt(cand.message, [p for p, _, _ in cand.files])) < MIN_PROMPT_CHARS:
        return "prompt too short once file names are stripped"
    return None


def problem_statement(message: str) -> str:
    """Subject line and first paragraph only. Later paragraphs of a commit message are where the
    solution, the changed names and the verification notes live, and they would hand it over."""
    text = _TRAILER.sub("", message).strip()
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(paragraphs[:2]).strip()


def clean_prompt(message: str, paths: list[str]) -> str:
    """The problem statement without PR refs or any file name, so it does not point at the fix."""
    text = problem_statement(message)
    text = _PR_REF.sub("", text)
    names = sorted({*paths, *(Path(p).name for p in paths), *(Path(p).stem for p in paths)},
                   key=len, reverse=True)
    for name in names:
        text = re.sub(rf"(?<![\w]){re.escape(name)}(?![\w])", "", text) if len(name) > 3 else text
    text = _PATHLIKE.sub("", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _code_names(line: str) -> set[str]:
    return {i for i in _IDENT.findall(line) if _CODE_SHAPE.search(i)} | set(_DEFINED.findall(line))


def new_identifiers(repo: Path, cand: Candidate) -> set[str]:
    """Code names the commit introduces in source files: in an added line, absent from the
    removed lines and from the parent's version of the file. A fair prompt cannot name them."""
    found: set[str] = set()
    for path, _, _ in cand.files:
        if is_test_path(path) or not language_of(path):
            continue
        diff = _git(repo, "show", "--format=", "--unified=0", cand.sha, "--", path)
        added = {i for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")
                 for i in _code_names(ln)}
        removed = {i for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")
                   for i in _code_names(ln)}
        parent_text = _git(repo, "show", f"{cand.parent}:{path}", check=False)
        found |= {i for i in added - removed if i not in parent_text}
    return found


def test_interface(repo: Path, cand: Candidate, new_names: set[str], runnable: list[str]) -> list[str]:
    """New names the hidden tests themselves use. The agent cannot guess these, so the prompt has
    to supply them; without them no arm could pass and the task would only add noise."""
    text = " ".join(_git(repo, "show", f"{cand.sha}:{p}", check=False) for p in runnable)
    used = set(_IDENT.findall(text)) & new_names
    return sorted(n for n in used if not (n.startswith("__") or n.startswith("test_")))[:8]


def leaked_names(prompt: str, new_names: set[str], interface: list[str] | None = None) -> list[str]:
    """New names the prompt mentions beyond the interface the tests need. A prompt that names the
    function to add, when the tests do not call it, is describing the solution."""
    return sorted(set(_IDENT.findall(prompt)) & (new_names - set(interface or [])))


def _expand(test_cmd: str, tests: list[str]) -> list[str]:
    """Split the command and substitute {tests}; {python} is the interpreter running the miner."""
    out: list[str] = []
    for part in shlex.split(test_cmd):
        if part == "{tests}":
            out.extend(tests)
        else:
            out.append(part.replace("{python}", sys.executable))
    return out


def run_tests(cwd: Path, test_cmd: str, tests: list[str], timeout: int = VERIFY_TIMEOUT_S) -> bool:
    try:
        done = subprocess.run(_expand(test_cmd, tests), cwd=cwd, capture_output=True,
                              timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0


class Worktree:
    """A detached checkout in a temp dir, removed on exit even if the body raises."""

    def __init__(self, repo: Path, rev: str):
        self.repo, self.rev = repo, rev
        self.path = Path(tempfile.mkdtemp(prefix="youk-mine-"))

    def __enter__(self) -> Path:
        _git(self.repo, "worktree", "add", "--detach", "--force", str(self.path), self.rev)
        return self.path

    def __exit__(self, *exc) -> None:
        _git(self.repo, "worktree", "remove", "--force", str(self.path), check=False)
        shutil.rmtree(self.path, ignore_errors=True)


def verify(repo: Path, cand: Candidate, test_cmd: str, runnable: list[str],
           setup: str | None = None) -> str | None:
    """None when the tests pass at the commit and fail on the parent code, else the reason."""
    with Worktree(repo, cand.sha) as at_commit:
        if setup and not _run_shell(at_commit, setup):
            return "setup failed at commit"
        if not run_tests(at_commit, test_cmd, runnable):
            return "tests fail at the commit"
    with Worktree(repo, cand.parent) as at_parent:
        if setup and not _run_shell(at_parent, setup):
            return "setup failed at parent"
        for path in runnable:
            target = at_parent / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_git(repo, "show", f"{cand.sha}:{path}"))
        if run_tests(at_parent, test_cmd, runnable):
            return "tests already pass on the parent"
    return None


def _run_shell(cwd: Path, command: str) -> bool:
    try:
        return subprocess.run(shlex.split(command), cwd=cwd, capture_output=True,
                              timeout=VERIFY_TIMEOUT_S).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def with_interface(prompt: str, interface: list[str]) -> str:
    if not interface:
        return prompt
    return (f"{prompt}\n\nThe tests for this change use these names (create or adapt them as "
            f"needed): {', '.join(interface)}.")


def build_task(repo_cfg: dict, cand: Candidate, interface: list[str] | None = None) -> Task:
    repo = Path(repo_cfg["path"]).expanduser()
    paths = [p for p, _, _ in cand.files]
    # a test file the commit deleted cannot be restored or run, so it is not part of the grade
    hidden = [p for p in paths if is_test_path(p) and not _missing_at(repo, cand.sha, p)]
    sources = [p for p in paths if not is_test_path(p) and language_of(p)]
    added = [p for p in hidden if _missing_at(repo, cand.parent, p)]
    return Task(
        id=f"{repo_cfg['name']}-{cand.sha[:8]}",
        repo=repo_cfg["name"],
        language=language_of(sources[0]) or repo_cfg.get("language", "unknown"),
        sha=cand.sha,
        parent_sha=cand.parent,
        prompt=with_interface(clean_prompt(cand.message, paths), interface or []),
        test_cmd=repo_cfg["test_cmd"],
        hidden_tests=hidden,
        runnable_tests=[p for p in hidden if is_runnable_test(p)],
        added_tests=added,
        interface=interface or [],
        source_files=sources,
        files=len(paths),
        lines=cand.lines,
    )


def _missing_at(repo: Path, rev: str, path: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{rev}:{path}"],
                          capture_output=True).returncode != 0


def mine_repo(repo_cfg: dict, limit: int, verify_tests: bool = True,
              log=lambda msg: None, tier: str = "s", skip: set[str] | None = None) -> list[Task]:
    repo = Path(repo_cfg["path"]).expanduser()
    tasks: list[Task] = []
    for cand in history(repo):
        if len(tasks) >= limit:
            break
        reason = select(cand, tier)
        if reason:
            continue
        if f"{repo_cfg['name']}-{cand.sha[:8]}" in (skip or set()):
            continue
        task = build_task(repo_cfg, cand)
        if not task.runnable_tests:
            continue
        new_names = new_identifiers(repo, cand)
        interface = test_interface(repo, cand, new_names, task.runnable_tests)
        leaks = leaked_names(task.prompt, new_names, interface)
        if leaks:
            log(f"  reject {cand.sha[:8]}: prompt names new identifiers {leaks[:3]}")
            continue
        task = build_task(repo_cfg, cand, interface)
        if verify_tests:
            reason = verify(repo, cand, task.test_cmd, task.runnable_tests, repo_cfg.get("setup"))
            if reason:
                log(f"  reject {cand.sha[:8]}: {reason}")
                continue
        tasks.append(task)
        log(f"  keep   {cand.sha[:8]} {task.language} {task.files}f/{task.lines}l")
    return tasks


def write_task(task: Task, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{task.id}.yaml"
    data = {k: getattr(task, k) for k in task.__dataclass_fields__}
    if path.exists():                       # a remine must not erase a human verdict
        previous = yaml.safe_load(path.read_text()) or {}
        data["review"] = previous.get("review", data["review"])
    path.write_text(yaml.safe_dump(data, sort_keys=False, width=100))
    return path


def load_tasks(tasks_dir: Path = TASKS_DIR) -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted(tasks_dir.glob("*.yaml"))]


def usable(tasks: list[dict]) -> list[dict]:
    """Tasks not marked unfair in review. `fair: null` (not yet reviewed) counts as usable."""
    return [t for t in tasks if (t.get("review") or {}).get("fair") is not False]


def summary(tasks: list[dict | Task]) -> str:
    rows = [t if isinstance(t, dict) else t.__dict__ for t in tasks]
    by_repo = Counter(r["repo"] for r in rows)
    by_lang = Counter(r["language"] for r in rows)
    lines = [f"{len(rows)} tasks",
             "by repo: " + ", ".join(f"{k} {v}" for k, v in sorted(by_repo.items())),
             "by language: " + ", ".join(f"{k} {v}" for k, v in sorted(by_lang.items()))]
    if len(rows) < 12:
        lines.append("kill criterion: fewer than 12 usable tasks, add another repo before S10")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repos", type=Path, default=REPOS_FILE)
    ap.add_argument("--out", type=Path, default=TASKS_DIR)
    ap.add_argument("--repo", help="mine only this repo name")
    ap.add_argument("--per-repo", type=int, default=8, help="cap per repo so no repo dominates")
    ap.add_argument("--no-verify", action="store_true", help="skip running tests (candidates only)")
    ap.add_argument("--tier", choices=sorted(TIERS), default="s",
                    help="s: up to 4 files and 200 lines. m: up to 12 files and 500 lines, above s")
    ap.add_argument("--skip-existing", action="store_true",
                    help="leave out commits that already have a task file, so a rerun resumes")
    ap.add_argument("--review", action="store_true", help="print prompts of written tasks")
    args = ap.parse_args(argv)

    if args.review:
        for t in load_tasks(args.out):
            print(f"--- {t['id']} ({t['files']}f/{t['lines']}l)\n{t['prompt']}\n")
        print(summary(load_tasks(args.out)))
        return 0

    cfg = yaml.safe_load(args.repos.read_text())["repos"]
    mined: list[Task] = []
    have = {p.stem for p in args.out.glob("*.yaml")} if args.skip_existing else set()
    for repo_cfg in cfg:
        if args.repo and repo_cfg["name"] != args.repo:
            continue
        print(f"{repo_cfg['name']}:", file=sys.stderr)
        tasks = mine_repo(repo_cfg, args.per_repo, not args.no_verify,
                          log=lambda m: print(m, file=sys.stderr), tier=args.tier, skip=have)
        for t in tasks:
            write_task(t, args.out)
        mined += tasks
    print(summary(mined))
    return 0


if __name__ == "__main__":
    sys.exit(main())
