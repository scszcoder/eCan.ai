"""Build the 云托管 upload folder: Dockerfile + requirements + knowledge/ks only.

    python deploy/ks/tcb/make_context.py            -> deploy/ks/tcb/dist/
Then deploy that folder (see README.md in this directory).
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIST = HERE / "dist"


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "knowledge").mkdir(parents=True)
    shutil.copy(HERE / "Dockerfile", DIST / "Dockerfile")
    shutil.copy(ROOT / "deploy" / "ks" / "requirements-ks.txt", DIST / "requirements-ks.txt")
    shutil.copytree(ROOT / "knowledge" / "ks", DIST / "knowledge" / "ks",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (DIST / "knowledge" / "__init__.py").write_text("", encoding="utf-8")
    files = [p for p in DIST.rglob("*") if p.is_file()]
    print(f"{DIST}: {len(files)} files, {sum(p.stat().st_size for p in files) // 1024} KB")


if __name__ == "__main__":
    main()
