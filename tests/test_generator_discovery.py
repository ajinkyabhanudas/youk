"""Generator auto-discovery — youk scans scripts/ to find which docs are generated,
instead of a hand-maintained list. Conservative by design: a false positive means
auto-running the wrong script, so the bar is high (provable write + file must exist).
"""
from __future__ import annotations

from pathlib import Path

from generator_discovery import discover_generators

_YOUK = Path(__file__).parent.parent


def test_discovers_stats_generator_on_real_repo():
    gens = discover_generators(youk_root=_YOUK)
    assert "STATS.md" in gens
    assert gens["STATS.md"] == ["python3", "scripts/export_stats.py"]


def test_command_is_arg_list_not_shell_string(tmp_path):
    """No shell-injection surface — commands are arg lists."""
    gens = discover_generators(youk_root=_YOUK)
    for doc, cmd in gens.items():
        assert isinstance(cmd, list), f"{doc} command must be a list"
        assert all(isinstance(p, str) for p in cmd)


def test_write_text_pattern_discovered(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "REPORT.md").write_text("exists")  # target must exist
    (tmp_path / "scripts" / "gen.py").write_text(
        'from pathlib import Path\n'
        'OUT = Path("REPORT.md")\n'
        'OUT.write_text("hi")\n'
    )
    gens = discover_generators(youk_root=tmp_path)
    assert gens.get("REPORT.md") == ["python3", "scripts/gen.py"]


def test_open_write_pattern_discovered(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "OUT.md").write_text("exists")
    (tmp_path / "scripts" / "gen2.py").write_text('open("OUT.md", "w").write("x")\n')
    gens = discover_generators(youk_root=tmp_path)
    assert "OUT.md" in gens


def test_nonexistent_target_is_not_discovered(tmp_path):
    """A script that writes a fragment or a file that doesn't exist is NOT a generator
    (rules out path fragments like '-research.md')."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gen.py").write_text(
        'from pathlib import Path\n'
        'Path("GHOST.md").write_text("x")\n'  # GHOST.md does not exist
    )
    gens = discover_generators(youk_root=tmp_path)
    assert "GHOST.md" not in gens


def test_script_that_only_reads_md_is_not_a_generator(tmp_path):
    """Reading an .md file must not classify the script as its generator."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "DATA.md").write_text("exists")
    (tmp_path / "scripts" / "reader.py").write_text(
        'from pathlib import Path\n'
        'content = Path("DATA.md").read_text()\n'  # reads, never writes
    )
    gens = discover_generators(youk_root=tmp_path)
    assert "DATA.md" not in gens


def test_no_scripts_dir_is_safe(tmp_path):
    assert discover_generators(youk_root=tmp_path) == {}
