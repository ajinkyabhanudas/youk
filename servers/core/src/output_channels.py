"""Two channels — the core of the rework. Split youk's output BY CONSUMER, not by topic.

The disease: one undifferentiated max-depth stream does two incompatible jobs, so the human
reads 90% execution-reasoning to find the 10% that teaches, can't skim safely, stops reading.

The fix (BUILD-SPEC D1-D3):
  - EXECUTION channel — consumer is youk. Full internal reasoning happens and is auditable,
    but the DEFAULT surface is one line (the signal glance). Expand-on-demand returns the full
    trace. The human needs it to have HAPPENED, not to READ it.
  - COMPREHENSION channel — consumer is the human. Only load-bearing items (a real trade-off,
    an irreversible foreclosure, a reusable pattern) are admitted, and they are PACED: they
    accrue and surface as a digest at a natural boundary (task/session end), never per-step.
    Per-step teaching IS the firehose.

Everything here is a VIEW generated from reasoning that already occurred (D8) — never a second
artifact the model hand-authors, which would just be more writing (the original disease).

No API. Pure rendering over data the caller already has.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from confidence_signal import Signal


class Load(StrEnum):
    """Why a comprehension item is load-bearing. Only these three admit an item — the filter
    that keeps Channel 2 from becoming the firehose. Anything else stays in Channel 1."""
    TRADEOFF = "tradeoff"        # a real decision with a rejected alternative
    FORECLOSURE = "foreclosure"  # an irreversible door closed — the human may want to veto
    PATTERN = "pattern"          # a reusable pattern worth internalizing


# --- Channel 1: execution -----------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionStep:
    """One unit of work. `full_trace` is the complete reasoning (blast-radius, gate output,
    why-this-file). It EXISTS and is auditable — it is simply below the fold by default."""
    label: str
    signal: Signal
    full_trace: str

    def collapsed(self) -> str:
        """Default surface: the label + the glanceable signal. One line. This is all the
        human reads unless the signal makes them want more (D2 + progressive disclosure)."""
        return f"{self.label} · {self.signal.glance()}"

    def expanded(self) -> str:
        """On-demand: the full trace. Round-trips losslessly — expanding never fabricates or
        omits; it reveals exactly what happened."""
        return f"{self.collapsed()}\n{self.full_trace}"


# --- Channel 2: comprehension -------------------------------------------------------------

@dataclass(frozen=True)
class CompItem:
    """A load-bearing item admitted to the comprehension channel. `kind` is WHY it teaches;
    `takeaway` is the one thing the human's mental model should update with."""
    kind: Load
    takeaway: str
    context: str = ""  # optional: what it attaches to (a file, a decision) — not required


@dataclass
class ComprehensionDigest:
    """Accrues load-bearing items across a task/session; emits ONCE at a boundary (paced).

    The pacing is the whole point: admitting items is cheap and continuous, but they SURFACE
    only when render() is called at a natural boundary — never per-step. An empty digest
    renders to empty (honest: nothing load-bearing happened is a valid, common outcome).
    """
    items: list[CompItem] = field(default_factory=list)

    def admit(self, item: CompItem) -> None:
        """Add a load-bearing item. Caller is responsible for only admitting genuinely
        load-bearing reasoning — the CompItem.kind is the contract that it qualifies."""
        self.items.append(item)

    def render(self) -> str:
        """The paced digest, grouped by kind so foreclosures (vetoable) read first. Empty
        input → empty output; we never manufacture teaching where none occurred."""
        if not self.items:
            return ""
        order = [Load.FORECLOSURE, Load.TRADEOFF, Load.PATTERN]
        headers = {
            Load.FORECLOSURE: "Foreclosed (veto if wrong)",
            Load.TRADEOFF: "Trade-offs made",
            Load.PATTERN: "Patterns worth keeping",
        }
        lines: list[str] = []
        for kind in order:
            group = [i for i in self.items if i.kind is kind]
            if not group:
                continue
            lines.append(f"## {headers[kind]}")
            for i in group:
                suffix = f"  ({i.context})" if i.context else ""
                lines.append(f"- {i.takeaway}{suffix}")
        return "\n".join(lines)


# --- combined per-task view ---------------------------------------------------------------

@dataclass
class TaskView:
    """What the human sees for a task by default: the execution ledger (collapsed lines) plus
    the paced comprehension digest. The full traces and the coverage tree are reachable but
    NOT resident. This is the 'write less' surface."""
    steps: list[ExecutionStep] = field(default_factory=list)
    digest: ComprehensionDigest = field(default_factory=ComprehensionDigest)

    def ledger(self) -> str:
        """Channel 1, default: one collapsed line per step. The scannable log."""
        return "\n".join(s.collapsed() for s in self.steps)

    def render(self) -> str:
        """Default task surface: ledger, then digest if non-empty. Deliberately compact."""
        parts = [self.ledger()]
        digest = self.digest.render()
        if digest:
            parts.append("\n— comprehension digest —\n" + digest)
        return "\n".join(p for p in parts if p)
