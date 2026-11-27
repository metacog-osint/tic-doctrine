"""tools/catalog_archive.py: archive lanes counted in the catalog, offline against a local stand-in archive."""

import gzip
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import catalog_archive as ca  # noqa: E402
from test_catalog import entry_problems  # noqa: E402

NOW = datetime(2026, 11, 27, 4, 0, tzinfo=timezone.utc)
SECRET_PATH = "private-folder/secret-name.json"


def put_snapshot(root: Path, tag: str, stamp: str, files: dict[str, bytes], corrupt=False) -> None:
    """Write one snapshot as tic_archive.py does: a tar of members named by sha256 and a .files.json index."""
    d = root / tag
    d.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(fileobj=gz, mode="w") as t:
        for data in {hashlib.sha256(b).hexdigest(): b for b in files.values()}.values():
            sha = hashlib.sha256(data).hexdigest()
            body = b"x" + data if corrupt else data
            ti = tarfile.TarInfo(f"{sha[:2]}/{sha}")
            ti.size = len(body)
            t.addfile(ti, io.BytesIO(body))
    tar = f"{stamp}-{hashlib.sha256(buf.getvalue()).hexdigest()[:12]}.tar.gz"
    (d / tar).write_bytes(buf.getvalue())
    doc = {"schema": "tic-archive-snapshot-1", "stamp": stamp, "files": [
        {"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "release": tag, "asset": tar,
         "member": f"{hashlib.sha256(b).hexdigest()[:2]}/{hashlib.sha256(b).hexdigest()}"} for p, b in files.items()]}
    (d / f"{stamp}-{'0' * 12}.files.json").write_text(json.dumps(doc), encoding="utf-8")


def field(value, how):
    return {"value": value, "status": "measured", "how": how}


def store(sid, kind, where, copies):
    return {"id": sid, "store": sid, "location": field({"kind": kind, "where": where}, "api"),
            "schema": field("files", "n"), "method_version": field("x-1", "feed"),
            "licence": field("registry:headwind", "terms"), "cadence": field("daily", "gaps"),
            "first_date": field("2026-11-01", "first"), "independent_copies": copies}


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "archive"
        self.root.mkdir()
        self.archive = ca.DirArchive(self.root)
        self.work = Path(self.td.name) / "work"
        self.work.mkdir()

    def tearDown(self):
        self.td.cleanup()


class Lanes(Base):
    def test_groups_months_and_rollover_parts(self):
        put_snapshot(self.root, "headwind-raw-2026-10", "20261031T000000Z", {"a": b"1"})
        put_snapshot(self.root, "headwind-raw-2026-11", "20261101T000000Z", {"a": b"2"})
        put_snapshot(self.root, "headwind-raw-2026-11.2", "20261102T000000Z", {"a": b"3"})
        (self.root / "not-a-lane").mkdir()
        lanes, odd = ca.lanes_of(self.archive.releases())
        self.assertEqual(set(lanes), {"headwind-raw"})
        self.assertEqual(len(lanes["headwind-raw"]["tags"]), 3)
        self.assertEqual(lanes["headwind-raw"]["snapshots"][-1]["stamp"], "20261102T000000Z")
        self.assertEqual(odd, ["not-a-lane"])

    def test_cadence_needs_enough_snapshots(self):
        snaps = [{"stamp": f"202611{d:02d}T000000Z"} for d in range(1, 4)]
        self.assertIsNone(ca.cadence(snaps))
        snaps = [{"stamp": f"202611{d:02d}T{h:02d}0000Z"} for d in range(1, 3) for h in (0, 6, 12, 18)]
        self.assertEqual(ca.cadence(snaps), "about every 6.0 h")


