"""Reusable A/B experiment infrastructure for youk skill behaviour.

Built from ~/Desktop/AB-Tests/ab-test-plan.md, deferred from that project to be
picked up here once the deploy path (YOUK_ROOT = Path("/youk") inside the running
containers) was known.

Two pieces, deliberately separable:
    assign_variant()  — deterministic session-hash variant assignment, generalizes to
                         any experiment, not just the rationale-text pilot.
    log_exposure()    — append-only exposure log, ADR-011 compliant.

The specific rationale_why vs rationale_why_terse pilot is wired in skills.py; this
module knows nothing about rationale text or skills, only about assigning and logging
variants for a named experiment. That separation is the plan's own definition of done
for the infra half: reusable, independent of the specific pilot.

Randomization unit is SESSION (per the plan): one session gets one variant per
experiment, consistently, for every skill that experiment touches. A session that
sees nfr-check twice gets the same variant both times.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

VARIANTS = ("control", "treatment")


def assign_variant(session_slug: str, experiment: str) -> str:
    """Deterministic 50/50 split, stable for the lifetime of (session, experiment).

    Hashing (session_slug, experiment) together rather than session_slug alone means
    a session gets independent assignments across different experiments — the same
    session isn't locked into "always treatment" for everything just because it drew
    treatment once.

    Deterministic and side-effect-free by design: callable any number of times without
    needing to read back a stored assignment, and safe to call before deciding whether
    logging the exposure is even possible.
    """
    key = f"{session_slug}:{experiment}".encode()
    digest = hashlib.sha256(key).digest()
    return VARIANTS[digest[0] % 2]


def _exposure_path(youk_root: Path) -> Path:
    return youk_root / "state" / "ab-exposures.json"


def log_exposure(
    youk_root: Path,
    session_slug: str,
    experiment: str,
    skill: str,
    variant: str,
) -> None:
    """Append one exposure record. Idempotent per (session, experiment, skill).

    ADR-011 applies exactly as it does to trace metadata: session_slug is hashed
    before it touches disk, and nothing here carries task text, rationale content, or
    any other session content. Only the identifiers needed to compute an exposure
    rate per experiment per skill.

    Silent-fail on any write error — an exposure log must never be able to block
    routing. A missed log entry costs a slightly under-counted pilot; a routing
    failure costs the developer's session.
    """
    try:
        session_hash = hashlib.sha256(session_slug.encode("utf-8")).hexdigest()[:16]
        path = _exposure_path(youk_root)
        path.parent.mkdir(parents=True, exist_ok=True)

        records: list[dict] = []
        if path.exists():
            try:
                records = json.loads(path.read_text())
                if not isinstance(records, list):
                    records = []
            except Exception:
                records = []

        dedup_key = (session_hash, experiment, skill)
        if any(
            (r.get("session_hash"), r.get("experiment"), r.get("skill")) == dedup_key
            for r in records
        ):
            return

        records.append({
            "session_hash": session_hash,
            "experiment": experiment,
            "skill": skill,
            "variant": variant,
            "ts": datetime.now(UTC).isoformat(),
        })

        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=1))
        tmp.replace(path)
    except Exception:
        pass


def pilot_status(youk_root: Path, experiment: str, threshold: int = 20) -> dict:
    """Count exposures per variant against the pre-registered stop threshold.

    Does NOT compute a readout. Per the plan's pre-registration ("analyze once,
    no peeking"), producing a comparison before the threshold is reached is exactly
    the failure mode pre-registration exists to prevent: a peek changes what "once"
    means, and a stop condition decided after seeing partial data is not a stop
    condition. This function draws the line the readout logic must respect — it
    reports counts and a boolean, nothing that could be read as a verdict.

    The comparison itself (joining against autonomy_depth trend) is deliberately
    not built here. It has no reason to exist before there is data to compare, and
    building it early is the same premature-infrastructure trap the plan's own
    reframing already named once for this project.

    Returns: {experiment, threshold, total, by_variant, ready, remaining}.
    ready=True only once total >= threshold. remaining is never negative.
    """
    exposures = read_exposures(youk_root, experiment)
    total = len(exposures)
    by_variant: dict[str, int] = {v: 0 for v in VARIANTS}
    for e in exposures:
        v = e.get("variant")
        if v in by_variant:
            by_variant[v] += 1
    return {
        "experiment": experiment,
        "threshold": threshold,
        "total": total,
        "by_variant": by_variant,
        "ready": total >= threshold,
        "remaining": max(threshold - total, 0),
    }


def read_exposures(youk_root: Path, experiment: str | None = None) -> list[dict]:
    """Read logged exposures, optionally filtered to one experiment.

    Used by the comparison harness (not yet built — the plan's step after infra is
    validated) and by the smoke test to confirm a run actually landed on disk.
    """
    path = _exposure_path(youk_root)
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text())
        if not isinstance(records, list):
            return []
    except Exception:
        return []
    if experiment is None:
        return records
    return [r for r in records if r.get("experiment") == experiment]
