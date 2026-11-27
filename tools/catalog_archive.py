"""Count the private archive's lanes in the data catalog.

    python tools/catalog_archive.py                     # report only: lanes, counts, where each maps
    python tools/catalog_archive.py --verify            # also read back each lane's newest snapshot by sha256
    python tools/catalog_archive.py --verify --write    # and update catalog/<program>.json

Programs copy stores into a private archive repository (metacog-osint/tic-archive) as release assets, one release
per program, lane and month: <program>-<lane>-YYYY-MM, rolling over to .2, .3 near GitHub's asset limit. Each
snapshot is a <stamp>-<sha12>.files.json index (every file's sha256 and the tar member that holds it) plus the
.tar.gz assets holding new content.

This tool only reads: the release list, the newest index of each lane and, with --verify, the tar assets that index
names. It needs a gh login that can read the archive. Each tar is hashed member by member as it streams, nothing is
extracted to disk, and every download is deleted before the next one starts.

A lane maps to a catalog store in one of two ways (LANES below):
- mirror: the lane copies a store already in the catalog. Only that store's independent_copies changes. A lane on
  the same GitHub account as the store is listed but not counted, since the README counts a copy only in a separate
  place. A lane on another provider counts once its newest snapshot reads back and matches by sha256; otherwise it is
  listed as not compared.
- own: the lane is the only copy of its data, so it is its own store: location, schema, cadence, first date and
  copies are measured from the lane.

What reaches the catalog, which is public: lane names, asset, snapshot and file counts, bytes and dates. Never a file
path, a member name or any content. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog"
REPO = os.environ.get("TIC_ARCHIVE_REPO", "metacog-osint/tic-archive")
TAG_RE = re.compile(r"^(?P<lane>[a-z0-9][a-z0-9-]*)-(?P<month>\d{4}-\d{2})(?:\.(?P<part>\d+))?$")
STAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)-[0-9a-f]{12}\.files\.json$")
SNAPSHOT_SCHEMA = "tic-archive-snapshot-1"
MARK = "; private archive lane"          # everything from here on in a copies note is written by this tool
NOT_COMPARED_OTHERS = "other copies were not compared; "
PRIVATE_WHERE = "private GitHub repository, release assets"
GITHUB_KINDS = {"git", "github-release"}
MIN_GAPS = 5                            # fewer snapshot gaps than this do not show a cadence

# lane -> (how, program, store id[, store name for a new own store])
LANES = {
    "headwind-history": ("mirror", "headwind", "headwind-history"),
    "headwind-state": ("mirror", "headwind", "headwind-state"),
    "context-firestore": ("mirror", "context", "context-snapshots"),
    "vigil-pgdump": ("mirror", "vigil", "vigil-db"),
    "watchfloor-bucket": ("mirror", "watchfloor", "watchfloor-bucket"),
    "headwind-raw": ("own", "headwind", "headwind-archive-raw", "Raw source archive"),
    "headwind-site": ("own", "headwind", "headwind-archive-site", "Site files archive"),
    "blackout-netblocks": ("own", "blackout", "blackout-archive-netblocks", "NetBlocks post archive"),
    "launch-history": ("mirror", "launch", "launch-history"),
    "launch-copies": ("mirror", "launch", "launch-history"),
    "launch-payloads": ("own", "launch", "launch-archive-payloads", "Payload rates archive"),
    "launch-site": ("mirror", "launch", "launch-site-files"),
    "launch-source": ("own", "launch", "launch-archive-source", "Raw source archive"),
    "launch-raw": ("own", "launch", "launch-archive-raw", "Raw reply archive"),
    "launch-state": ("own", "launch", "launch-archive-state", "Run state archive"),
    "noisefloor-baltico": ("own", "noisefloor", "noisefloor-archive-baltico", "Raw BALTICO archive"),
    "noisefloor-collectors": ("own", "noisefloor", "noisefloor-archive-collectors", "Raw collector archive"),
    "noisefloor-nisar": ("own", "noisefloor", "noisefloor-archive-nisar", "Raw NISAR archive"),
    "noisefloor-sensors": ("own", "noisefloor", "noisefloor-archive-sensors", "Sensor data archive"),
    "orbit-raw": ("own", "orbit", "orbit-archive-raw", "Raw source archive"),
    "orbit-state": ("own", "orbit", "orbit-archive-state", "State and ledger archive"),
    "orbit-ledger": ("own", "orbit", "orbit-archive-state", "State and ledger archive"),
    "relief-raw": ("own", "relief", "relief-archive-raw", "Raw source archive"),
    "relief-appeals": ("own", "relief", "relief-archive-appeals", "Appeals archive"),
    "undertow-raw": ("own", "undertow", "undertow-archive-raw", "Raw source archive"),
}
IGNORED = {"kit-selftest"}               # the archive tool's own test lane


class Error(RuntimeError):
    pass


# --- reading the archive -----------------------------------------------------------------------------------------

class GhArchive:
    """The archive's releases through the gh CLI. Read only: GET requests and asset downloads."""

    def __init__(self, repo: str = REPO):
        self.repo = repo

    def _gh(self, args: list[str]) -> str:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise Error(f"gh {args[0]} failed: {r.stderr.strip()[:300]}")
        return r.stdout

    def _pages(self, path: str) -> list:
        return [x for page in json.loads(self._gh(["api", "--paginate", "--slurp", path])) for x in page]

    def releases(self) -> dict[str, list[dict]]:
        """{tag: [{name, size, created}]}"""
        out = {}
        for rel in self._pages(f"repos/{self.repo}/releases?per_page=100"):
            assets = self._pages(f"repos/{self.repo}/releases/{rel['id']}/assets?per_page=100")
            out[rel["tag_name"]] = [{"name": a["name"], "size": a["size"], "created": a["created_at"]} for a in assets]
        return out

    def download(self, tag: str, name: str, dest: Path) -> Path:
        self._gh(["release", "download", tag, "-R", self.repo, "-p", name, "-D", str(dest)])
        return Path(dest) / name