class Verify(Base):
    def lane(self):
        return ca.lanes_of(self.archive.releases())[0]["vigil-pgdump"]

    def test_match(self):
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {"a": b"one", "b": b"two", "c": b"one"})
        v = ca.verify_newest(self.archive, self.lane(), 10**9, self.work)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["files"], 3)
        self.assertEqual(list(self.work.iterdir()), [], "downloads are deleted")

    def test_mismatch(self):
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {"a": b"one"}, corrupt=True)
        v = ca.verify_newest(self.archive, self.lane(), 10**9, self.work)
        self.assertFalse(v["ok"])
        self.assertIn("sha256", v["why"])

    def test_over_the_limit_is_not_compared(self):
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {"a": b"one" * 1000})
        v = ca.verify_newest(self.archive, self.lane(), 10, self.work)
        self.assertFalse(v["ok"])
        self.assertIn("limit", v["why"])

    def test_missing_tar(self):
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {"a": b"one"})
        for p in (self.root / "vigil-pgdump-2026-11").glob("*.tar.gz"):
            p.unlink()
        v = ca.verify_newest(self.archive, self.lane(), 10**9, self.work)
        self.assertFalse(v["ok"])
        self.assertIn("missing", v["why"])


class Apply(unittest.TestCase):
    OK = {"ok": True, "stamp": "20261127T035554Z", "files": 16}
    BAD = {"ok": False, "stamp": "20261127T035554Z", "files": 16, "why": "a file did not match its sha256"}

    def doc(self):
        return {"catalog": "tic-catalog/1", "program": "headwind", "measured_at": "2026-11-24T03:32:48Z", "stores": [
            store("headwind-history", "git", "github.com/metacog-osint/headwind: history", field(
                1, "at least one copy confirmed here; other copies were not compared; local clones are not counted")),
            store("headwind-bucket", "object-store", "Google Cloud Storage", field(1, "no versioning")),
            store("headwind-db", "database", "Postgres", {"value": None, "status": "unverified",
                                                          "why": "backup settings were not read"}),
        ]}

    def lanes(self):
        snaps = [{"stamp": f"2026112{d}T0{h}0000Z", "tag": "t", "name": "n"} for d in range(1, 5) for h in (0, 6)]
        assets = [{"name": "20261121T000000Z-aaaaaaaaaaaa.tar.gz", "size": 2_000_000, "tag": "t"},
                  {"name": "20261121T000000Z-aaaaaaaaaaaa.files.json", "size": 500, "tag": "t"}]
        return {n: {"tags": ["t"], "assets": assets, "snapshots": snaps} for n in
                ("headwind-history", "headwind-bucket", "headwind-db", "headwind-raw")}

    def plan(self):
        return {"mirror": {"headwind-history": ["headwind-history"], "headwind-bucket": ["headwind-bucket"],
                           "headwind-db": ["headwind-db"]},
                "own": {"headwind-archive-raw": ("Raw source archive", ["headwind-raw"])}}

    def run_apply(self, doc, checks):
        ca.apply(doc, self.plan(), self.lanes(), checks, "2026-11-27")
        return {s["id"]: s for s in doc["stores"]}

    def test_same_account_is_listed_not_counted(self):
        s = self.run_apply(self.doc(), dict.fromkeys(self.lanes(), self.OK))["headwind-history"]["independent_copies"]
        self.assertEqual(s["value"], 1)
        self.assertIn("private archive lane headwind-history", s["how"])
        self.assertIn("same GitHub account, so not counted", s["how"])
        self.assertNotIn("other copies were not compared", s["how"])

    def test_other_provider_counts_only_when_matched(self):
        s = self.run_apply(self.doc(), dict.fromkeys(self.lanes(), self.OK))
        self.assertEqual(s["headwind-bucket"]["independent_copies"]["value"], 2)
        self.assertEqual(s["headwind-db"]["independent_copies"]["value"], 2)
        self.assertEqual(s["headwind-db"]["independent_copies"]["status"], "measured")
        s = self.run_apply(self.doc(), dict.fromkeys(self.lanes(), self.BAD))
        self.assertEqual(s["headwind-bucket"]["independent_copies"]["value"], 1)
        self.assertIn("not compared", s["headwind-bucket"]["independent_copies"]["how"])
        self.assertEqual(s["headwind-db"]["independent_copies"]["status"], "unverified")
        self.assertIn("not compared", s["headwind-db"]["independent_copies"]["why"])
        s = self.run_apply(self.doc(), dict.fromkeys(self.lanes()))
        self.assertIn("not compared in this run", s["headwind-bucket"]["independent_copies"]["how"])

    def test_rerun_gives_the_same_result(self):
        checks = dict.fromkeys(self.lanes(), self.OK)
        once = self.doc()
        self.run_apply(once, checks)
        twice = json.loads(json.dumps(once))
        self.run_apply(twice, checks)
        self.assertEqual(once, twice)
        # A counted copy that later fails its read-back drops back to the store alone.
        self.run_apply(twice, dict.fromkeys(self.lanes(), self.BAD))
        self.assertEqual({s["id"]: s for s in twice["stores"]}["headwind-bucket"]["independent_copies"]["value"], 1)

    def test_own_store_is_added_and_valid(self):
        doc = self.doc()
        s = self.run_apply(doc, dict.fromkeys(self.lanes(), self.OK))["headwind-archive-raw"]
        self.assertEqual(s["store"], "Raw source archive")
        self.assertEqual(s["location"]["value"], {"kind": "github-release", "where": ca.PRIVATE_WHERE})
        self.assertEqual(s["schema"]["value"], "files: .tar.gz, .json")
        self.assertEqual(s["cadence"]["value"], "about every 6.0 h")
        self.assertEqual(s["first_date"]["value"], "2026-11-21")
        self.assertEqual(s["independent_copies"]["value"], 1)
        self.assertIn("matched by sha256", s["independent_copies"]["how"])
        self.assertEqual(entry_problems(doc, "headwind"), [])

    def test_own_store_keeps_its_name_and_method(self):
        doc = self.doc()
        doc["stores"].append(store("headwind-archive-raw", "github-release", ca.PRIVATE_WHERE, field(1, "x")))
        doc["stores"][-1]["store"] = "Kept name"
        s = self.run_apply(doc, dict.fromkeys(self.lanes()))["headwind-archive-raw"]
        self.assertEqual(s["store"], "Kept name")
        self.assertEqual(s["method_version"]["value"], "x-1")
        self.assertEqual(len([x for x in doc["stores"] if x["id"] == "headwind-archive-raw"]), 1)


