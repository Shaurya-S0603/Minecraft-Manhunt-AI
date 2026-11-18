"""Package the Python/Scarpet distribution without runtime files."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
PREFIX = "Minecraft_Manhunt_Hunter_v1.2.1"
DIRECTORIES = ("ai-controller", "config", "docs", "quickstart", "reports", "research", "training")
ROOT_FILES = (".gitignore", "CHANGELOG.md", "README.md", "RUN_TESTS.bat", "build_v1.py",
              "manhunt/START_HUNTER_V1.bat")
SKIP = {"__pycache__", "node_modules", ".venv", ".pytest_cache", "generated"}
RUNTIME_SUFFIXES = {".class", ".jar", ".log", ".pyc", ".zip", ".7z", ".jsonl"}


def build(destination):
    files = [ROOT / name for name in ROOT_FILES]
    for name in DIRECTORIES:
        files.extend((ROOT / name).rglob("*"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            relative = path.relative_to(ROOT)
            if (path.is_file() and not path.is_symlink() and not SKIP.intersection(relative.parts)
                    and path.suffix not in RUNTIME_SUFFIXES):
                archive.write(path, arcname=f"{PREFIX}/{relative.as_posix()}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, nargs="?", default=ROOT.parent / f"{PREFIX}_1.21.11.zip")
    print(build(parser.parse_args().destination))
