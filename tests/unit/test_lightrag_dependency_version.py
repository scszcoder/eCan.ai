"""Keep LightRAG pinned consistently across every deployable runtime."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIGHTRAG_VERSION = "1.5.6"
REQUIREMENTS_FILES = (
    PROJECT_ROOT / "requirements-base.txt",
    PROJECT_ROOT / "requirements-web.txt",
    PROJECT_ROOT / "requirements-worker.txt",
    PROJECT_ROOT / "rag_worker" / "requirements.txt",
)


def _lightrag_pins(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().lower().startswith("lightrag-hku")
    ]


def test_lightrag_version_is_consistent_across_runtimes() -> None:
    expected = [f"lightrag-hku=={LIGHTRAG_VERSION}"]

    for requirements_file in REQUIREMENTS_FILES:
        assert _lightrag_pins(requirements_file) == expected, (
            f"{requirements_file.relative_to(PROJECT_ROOT)} must contain exactly "
            f"one LightRAG pin: {expected[0]}"
        )
