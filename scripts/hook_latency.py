#!/usr/bin/env python3
"""Wall-clock latency of the usage tap, including interpreter start.

The ledger's own `hook` events time only the script body. The 50 ms budget in
docs/value-plan is about the whole call, so this measures the whole call.

    python3 scripts/hook_latency.py [runs]
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TAP = Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "usage_tap.py"
PAYLOAD = json.dumps({
    "hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "/work/proj",
    "tool_input": {"command": "uv run pytest -q"}, "tool_response": {"exit_code": 0},
    "session_id": "bench", "tool_use_id": "toolu_bench", "duration": 10,
})


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    root = tempfile.mkdtemp()
    env = {**os.environ, "YOUK_ROOT": root}
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run([sys.executable, "-S", str(TAP)], input=PAYLOAD, text=True, env=env,
                       capture_output=True)
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    print(f"{runs} runs  p50 {statistics.median(samples):.0f} ms  p95 {p95:.0f} ms  max {samples[-1]:.0f} ms")


if __name__ == "__main__":
    main()
