"""Mechanical contracts, compiled into code (S12).

A contract that is a plain rule about a shell command ("never push to main", "never read .env")
does not need the model to remember it. S07 classified 16 of 208 saved contracts as mechanical;
the ones that can be decided from a Bash command and the git state are enforced here, by the
PreToolUse hook, so they cost no always-on tokens and cannot be skipped.

Design limits, stated so a reviewer can judge them:
- Only Bash commands are checked. Reading a file with the Read tool is not (a hook on every Read
  costs a process start per call); for that, deny it in settings with `Read(**/.env*)`.
- Pattern checks work on the command text. A command built through a variable or a script is not
  seen. This is a guard against the model's mistakes, not a sandbox.
- Rules prefer a miss to a false block: secrets and screenshots are checked on files being
  newly added, not on every tracked file.

`YOUK_GUARD_OFF=rule-id,other-id` (or `all`) turns rules off for a session. That is an explicit
decision by whoever launched it.

Stdlib only and import-light: the hook starts a fresh interpreter for each call.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_BRANCHES = frozenset({"main", "master"})

# id -> (what the contract says, what to do instead)
RULES: dict[str, tuple[str, str]] = {
    "commit-on-default-branch": (
        "Commits go on a branch, never on the default branch.",
        "Create a branch first: git switch -c <name>."),
    "push-to-default-branch": (
        "Never push to the default branch; open a PR from a feature branch.",
        "Push your branch: git push -u origin <branch>."),
    "force-push": (
        "No force push. It rewrites shared history.",
        "Use --force-with-lease on your own branch, after saying why."),
    "no-verify": (
        "No --no-verify. It skips the pre-commit contracts and cannot be audited.",
        "Fix what the hook reports, then commit normally."),
    "staged-screenshot": (
        "Screenshot files from testing must never be committed.",
        "Unstage them: git restore --staged <file>, and add them to .gitignore."),
    "staged-secret": (
        "Secrets and key files must never be committed.",
        "Unstage the file, rotate the secret if it was ever committed, and add it to .gitignore."),
    "read-dotenv": (
        "Never read .env or secret files directly; load them into the environment instead.",
        "Source the file in your own shell (set -a; source .env; set +a) without printing it."),
    "dependency-force": (
        "No --force or --legacy-peer-deps on installs. It hides a real conflict.",
        "Resolve the conflicting versions."),
    "voice-pr-text": (
        "PR titles and bodies are written in the developer's voice, with no AI-tells.",
        "Rewrite it plain and short, see docs/voice-style.md, and run check_voice on the draft."),
}

_SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
_DOTENV = re.compile(r"^\.env(\..+)?$")
_DOTENV_SAFE_SUFFIX = {"example", "sample", "template", "dist", "defaults"}
_READERS = frozenset({"cat", "head", "tail", "less", "more", "bat", "nl", "tac", "grep", "egrep",
                      "fgrep", "rg", "sed", "awk", "cut", "sort", "strings", "xxd", "od", "diff",
                      "wc", "jq", "tee"})
_SCREENSHOT = re.compile(r"(?i)(^|/)(screenshots?|screen-shots?|\.playwright[^/]*)/|"
                         r"(^|/)[^/]*screenshot[^/]*\.(png|jpe?g|gif|webp)$")
_SECRET_FILE = re.compile(r"(?i)(^|/)(\.env(\..+)?|id_rsa[^/]*|id_ed25519[^/]*|[^/]+\.(pem|p12|pfx|key)|"
                          r"credentials\.json|service-account[^/]*\.json)$")
_PACKAGE_MANAGERS = frozenset({"npm", "pnpm", "yarn"})
_INSTALL_VERBS = frozenset({"install", "i", "ci", "add", "update", "upgrade"})


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str

    def text(self) -> str:
        said, instead = RULES[self.rule]
        return (f"[YOUK contract: {self.rule}] {said} {self.message} {instead} "
                f"(Deliberate exception: launch with YOUK_GUARD_OFF={self.rule}.)")


def _enabled(rule: str) -> bool:
    off = {x.strip() for x in os.environ.get("YOUK_GUARD_OFF", "").split(",") if x.strip()}
    return "all" not in off and rule not in off


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=False, posix=True)
    except ValueError:
        return segment.split()


def _git_call(tokens: list[str]) -> tuple[str, list[str], str | None] | None:
    """(subcommand, arguments after it, -C directory) for a `git ...` segment, else None."""
    if not tokens or os.path.basename(tokens[0]) != "git":
        return None
    i, directory = 1, None
    while i < len(tokens):
        t = tokens[i]
        if t == "-C" and i + 1 < len(tokens):
            directory, i = tokens[i + 1], i + 2
        elif t == "-c" and i + 1 < len(tokens):
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t, tokens[i + 1:], directory
    return None


def _run_git(cwd: str, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def current_branch(cwd: str) -> str:
    return _run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD").strip()


def _creates_or_switches_branch(sub: str, args: list[str]) -> bool:
    if sub == "switch":
        return True
    if sub == "checkout":
        return any(a in ("-b", "-B") for a in args) or (
            bool(args) and not args[0].startswith("-") and args[0] not in DEFAULT_BRANCHES)
    return False


def _pushed_refs(args: list[str]) -> list[str]:
    positional = [a for a in args if not a.startswith("-")]
    return positional[1:]            # first positional is the remote


def _short_cluster(args: list[str], letter: str) -> bool:
    return any(re.fullmatch(rf"-[a-zA-Z]*{letter}[a-zA-Z]*", a) for a in args)


def _is_dotenv(path: str) -> bool:
    name = os.path.basename(path.rstrip("/"))
    if not _DOTENV.match(name):
        return False
    return name.split(".")[-1] not in _DOTENV_SAFE_SUFFIX or name == ".env"


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\s*\2\b", re.DOTALL)
_PR_COMMAND = re.compile(r"\bgh\s+pr\s+(create|edit)\b")
_BODY_FLAG = re.compile(r"""(?:--body|-b)\s+(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""", re.DOTALL)
_TITLE_FLAG = re.compile(r"""(?:--title|-t)\s+(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""", re.DOTALL)
_BODY_FILE = re.compile(r"--body-file\s+(\S+)")
_LONG_QUOTE = re.compile(r"""("(?:[^"\\]|\\.){60,}"|'[^']{60,}')""", re.DOTALL)


