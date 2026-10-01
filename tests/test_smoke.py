from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skeleton_files_exist():
    for name in ["README.md", "AGENTS.md", "CLAUDE.md", "requirements.txt", "pyproject.toml", ".gitattributes"]:
        assert (ROOT / name).is_file(), name
