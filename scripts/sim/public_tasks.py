"""Turn public benchmark instances into battery tasks and grade them in their own container.

Source: SWE-bench Multilingual (MIT, 300 instances, nine languages). Each instance carries a base
commit, an issue text, a test patch and the image its tests run in. The agent edits a shallow
checkout of the base commit on this machine. Grading takes the agent's diff and hands it to the
swebench harness, which applies the test patch and runs the tests inside the instance image.

    python scripts/sim/public_tasks.py fetch  --out /tmp/ml.json
    python scripts/sim/public_tasks.py sample --rows /tmp/ml.json --per-language 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PUBLIC_TASKS_DIR = REPO_ROOT / "bench" / "tasks-public"
DATASET = "SWE-bench/SWE-bench_Multilingual"
SOURCE = "swebench-multilingual"
ROWS_URL = ("https://datasets-server.huggingface.co/rows?dataset={ds}&config=default"
            "&split=test&offset={off}&length=100")

MIN_STATEMENT_CHARS = 200
MAX_FILES = 12
MAX_LINES = 500

LANGUAGE_OF_REPO = {
    "preactjs/preact": "javascript", "axios/axios": "javascript", "babel/babel": "javascript",
    "facebook/docusaurus": "javascript", "immutable-js/immutable-js": "javascript",
    "mrdoob/three.js": "javascript", "vuejs/core": "typescript",
    "projectlombok/lombok": "java", "apache/lucene": "java", "google/gson": "java",
    "apache/druid": "java", "javaparser/javaparser": "java", "reactivex/rxjava": "java",
    "rubocop/rubocop": "ruby", "fluent/fluentd": "ruby", "fastlane/fastlane": "ruby",
    "jekyll/jekyll": "ruby", "faker-ruby/faker": "ruby", "jordansissel/fpm": "ruby",
    "caddyserver/caddy": "go", "gin-gonic/gin": "go", "prometheus/prometheus": "go",
    "gohugoio/hugo": "go", "hashicorp/terraform": "go",
    "laravel/framework": "php", "briannesbitt/carbon": "php", "php-cs-fixer/php-cs-fixer": "php",
    "phpoffice/phpspreadsheet": "php",
    "redis/redis": "c", "jqlang/jq": "c", "micropython/micropython": "c", "valkey-io/valkey": "c",
    "fmtlib/fmt": "cpp", "nlohmann/json": "cpp",
    "tokio-rs/tokio": "rust", "tokio-rs/axum": "rust", "sharkdp/bat": "rust",
    "astral-sh/ruff": "rust", "nushell/nushell": "rust", "uutils/coreutils": "rust",
    "burntsushi/ripgrep": "rust",
}

_DIFF_FILE = re.compile(r"^diff --git a/(\S+) b/", re.MULTILINE)


def fetch_rows(dataset: str = DATASET, total: int = 300) -> list[dict]:
    """All rows through the public datasets server, 100 per page."""
    rows: list[dict] = []
    for off in range(0, total, 100):
        with urllib.request.urlopen(ROWS_URL.format(ds=dataset, off=off), timeout=60) as resp:
            rows += [r["row"] for r in json.load(resp)["rows"]]
    return rows


def diff_files(patch: str) -> list[str]:
    return _DIFF_FILE.findall(patch)


def diff_lines(patch: str) -> int:
    return sum(1 for ln in patch.splitlines()
               if ln[:1] in "+-" and not ln.startswith(("+++", "---")))


def language_of(row: dict) -> str | None:
    return LANGUAGE_OF_REPO.get(row["repo"])


def reject_reason(row: dict) -> str | None:
    """None if the instance can be used as a battery task, else why not."""
    if not language_of(row):
        return f"unknown language for {row['repo']}"
    if len(row["problem_statement"].strip()) < MIN_STATEMENT_CHARS:
        return "problem statement too short to specify the change"
    n_files, n_lines = len(diff_files(row["patch"])), diff_lines(row["patch"])
    if n_files > MAX_FILES or n_lines > MAX_LINES:
        return f"{n_files} files and {n_lines} lines"
    if not diff_files(row["test_patch"]):
        return "no test patch"
    if not row.get("FAIL_TO_PASS"):
        return "no failing test to fix"
    return None


def to_task(row: dict) -> dict:
    owner_repo = row["repo"]
    patch_files = diff_files(row["patch"])
    return {
        "id": f"ml-{row['instance_id']}",
        "repo": owner_repo.replace("/", "__"),
        "language": language_of(row),
        "sha": row["base_commit"],
        "parent_sha": row["base_commit"],
        "prompt": row["problem_statement"].strip(),
        "test_cmd": "",
        "hidden_tests": diff_files(row["test_patch"]),
        "runnable_tests": list(row["FAIL_TO_PASS"]),
        "added_tests": [],
        "interface": [],
        "source_files": patch_files,
        "files": len(patch_files),
        "lines": diff_lines(row["patch"]),
        "review": {"fair": None, "note": ""},
        "public": {
            "source": SOURCE,
            "instance_id": row["instance_id"],
            "github": owner_repo,
            "image": row["image"],
            "log_parser": row.get("log_parser", ""),
            "fail_to_pass": list(row["FAIL_TO_PASS"]),
            "pass_to_pass": list(row["PASS_TO_PASS"]),
        },
    }


def sample(rows: list[dict], per_language: int, taken: set[str] | None = None) -> list[dict]:
    """Up to per_language usable instances per language, spread across repos, largest diffs first, since bigger fixes are less likely to be at the ceiling."""
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["instance_id"] in (taken or set()) or reject_reason(row):
            continue
        by_lang[language_of(row)].append(row)
    picked: list[dict] = []
    for lang in sorted(by_lang):
        per_repo: dict[str, list[dict]] = defaultdict(list)
        for row in sorted(by_lang[lang], key=lambda r: -diff_lines(r["patch"])):
            per_repo[row["repo"]].append(row)
        chosen: list[dict] = []
        while len(chosen) < per_language and any(per_repo.values()):
            for repo in sorted(per_repo):
                if per_repo[repo] and len(chosen) < per_language:
                    chosen.append(per_repo[repo].pop(0))
        picked += chosen
    return picked


def write_task(task: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{task['id']}.yaml"
    path.write_text(yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    return path


# ---- checkout and grading ---------------------------------------------------------------------

def prepare_checkout(task: dict, dest: Path, remote: str | None = None) -> None:
    """A shallow checkout of the base commit. The test patch is not applied: the agent must not
    see the tests, and the harness applies them itself when it grades."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    url = remote or f"https://github.com/{task['public']['github']}"
    for cmd in (["init", "--quiet"], ["remote", "add", "origin", url],
                ["fetch", "--quiet", "--depth", "1", "origin", task["sha"]],
                ["checkout", "--quiet", "--detach", "FETCH_HEAD"]):
        subprocess.run(["git", "-C", str(dest), *cmd], check=True, capture_output=True)