def _pr_texts(command: str, cwd: str) -> list[str]:
    """Title and body text of a `gh pr create|edit`, whether given inline, as a heredoc or as a file."""
    if not _PR_COMMAND.search(command):
        return []
    texts = [m.group(3) for m in _HEREDOC.finditer(command)]
    for pattern in (_TITLE_FLAG, _BODY_FLAG):
        for m in pattern.finditer(command):
            value = m.group(1) if m.group(1) is not None else m.group(2)
            if value and "<<" not in value and "$(" not in value:
                texts.append(value)
    for m in _BODY_FILE.finditer(command):
        path = m.group(1).strip("'\"")
        full = path if os.path.isabs(path) else os.path.join(cwd, path)
        try:
            with open(full, encoding="utf-8") as fh:
                texts.append(fh.read(20000))
        except OSError:
            pass
    return texts


def _mask_text_bodies(command: str) -> str:
    """Blank out heredoc bodies and long quoted strings (commit messages, PR bodies) so prose that
    mentions `git push origin main` is never read as a command."""
    masked = _HEREDOC.sub(lambda m: m.group(0).replace(m.group(3), " "), command)
    return _LONG_QUOTE.sub('" "', masked)


def evaluate_bash(command: str, cwd: str,
                  voice_check: Callable[[str], list[str]] | None = None) -> list[Violation]:
    """Every contract the command would break, in order. Empty when it is fine.
    voice_check(text) returns the AI-tells in a text (empty when clean); the hook passes the
    voice gate here so the guard stays free of imports from the core server code."""
    found: list[Violation] = []
    switched = False
    if voice_check is not None:
        for text in _pr_texts(command, cwd):
            tells = voice_check(text)
            if tells:
                found.append(Violation("voice-pr-text", "Tells found: " + "; ".join(tells[:4]) + "."))
    for segment in _SEGMENT_SPLIT.split(_mask_text_bodies(command).strip()):
        tokens = _tokens(segment)
        if not tokens:
            continue
        git = _git_call(tokens)
        if git:
            sub, args, directory = git
            where = directory if directory and os.path.isabs(directory) else (
                os.path.join(cwd, directory) if directory else cwd)
            if _creates_or_switches_branch(sub, args):
                switched = True
            if sub in ("commit", "push") and (
                    "--no-verify" in args or (sub == "commit" and _short_cluster(args, "n"))):
                found.append(Violation("no-verify", "The command passes --no-verify."))
            if sub == "commit":
                if not switched and current_branch(where) in DEFAULT_BRANCHES:
                    found.append(Violation(
                        "commit-on-default-branch",
                        f"You are on '{current_branch(where)}'."))
                added = _run_git(where, "diff", "--cached", "--name-only", "--diff-filter=A", "-z")
                for name in filter(None, added.split("\0")):
                    if _SCREENSHOT.search(name):
                        found.append(Violation("staged-screenshot", f"Staged: {name}."))
                    elif _SECRET_FILE.search(name) and not name.endswith(
                            tuple(f".{s}" for s in _DOTENV_SAFE_SUFFIX)):
                        found.append(Violation("staged-secret", f"Staged: {name}."))
            if sub == "push":
                forced = ("--force" in args or _short_cluster(args, "f")) and not any(
                    a.startswith("--force-with-lease") for a in args)
                if forced:
                    found.append(Violation("force-push", "The push is forced."))
                if "--delete" not in args and "-d" not in args:
                    refs = _pushed_refs(args)
                    targets = [r.split(":")[-1].removeprefix("refs/heads/") for r in refs]
                    if any(t in DEFAULT_BRANCHES for t in targets) or (
                            not refs and not switched and current_branch(where) in DEFAULT_BRANCHES):
                        found.append(Violation("push-to-default-branch",
                                               "The push targets the default branch."))
            continue
        name = os.path.basename(tokens[0])
        if name in _PACKAGE_MANAGERS and any(t in _INSTALL_VERBS for t in tokens[1:3]):
            if any(t in ("--legacy-peer-deps", "--force") for t in tokens):
                found.append(Violation("dependency-force", "The install forces past a conflict."))
        if name in _READERS and any(_is_dotenv(t) for t in tokens[1:] if not t.startswith("-")):
            found.append(Violation("read-dotenv", "The command prints a .env file."))
    return [v for v in found if _enabled(v.rule)]


def first_violation(command: str, cwd: str,
                    voice_check: Callable[[str], list[str]] | None = None) -> Violation | None:
    found = evaluate_bash(command, cwd, voice_check)
    return found[0] if found else None
