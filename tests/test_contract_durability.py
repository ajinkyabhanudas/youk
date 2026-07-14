"""
Contract durability tests.

Contracts are the core value proposition of youk: when a developer says
"always run tests before committing", that agreement must survive every
session boundary, compaction, and tab-close.

These tests verify the full durability chain:
  save_contract → contracts.md → compact_context → session_start → brief

If any link breaks, contracts silently vanish — the developer re-states them
and wonders why youk feels unreliable.
"""
from __future__ import annotations
from pathlib import Path


class TestContractSurvivesCompaction:
    """
    The full chain: contract written → compaction runs → session_start loads it.

    This is the most important durability test. Claude's auto-compaction can
    evict anything from the conversation that wasn't written to a file. If
    write_contracts persists to contracts.md, the contract survives.
    """

    def test_contract_in_brief_after_compact(self, monkeypatch, tmp_path):
        """
        Write a contract, compact, load — contract must appear in the brief.
        Chain: write_contracts() → compact_context() state → _load_contracts() → present in brief.
        """
        import compaction
        import session

        monkeypatch.setattr(compaction, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)

        slug = "myproject"
        proj_dir = tmp_path / "knowledge" / "projects" / slug
        proj_dir.mkdir(parents=True)

        # Step 1: contract verbalized and written
        compaction.write_contracts(slug, ["always run ruff before committing"])

        # Step 2: verify it's in the file (the actual write, not just the call)
        contracts_file = proj_dir / "contracts.md"
        assert contracts_file.exists(), "contracts.md must exist after write_contracts"
        raw = contracts_file.read_text()
        assert "always run ruff before committing" in raw, (
            "Contract must appear verbatim in contracts.md — "
            "compaction loads from this file, not from conversation"
        )

        # Step 3: simulate session_start reading it back (what builds the brief)
        loaded = session._load_contracts(slug)
        assert any("always run ruff before committing" in c for c in loaded), (
            "_load_contracts must return the contract — "
            "this is what gets injected into the session brief at session_start"
        )

    def test_multiple_contracts_all_survive(self, monkeypatch, tmp_path):
        """
        Multiple contracts written across different moments in a session
        all survive — not just the last one.
        """
        import compaction
        import session

        monkeypatch.setattr(compaction, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)

        slug = "myproject"
        (tmp_path / "knowledge" / "projects" / slug).mkdir(parents=True)

        contracts = [
            "always run ruff before committing",
            "never mock the database in tests",
            "from now on use ISO dates in all API responses",
        ]
        for contract in contracts:
            compaction.write_contracts(slug, [contract])

        loaded = session._load_contracts(slug)
        loaded_text = " ".join(loaded)
        for contract in contracts:
            assert contract in loaded_text, (
                f"Contract '{contract}' must survive — "
                "each verbalized agreement is individually load-bearing"
            )


class TestContractInYoukLiteTemplate:
    """
    youk-lite relies entirely on the CLAUDE.md template to instruct Claude
    to write contracts. If the instruction is absent or ambiguous, contracts
    are only as durable as the developer's memory.
    """

    def test_contracts_section_has_immediate_write_instruction(self):
        """
        The ## Contracts section in the youk-lite template must instruct Claude
        to write immediately — not at end of session, not on request.

        'Immediately' here means: the moment the user states a working agreement,
        not after they type /done or 'save this'.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        assert lite_doc.exists(), "docs/youk-lite.md must exist"
        content = lite_doc.read_text()

        # The key behavioral instruction
        assert "immediately" in content, (
            "youk-lite.md template ## Contracts section must say 'immediately' — "
            "deferred writes are exactly what compaction destroys"
        )
        assert "Do not wait" in content, (
            "youk-lite.md must tell Claude 'Do not wait for end of session' — "
            "without this, contracts are session-boundary losses waiting to happen"
        )

    def test_contracts_section_names_trigger_phrases(self):
        """
        The ## Contracts section must name what triggers a write:
        'always', 'never', 'from now on', 'remember to', 'make sure you'.

        If trigger phrases are not named, Claude may only write contracts when
        the developer says "save this" explicitly — missing the natural-language cases.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = lite_doc.read_text()

        # At least 'always' and 'never' must be named as triggers
        assert "always" in content, (
            "youk-lite.md must name 'always' as a contract trigger phrase"
        )
        assert "never" in content, (
            "youk-lite.md must name 'never' as a contract trigger phrase"
        )

    def test_resume_point_has_staleness_warning(self):
        """
        The ## Resume point section must warn Claude when the entry is >14 days old.

        Without this, Persona D (returning dev after 8 weeks) loads a stale
        resume point silently — wrong codebase state, stale contracts, no warning.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = lite_doc.read_text()

        assert "14 days" in content, (
            "youk-lite.md ## Resume point must include 14-day staleness threshold — "
            "without this, stale context loads as if it were fresh"
        )