def agent_patch(workdir: Path, base: str) -> str:
    """Everything the agent changed against the base commit, new files included."""
    subprocess.run(["git", "-C", str(workdir), "add", "-A"], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(workdir), "diff", "--cached", "--binary", base],
                          capture_output=True, text=True, check=True).stdout


def harness_command(predictions: Path, run_id: str, instance_id: str, report_dir: Path,
                    dataset: str = DATASET) -> list[str]:
    return ["uv", "run", "--with", "swebench", "python", "-m", "swebench.harness.run_evaluation",
            "--dataset_name", dataset, "--predictions_path", str(predictions),
            "--instance_ids", instance_id, "--run_id", run_id, "--max_workers", "1",
            "--timeout", "1800", "--report_dir", str(report_dir)]


def run_harness(predictions: Path, run_id: str, cwd: Path, instance_id: str, image: str) -> None:
    # The instance images are x86_64 only. The harness pulls through the docker SDK, which ignores
    # the platform setting, so the image is pulled here first and an arm64 host runs it emulated.
    subprocess.run(["docker", "pull", "--quiet", "--platform", "linux/amd64", image], check=True,
                   capture_output=True, text=True)
    env = {**os.environ, "DOCKER_DEFAULT_PLATFORM": "linux/amd64"}
    subprocess.run(harness_command(predictions, run_id, instance_id, cwd), cwd=cwd, check=True,
                   capture_output=True, text=True, env=env)


def resolved_in(report_dir: Path, instance_id: str) -> bool | None:
    """True or False from the harness report for one instance, None if no report was written."""
    for report in report_dir.glob("*.json"):
        try:
            data = json.loads(report.read_text())
        except json.JSONDecodeError:
            continue
        if "resolved_ids" in data:
            if instance_id in data["resolved_ids"]:
                return True
            return False if instance_id in data.get("unresolved_ids", []) else None   # errors have no verdict
    return None


def grade(task: dict, workdir: Path, scratch: Path, run=run_harness) -> bool | None:
    """Did the agent's diff make the failing tests pass without breaking the passing ones.
    None when the harness did not produce a verdict, which the runner treats as infrastructure."""
    info = task["public"]
    patch = agent_patch(workdir, task["sha"])
    if not patch.strip():
        return False                                  # an empty diff cannot fix anything
    run_id = f"youk-{info['instance_id']}".replace("/", "_")
    scratch.mkdir(parents=True, exist_ok=True)
    predictions = scratch / f"{run_id}.jsonl"
    predictions.write_text(json.dumps({"instance_id": info["instance_id"],
                                       "model_name_or_path": "youk-bench", "model_patch": patch}) + "\n")
    try:
        run(predictions, run_id, scratch, info["instance_id"], info["image"])
    except (subprocess.CalledProcessError, OSError):
        return None
    return resolved_in(scratch, info["instance_id"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download all instances once")
    f.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("sample", help="write task files for a language-balanced sample")
    s.add_argument("--rows", type=Path, required=True)
    s.add_argument("--per-language", type=int, default=3)
    s.add_argument("--out", type=Path, default=PUBLIC_TASKS_DIR)
    s.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        rows = fetch_rows()
        args.out.write_text(json.dumps(rows))
        print(f"{len(rows)} instances to {args.out}")
        return 0
    rows = json.loads(args.rows.read_text())
    have = {p.stem for p in args.out.glob("*.yaml")} if args.skip_existing else set()
    picked = [r for r in sample(rows, args.per_language) if f"ml-{r['instance_id']}" not in have]
    for row in picked:
        write_task(to_task(row), args.out)
    langs = defaultdict(int)
    for row in picked:
        langs[language_of(row)] += 1
    print(f"{len(picked)} tasks: {dict(sorted(langs.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