class DirArchive:
    """A local stand-in for tests: <root>/<tag>/<asset>."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def releases(self) -> dict[str, list[dict]]:
        out = {}
        for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
            out[d.name] = [{"name": f.name, "size": f.stat().st_size,
                            "created": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ")} for f in sorted(d.iterdir())]
        return out

    def download(self, tag: str, name: str, dest: Path) -> Path:
        src = self.root / tag / name
        if not src.is_file():
            raise Error(f"asset not found in {tag}")
        out = Path(dest) / name
        out.write_bytes(src.read_bytes())
        return out


def stamp_time(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def lanes_of(releases: dict[str, list[dict]]) -> tuple[dict[str, dict], list[str]]:
    """Group releases into lanes. Returns ({lane: {tags, assets, snapshots}}, tags that are not lane releases)."""
    lanes, odd = {}, []
    for tag, assets in sorted(releases.items()):
        m = TAG_RE.match(tag)
        if not m:
            odd.append(tag)
            continue
        lane = lanes.setdefault(m["lane"], {"tags": [], "assets": [], "snapshots": []})
        lane["tags"].append(tag)
        for a in assets:
            lane["assets"].append({**a, "tag": tag})
            s = STAMP_RE.match(a["name"])
            if s:
                lane["snapshots"].append({"stamp": s[1], "tag": tag, "name": a["name"]})
    for lane in lanes.values():
        lane["snapshots"].sort(key=lambda s: s["stamp"])
    return lanes, odd


def cadence(snapshots: list[dict]) -> str | None:
    times = sorted(stamp_time(s["stamp"]) for s in snapshots)
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
    if len(gaps) < MIN_GAPS:
        return None
    h = statistics.median(gaps)
    return f"about every {h:.1f} h" if h < 48 else f"about every {h / 24:.1f} days"


def verify_newest(archive, lane: dict, max_bytes: int, work: Path) -> dict:
    """Read the newest snapshot back from its tar members and match every file by sha256.

    Returns {"ok": bool, "stamp", "files", "bytes_read", "why"}. Never returns paths or member names."""
    if not lane["snapshots"]:
        return {"ok": False, "why": "the lane has no snapshot index"}
    snap = lane["snapshots"][-1]
    idx = archive.download(snap["tag"], snap["name"], work)
    try:
        doc = json.loads(idx.read_text(encoding="utf-8"))
    finally:
        idx.unlink(missing_ok=True)
    base = {"stamp": snap["stamp"], "files": len(doc.get("files", []))}
    if doc.get("schema") != SNAPSHOT_SCHEMA:
        return {**base, "ok": False, "why": "the newest index has an unknown schema"}
    sizes = {(a["tag"], a["name"]): a["size"] for a in lane["assets"]}
    want: dict[tuple[str, str], dict[str, str]] = {}
    for f in doc["files"]:
        want.setdefault((f["release"], f["asset"]), {})[f["member"]] = f["sha256"]
    missing = [k for k in want if k not in sizes]
    if missing:
        return {**base, "ok": False, "why": f"{len(missing)} tar asset(s) named by the newest index are missing"}
    need = sum(sizes[k] for k in want)
    if need > max_bytes:
        return {**base, "ok": False,
                "why": f"reading the newest snapshot back needs {need / 1e6:,.0f} MB of downloads, over this run's "
                       f"{max_bytes / 1e6:,.0f} MB limit"}
    for (tag, name), members in sorted(want.items()):
        tar = archive.download(tag, name, work)
        try:
            with tarfile.open(tar, "r:gz") as t:
                for m in t:
                    if m.name not in members:
                        continue
                    h = hashlib.sha256()
                    fh = t.extractfile(m)
                    for b in iter(lambda: fh.read(1 << 20), b""):
                        h.update(b)
                    if h.hexdigest() != members.pop(m.name):
                        return {**base, "ok": False, "why": "a file did not match its sha256"}
            if members:
                return {**base, "ok": False, "why": "a file named by the index is not in its tar"}
        finally:
            tar.unlink(missing_ok=True)
    # Each member is stored once, so files with the same bytes share it; all of them matched.
    return {**base, "ok": True, "bytes_read": need}


# --- writing the catalog -----------------------------------------------------------------------------------------

def day(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


def when(stamp: str) -> str:
    return stamp_time(stamp).strftime("%Y-%m-%d %H:%MZ")


def check_text(v: dict | None, lane: str) -> str:
    if v is None:
        return "newest snapshot not compared in this run"
    if v["ok"]:
        n = v["files"]
        return (f"newest snapshot ({when(v['stamp'])}, {n:,} file{'' if n == 1 else 's'}) read back from its tar "
                f"members and matched by sha256")
    return f"newest snapshot not compared: {v['why']}"


def mirror_copies(field: dict, notes: list[tuple[str, bool, str]], read: str) -> dict:
    """independent_copies of a mirrored store. notes: [(lane, counted, text)]."""
    base = field.get("how") or field.get("why") or ""
    base = base.split(MARK)[0].replace(NOT_COMPARED_OTHERS, "")
    tail = "".join(f"{MARK} {lane}: {text}" for lane, _, text in notes) + f" (read {read})"
    counted = sum(1 for _, c, _ in notes if c)
    if counted:
        # The store itself is one copy; each archive lane that matched on another provider is one more.
        return {"value": 1 + counted, "status": "measured", "how": base + tail}
    if field["status"] == "unverified":
        return {"value": None, "status": "unverified", "why": base + tail}
    value = field["value"] if MARK not in (field.get("how") or "") else 1
    return {"value": value, "status": "measured", "how": base + tail}


def own_store(old: dict | None, sid: str, name: str, program: str, lanes: list[str], data: list[dict],
              checks: list[dict | None], read: str) -> dict:
    assets = [a for d in data for a in d["assets"]]
    snaps = [s for d in data for s in d["snapshots"]]
    exts = sorted({".tar.gz" if a["name"].endswith(".tar.gz") else Path(a["name"]).suffix for a in assets}, reverse=True)
    names = ", ".join(lanes)
    lane_word = "lanes" if len(lanes) > 1 else "lane"
    per_lane = [(lane, cadence(d["snapshots"])) for lane, d in zip(lanes, data)]
    per_lane = [(lane, c) for lane, c in per_lane if c]
    if len(lanes) == 1:
        cad = per_lane[0][1] if per_lane else None
    else:
        cad = "; ".join(f"{lane}: {c}" for lane, c in per_lane) or None
    store = {
        "id": sid,
        "store": old["store"] if old else name,
        "location": {"value": {"kind": "github-release", "where": PRIVATE_WHERE}, "status": "measured",
                     "how": f"GitHub releases API, archive {lane_word} {names} (read {read})"},
        "schema": {"value": "files: " + ", ".join(exts), "status": "measured",
                   "how": f"{len(assets):,} assets, {sum(a['size'] for a in assets) / 1e6:,.1f} MB, "
                          f"{len(snaps):,} snapshots (read {read})"},
        "method_version": (old or {}).get("method_version") or {
            "value": None, "status": "unverified", "why": "archive copy; no method version is recorded for this store"},
        "licence": (old or {}).get("licence") or {
            "value": f"registry:{program}", "status": "measured",
            "how": "program terms in vocab/programs.json; archive lanes keep each source's own terms, not broken out "
                   "per store"},
        "cadence": ({"value": cad, "status": "measured",
                     "how": f"median gap between snapshot times, per lane (read {read})"} if cad else
                    {"value": None, "status": "unverified", "why": "too few snapshots to show a cadence"}),
        "first_date": ({"value": day(stamp_time(snaps[0]["stamp"])), "status": "measured",
                        "how": "earliest surviving snapshot"} if snaps else
                       {"value": None, "status": "unverified", "why": "no snapshot index found"}),
        "independent_copies": {
            "value": 1, "status": "measured",
            "how": "one copy, in the private archive; " + "; ".join(
                f"{lane}: {check_text(c, lane)}" for lane, c in zip(lanes, checks)) +
                   f"; a second copy on the same GitHub account would not be independent (read {read})"},
    }
    return store


def plan(lanes: dict[str, dict]) -> tuple[dict, list[str]]:
    """{program: {"mirror": {store: [lane]}, "own": {store: (name, [lane])}}}, unmapped lanes."""
    out, unmapped = {}, []
    for lane in sorted(lanes):
        if lane in IGNORED:
            continue
        if lane not in LANES:
            unmapped.append(lane)
            continue
        kind, program, sid, *rest = LANES[lane]
        p = out.setdefault(program, {"mirror": {}, "own": {}})
        if kind == "mirror":
            p["mirror"].setdefault(sid, []).append(lane)
        else:
            p["own"].setdefault(sid, (rest[0], []))[1].append(lane)
    return out, unmapped


def apply(doc: dict, program_plan: dict, lanes: dict[str, dict], checks: dict[str, dict | None], read: str) -> list[str]:
    """Update one program's catalog document in place. Returns what changed, for the report."""
    changed = []
    by_id = {s["id"]: s for s in doc["stores"]}
    for sid, lane_names in sorted(program_plan["mirror"].items()):
        s = by_id.get(sid)
        if s is None:
            raise Error(f"{doc['program']}: mirror store {sid} is not in the catalog")
        same = s["location"]["status"] == "measured" and s["location"]["value"]["kind"] in GITHUB_KINDS
        notes = []
        for lane in lane_names:
            c = checks.get(lane)
            if same:
                notes.append((lane, False, check_text(c, lane) + ", on the same GitHub account, so not counted"))
            else:
                ok = bool(c and c["ok"])
                notes.append((lane, ok, check_text(c, lane) + (", on GitHub, a separate provider" if ok else "")))
        s["independent_copies"] = mirror_copies(s["independent_copies"], notes, read)
        changed.append(f"{sid}: copies {s['independent_copies']['value']}")
    for sid, (name, lane_names) in sorted(program_plan["own"].items()):
        new = own_store(by_id.get(sid), sid, name, doc["program"], lane_names, [lanes[n] for n in lane_names],
                        [checks.get(n) for n in lane_names], read)
        if sid in by_id:
            doc["stores"][doc["stores"].index(by_id[sid])] = new
            changed.append(f"{sid}: updated")
        else:
            doc["stores"].append(new)
            changed.append(f"{sid}: added")
    return changed


