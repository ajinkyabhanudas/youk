"""Mode coverage view — the coverage tree generalized across reasoning modes.

The user's insight: challenge, stress-test, and nfr-check are ALL completeness claims wearing
prose. 'Did I attack every angle?' is the same question as 'did I cover every branch?'. A tree
is a better interface for a completeness claim than a paragraph you must read linearly — you
audit the SHAPE at a glance and descend only where a node looks thin or missing.

This adapter renders each mode's angle-set as the SAME coverage view (reusing Branch/Node from
coverage_tree), so the glanceable-completeness surface is uniform across modes.

CRITICAL (BUILD-SPEC D8): this is a VIEW GENERATED FROM THE PASS, never a second artifact the
model hand-authors. The mode already reasons over its angles; this only renders that reasoning
as a tree. If it became a thing written IN ADDITION to the reasoning, it would be more writing
— the original disease. So the input here is the angle-outcomes the mode already produced.

Pure rendering. No API.
"""
from __future__ import annotations

from coverage_tree import Branch, Coverage, CoverageTree, Node

# The angle-sets each mode reasons over. These mirror the modes' own fixed lenses; they are
# self-revising judgment-sets (grow at the frontier via the modes' challenge discipline), NOT
# frozen — same contract as the coverage-tree templates.
MODE_ANGLES: dict[str, list[str]] = {
    "challenge": [
        "is this the right problem",
        "is there a simpler framing",
        "what are we assuming about the ask",
        "what fixed constraints bound this",
    ],
    "stress-test": [
        "scale",
        "edge cases",
        "hidden assumptions",
    ],
    "nfr-check": [
        "caching",
        "retry / timeout",
        "observability",
        "auth",
        "rate limits",
        "idempotency",
        "consistency",
        "data volume",
    ],
}


def view_from_outcomes(
    mode: str,
    target: str,
    outcomes: dict[str, Coverage],
    details: dict[str, str] | None = None,
) -> CoverageTree:
    """Render a mode's pass as a coverage tree.

    `outcomes` maps each angle the mode reasoned over to whether it was addressed. Any angle in
    MODE_ANGLES not present in `outcomes` is rendered MISSING — an angle the pass never reached
    is exactly the cheap-to-find gap the view exists to surface.

    Reuses the coverage-tree render/review_order, so a challenge pass, a stress-test, and an
    nfr-check all present the same glanceable completeness surface. adversary_status is left
    NOT_RUN unless the caller ran an independent adversary over the angle-set — we never imply
    a mode self-verified its own completeness (false-green anti-pattern).
    """
    details = details or {}
    angles = MODE_ANGLES.get(mode, list(outcomes.keys()))
    nodes: list[Node] = []
    for angle in angles:
        cov = outcomes.get(angle, Coverage.MISSING)
        nodes.append(Node(concept=angle, covered=cov, detail=details.get(angle, "")))
    tree = CoverageTree(task=f"{mode}: {target}")
    tree.branches.append(Branch(domain=mode, nodes=nodes))
    return tree