class Main(Base):
    def catalog(self, stores):
        c = Path(self.td.name) / "catalog"
        c.mkdir(exist_ok=True)
        doc = {"catalog": "tic-catalog/1", "program": "vigil", "measured_at": "2026-11-24T03:32:48Z",
               "stores": stores}
        (c / "vigil.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        return c

    def test_write_names_no_path_or_member(self):
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {SECRET_PATH: b"dump"})
        put_snapshot(self.root, "kit-selftest-2026-11", "20261119T000000Z", {"a": b"x"})
        c = self.catalog([store("vigil-db", "database", "Postgres", {
            "value": None, "status": "unverified", "why": "platform backup settings were not read"})])
        self.assertEqual(ca.main(["--verify", "--write"], self.archive, c, NOW), 0)
        text = (c / "vigil.json").read_text(encoding="utf-8")
        doc = json.loads(text)
        self.assertEqual(doc["stores"][0]["independent_copies"]["value"], 2)
        self.assertIn("(read 2026-11-27)", text)
        sha = hashlib.sha256(b"dump").hexdigest()
        for secret in ("private-folder", "secret-name", sha[:12]):
            self.assertNotIn(secret, text)
        self.assertEqual(entry_problems(doc, "vigil"), [])

    def test_unmapped_lane_is_not_written_and_fails_the_run(self):
        put_snapshot(self.root, "newprog-raw-2026-11", "20261125T000000Z", {"a": b"x"})
        put_snapshot(self.root, "vigil-pgdump-2026-11", "20261125T000000Z", {"a": b"dump"})
        c = self.catalog([store("vigil-db", "database", "Postgres", field(1, "x"))])
        self.assertEqual(ca.main(["--verify", "--write"], self.archive, c, NOW), 1)
        text = (c / "vigil.json").read_text(encoding="utf-8")
        self.assertIn("vigil-pgdump", text)
        self.assertNotIn("newprog", text)
        self.assertFalse((c / "newprog.json").exists())

    def test_every_mapped_store_exists_or_is_own(self):
        cat = {}
        for f in (ROOT / "catalog").glob("*.json"):
            if f.name != "schema.json":
                d = json.loads(f.read_text(encoding="utf-8"))
                cat[d["program"]] = {s["id"] for s in d["stores"]}
        for lane, (kind, program, sid, *_) in ca.LANES.items():
            self.assertIn(program, cat, lane)
            self.assertTrue(lane.startswith(program), lane)
            if kind == "mirror":
                self.assertIn(sid, cat[program], lane)


if __name__ == "__main__":
    unittest.main()