def main(argv=None, archive=None, catalog: Path = CATALOG, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verify", action="store_true", help="read back each lane's newest snapshot by sha256")
    ap.add_argument("--max-verify-mb", type=float, default=400,
                    help="skip the read-back of a lane whose newest snapshot needs more downloads than this")
    ap.add_argument("--lane", action="append", default=[], help="verify only these lanes (repeat)")
    ap.add_argument("--write", action="store_true", help="update catalog/<program>.json")
    a = ap.parse_args(argv)
    archive = archive or GhArchive()
    read = day(now or datetime.now(timezone.utc))
    try:
        lanes, odd = lanes_of(archive.releases())
        todo, unmapped = plan(lanes)
        checks: dict[str, dict | None] = {}
        with tempfile.TemporaryDirectory(prefix="tic-catalog-") as td:
            for name in sorted(lanes):
                if name in IGNORED or name in unmapped:
                    continue
                if a.verify and (not a.lane or name in a.lane):
                    checks[name] = verify_newest(archive, lanes[name], int(a.max_verify_mb * 1e6), Path(td))
                else:
                    checks[name] = None
                c = checks[name]
                lane = lanes[name]
                print(f"{name}\t{len(lane['assets'])} assets\t{len(lane['snapshots'])} snapshots\t"
                      f"-> {LANES[name][1]}/{LANES[name][2]} ({LANES[name][0]})\t{check_text(c, name)}")
        for name in unmapped:
            print(f"{name}\tnot in LANES: not written; add it and run again", file=sys.stderr)
        for tag in odd:
            print(f"release {tag} is not a lane release; skipped", file=sys.stderr)
        if a.write:
            for program, program_plan in sorted(todo.items()):
                path = catalog / f"{program}.json"
                doc = json.loads(path.read_text(encoding="utf-8"))
                for line in apply(doc, program_plan, lanes, checks, read):
                    print(f"{program}: {line}")
                path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return 1 if unmapped else 0
    except (Error, OSError, tarfile.TarError, json.JSONDecodeError) as e:
        print(f"catalog_archive: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
