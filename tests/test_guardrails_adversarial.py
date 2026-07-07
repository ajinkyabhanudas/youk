"""Adversarial test suite for youk guardrails.

Pass bar: 100%. Any bypass attempt that succeeds (no exception raised when one
should be) is a direct product safety failure. Cases marked "should NOT block"
verify the guardrail doesn't over-fire on safe inputs.
"""
from __future__ import annotations
import pytest
from guardrails import HardRuleViolation, check_credential_file, check_destructive_command, check_knowledge_write


# ── no-credential-commits ─────────────────────────────────────────────────────

class TestCredentialFileGuardrail:

    # ── should BLOCK ──────────────────────────────────────────────────────────

    def test_blocks_plain_dotenv(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file(".env")

    def test_blocks_dotenv_local(self):
        """.env.local is a real bypass of the old \.env$ pattern."""
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file(".env.local")

    def test_blocks_dotenv_backup(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file(".env.backup")

    def test_blocks_dotenv_production(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file(".env.production")

    def test_blocks_dotenv_in_subdir(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("config/.env.local")

    def test_blocks_api_keys_json(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("api_keys.json")

    def test_blocks_secrets_env(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("secrets.env")

    def test_blocks_pem_file(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("server.pem")

    def test_blocks_private_key(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("id_rsa.key")

    def test_blocks_password_file(self):
        with pytest.raises(HardRuleViolation, match="no-credential-commits"):
            check_credential_file("passwords.txt")

    # ── should NOT block ──────────────────────────────────────────────────────

    def test_allows_dotenv_example(self):
        """.env.example is a template — must never be blocked."""
        check_credential_file(".env.example")

    def test_allows_dotenv_sample(self):
        check_credential_file(".env.sample")

    def test_allows_dotenv_template(self):
        check_credential_file(".env.template")

    def test_allows_regular_python_file(self):
        check_credential_file("src/main.py")

    def test_allows_regular_json(self):
        check_credential_file("config/settings.json")

    def test_allows_readme(self):
        check_credential_file("README.md")


# ── no-destructive-without-confirm ────────────────────────────────────────────

class TestDestructiveCommandGuardrail:

    # ── should BLOCK ──────────────────────────────────────────────────────────

    def test_blocks_rm_rf(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("rm -rf ./dist")

    def test_blocks_rm_rf_with_sudo(self):
        """sudo prefix must not bypass the check."""
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("sudo rm -rf /tmp/cache")

    def test_blocks_rm_flags_separated(self):
        """`rm -r -f` (separated flags) was a real bypass — now blocked."""
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("rm -r -f ./build")

    def test_blocks_rm_flags_reversed(self):
        """`rm -f -r` (reversed order) must also be blocked."""
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("rm -f -r ./tmp")

    def test_blocks_git_push_force(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git push --force")

    def test_blocks_git_push_force_with_ref(self):
        """`git push origin main --force` was a real bypass — now blocked."""
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git push origin main --force")

    def test_blocks_git_push_force_with_upstream(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git push upstream feature-branch --force")

    def test_blocks_git_reset_hard(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git reset --hard")

    def test_blocks_git_reset_hard_with_ref(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git reset --hard HEAD~1")

    def test_blocks_drop_table(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("DROP TABLE users")

    def test_blocks_drop_table_lowercase(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("drop table sessions")

    def test_blocks_checkout_dot(self):
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git checkout .")

    # ── should NOT block ──────────────────────────────────────────────────────

    def test_allows_rm_single_file(self):
        """Plain `rm` (not recursive) must not be blocked."""
        check_destructive_command("rm ./file.txt")

    def test_allows_git_push_force_with_lease(self):
        """`--force-with-lease` is safer than `--force` — must NOT be blocked."""
        check_destructive_command("git push --force-with-lease")

    def test_allows_git_push_force_with_lease_and_ref(self):
        check_destructive_command("git push origin main --force-with-lease")

    def test_allows_git_push_no_flags(self):
        check_destructive_command("git push origin main")

    def test_allows_grep_recursive(self):
        """`grep -r` uses -r flag but is not destructive."""
        check_destructive_command("grep -r 'pattern' .")

    def test_allows_git_reset_soft(self):
        check_destructive_command("git reset --soft HEAD~1")


# ── knowledge-extraction-not-logging ──────────────────────────────────────────

class TestKnowledgeWriteGuardrail:

    # ── should BLOCK ──────────────────────────────────────────────────────────

    def test_blocks_human_prefix(self):
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write("Human: what does this function do?")

    def test_blocks_assistant_prefix(self):
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write("Assistant: here's how it works...")

    def test_blocks_human_lowercase(self):
        """Lowercase `human:` was a real bypass — now blocked."""
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write("human: tell me more about this")

    def test_blocks_assistant_lowercase(self):
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write("assistant: the answer is...")

    def test_blocks_user_prefix(self):
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write("User: can you explain?")

    def test_blocks_transcript_embedded_in_text(self):
        content = "Some context.\nHuman: what should I do?\nAssistant: try this."
        with pytest.raises(HardRuleViolation, match="knowledge-extraction-not-logging"):
            check_knowledge_write(content)

    # ── should NOT block ──────────────────────────────────────────────────────

    def test_allows_structured_insight(self):
        check_knowledge_write(
            "Pattern: always validate input at the boundary layer. "
            "Prevents tight coupling between validation rules and business logic."
        )

    def test_allows_human_word_without_colon(self):
        """'human' without the colon marker must not trigger the guardrail."""
        check_knowledge_write(
            "The human-computer interaction pattern here is worth noting."
        )

    def test_allows_contract_text(self):
        check_knowledge_write("always run ruff before committing")

    def test_allows_empty_string(self):
        check_knowledge_write("")
