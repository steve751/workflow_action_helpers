"""Build dist/steves-workflow-helpers-<version>.zip for DataHub's Extra Pip Libraries.

pip installs a source zip when the project sits in a single top-level directory with
``pyproject.toml`` inside it (the layout GitHub's archive zips use). The zip contains
only what the build needs, so it stays small and reproducible.
"""

from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
INCLUDE_FILES = ["pyproject.toml", "setup.py", "README.md"]
INCLUDE_TREES = ["src"]
SKIP_PARTS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}


def _project_files() -> list[Path]:
    files = [ROOT / name for name in INCLUDE_FILES]
    for tree in INCLUDE_TREES:
        for path in sorted((ROOT / tree).rglob("*")):
            if not path.is_file():
                continue
            if SKIP_PARTS & set(path.parts) or path.suffix in SKIP_SUFFIXES:
                continue
            if any(part.endswith(".egg-info") for part in path.parts):
                continue
            files.append(path)
    return files


def main() -> Path:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    top_dir = f"{project['name']}-{project['version']}"
    DIST.mkdir(exist_ok=True)
    for old in DIST.glob(f"{project['name']}-*.zip"):
        old.unlink()
    target = DIST / f"{top_dir}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in _project_files():
            archive.write(path, f"{top_dir}/{path.relative_to(ROOT).as_posix()}")
    print(target)
    return target


if __name__ == "__main__":
    main()
