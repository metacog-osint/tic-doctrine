"""Copy the kit into a program repo as doctrine/kit/ (a vendored, read-only copy).

    python tools/sync.py [local path]          # copy, write doctrine/kit/KIT.json
    python tools/sync.py [local path] --check  # exit 1 if the copy was edited or is behind

Repos differ in language and some have no git remote, so a plain copy with a
manifest of hashes is the simplest way to share one kit at $0. Programs never
edit doctrine/kit/; they change the kit here and sync.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ["tic.py", "vocab", "geo", "python/tic_doctrine", "js", "schema", "docs", "LICENSE", "README.md"]
SKIP = {"__pycache__"}


def files(base: Path):
    for part in PARTS:
        p = base / part
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not SKIP & set(f.parts):
                    yield f


def digest(f: Path) -> str:
    """sha256 with CRLF read as LF, so a Windows checkout (core.autocrlf) of the same file matches."""
    return hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def manifest(base: Path) -> dict:
    return {f.relative_to(base).as_posix(): digest(f) for f in files(base)}


def version() -> str:
    for line in (ROOT / "python" / "tic_doctrine" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split('"')[1]
    raise RuntimeError("no __version__")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = Path(sys.argv[1]) / "doctrine" / "kit"
    want = manifest(ROOT)
    if "--check" in sys.argv:
        kit_json = target / "KIT.json"
        if not kit_json.exists():
            print(f"{target}: no kit copy")
            return 1
        recorded = json.loads(kit_json.read_text(encoding="utf-8"))["files"]
        have = manifest(target)
        edited = sorted(k for k in have if recorded.get(k) != have[k])
        behind = sorted(k for k in want if recorded.get(k) != want[k])
        if edited:
            print("edited inside doctrine/kit/ (change the kit repo instead):", ", ".join(edited))
        if behind:
            print("kit copy is behind the kit repo:", ", ".join(behind))
        print("kit copy", "OK" if not (edited or behind) else "NOT current")
        return 1 if edited else 0
    if target.exists():
        shutil.rmtree(target)
    for f in files(ROOT):
        dest = target / f.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
    (target / "KIT.json").write_text(json.dumps(
        {"kit": "tic-doctrine", "version": version(), "files": want}, indent=2) + "\n", encoding="utf-8")
    print(f"synced tic-doctrine {version()} to {target} ({len(want)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
