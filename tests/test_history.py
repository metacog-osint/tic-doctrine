"""Offline tests for the history log (python/tic_doctrine/history.py). Run as a plain script or with unittest.

The items are the kit's own good fixture (tests/fixtures/good.geojson) with ids, tiers and lanes varied here. The
behaviour on recorded data is tested in Elements, where the format was first written (elements/tests/test_history.py).
"""

import copy
import gzip
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from tic_doctrine import history  # noqa: E402

GOOD = json.loads((ROOT / "tests" / "fixtures" / "good.geojson").read_text(encoding="utf-8"))
T0 = datetime(2026, 11, 14, 2, 0, tzinfo=timezone.utc)


def item(iid, lane="src-a", tier="routine", **props):
    f = copy.deepcopy(GOOD["features"][0])
    p = f["properties"]
    p.update({"id": iid, "tier": tier, "program": "testprog"}, **props)
    p["sources"] = [dict((p.get("sources") or [{}])[0], id=lane, accessed_at="2026-11-14T02:00:00Z")]
    return f


def feed(*items, **extra):
    return {"type": "FeatureCollection", "program": "testprog", "features": list(items), **extra}


def health(now, *ok, failed=()):
    at = history._stamp(now)
    rec = {k: {"last_ok": at, "checked_at": at} for k in ok}
    rec.update({k: {"last_ok": "2026-11-01T00:00:00Z", "checked_at": at} for k in failed})
    return rec


class Update(unittest.TestCase):
    def test_first_run_logs_every_item_new_with_the_full_item(self):
        state, lines = history.update({}, feed(item("p:a:1"), item("p:a:2")), health(T0, "src-a"), T0)
        self.assertEqual([(x["change"], x["id"]) for x in lines], [("new", "p:a:1"), ("new", "p:a:2")])
        x = lines[0]
        self.assertEqual((x["format"], x["program"], x["lane"]), ("tic-history/1", "testprog", "src-a"))
        self.assertEqual(x["item"]["properties"]["id"], "p:a:1")
        self.assertEqual((x["first_seen"], x["last_seen"], x["updates"]), ("2026-11-14T02:00:00Z",) * 2 + (0,))
        self.assertEqual(sorted(state["open"]), ["p:a:1", "p:a:2"])

    def test_an_unchanged_item_is_quiet_and_volatile_fields_are_no_change(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        later = item("p:a:1", published_at="2026-11-14T04:00:00Z")
        later["properties"]["sources"][0]["accessed_at"] = "2026-11-14T04:00:00Z"
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(later), health(t1, "src-a"), t1)
        self.assertEqual(lines, [])
        self.assertEqual(s2["open"]["p:a:1"]["updates"], 0)
        self.assertEqual(s2["open"]["p:a:1"]["last_seen"], "2026-11-14T04:00:00Z")

    def test_an_edit_that_is_not_a_status_change_only_counts_an_update(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(item("p:a:1", title="Reworded")), health(t1, "src-a"), t1)
        self.assertEqual(lines, [])
        self.assertEqual(s2["open"]["p:a:1"]["updates"], 1)

    def test_a_tier_move_is_a_changed_line_and_the_peak_is_kept(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        s2, up = history.update(s1, feed(item("p:a:1", tier="warning")), health(t1, "src-a"), t1)
        self.assertEqual([(x["change"], x["was"]["tier"], x["peak_tier"]) for x in up], [("changed", "routine", "warning")])
        s3, down = history.update(s2, feed(item("p:a:1", tier="anomaly")), health(t2, "src-a"), t2)
        self.assertEqual([(x["change"], x["was"]["tier"], x["peak_tier"]) for x in down], [("changed", "warning", "warning")])

    def test_an_item_that_left_ends_with_its_last_version(self):
        s1, _ = history.update({}, feed(item("p:a:1", title="Last words"), item("p:a:2")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(item("p:a:2")), health(t1, "src-a"), t1)
        self.assertEqual([(x["change"], x["id"], x["end_reason"]) for x in lines], [("ended", "p:a:1", "left the feed")])
        self.assertEqual(lines[0]["item"]["properties"]["title"], "Last words")
        self.assertEqual((lines[0]["last_seen"], lines[0]["ended_at"]), ("2026-11-14T02:00:00Z", "2026-11-14T04:00:00Z"))
        self.assertNotIn("p:a:1", s2["open"])

    def test_the_end_time_is_the_items_own_when_it_ran_out_between_runs(self):
        s1, _ = history.update({}, feed(item("p:a:1", valid_until="2026-11-14T03:10:00Z"),
                                        item("p:a:2", valid_until="2026-11-14T01:00:00Z")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        _, lines = history.update(s1, feed(), health(t1, "src-a"), t1)
        self.assertEqual({x["id"]: x["ended_at"] for x in lines},
                         {"p:a:1": "2026-11-14T03:10:00Z", "p:a:2": "2026-11-14T04:00:00Z"})

    def test_a_failed_source_ends_nothing_of_its_own(self):
        s1, _ = history.update({}, feed(item("p:a:1", lane="src-a"), item("p:b:1", lane="src-b")),
                               health(T0, "src-a", "src-b"), T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(), health(t1, "src-a", failed=("src-b",)), t1)
        self.assertEqual(history.ended_ids_in(lines), {"p:a:1"})
        self.assertIn("p:b:1", s2["open"])

    def test_an_item_the_linter_dropped_is_not_ended(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        _, lines = history.update(s1, feed(dropped=[{"id": "p:a:1"}]), health(t1, "src-a"), t1)
        self.assertEqual(lines, [])

    def test_an_item_that_comes_back_is_new_again(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        s2, _ = history.update(s1, feed(), health(t1, "src-a"), t1)
        _, lines = history.update(s2, feed(item("p:a:1")), health(t2, "src-a"), t2)
        self.assertEqual([(x["change"], x["first_seen"]) for x in lines], [("new", "2026-11-14T06:00:00Z")])

    def test_with_no_health_record_every_lane_counts_as_read(self):
        s1, _ = history.update({}, feed(item("p:a:1"), item("p:a:2")), None, T0)
        t1 = T0 + timedelta(hours=2)
        _, lines = history.update(s1, feed(item("p:a:2")), None, t1)
        self.assertEqual(history.ended_ids_in(lines), {"p:a:1"})

    def test_with_no_health_record_an_empty_feed_ends_nothing(self):
        s1, _ = history.update({}, feed(item("p:a:1"), item("p:a:2")), None, T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(), None, t1)
        self.assertEqual(lines, [])
        self.assertEqual(len(s2["open"]), 2)

    def test_the_caller_can_name_the_lanes_and_say_which_were_read(self):
        # COP's case: a lane is a program, and a program is read when its feed came fresh this build.
        prog = lambda f: f["properties"]["program"]                                    # noqa: E731
        a, b = item("x:1", program="alpha"), item("y:1", program="beta")
        a["properties"]["program"], b["properties"]["program"] = "alpha", "beta"
        s1, _ = history.update({}, feed(a, b), None, T0, ok={"alpha", "beta"}, lane_of=prog)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(), None, t1, ok={"alpha"}, lane_of=prog)
        self.assertEqual([(x["id"], x["lane"]) for x in lines], [("x:1", "alpha")])
        self.assertIn("y:1", s2["open"])

    def test_extra_volatile_fields_can_be_named(self):
        s1, _ = history.update({}, feed(item("p:a:1", cop_pick=1)), None, T0, volatile=("published_at", "cop_pick"))
        t1 = T0 + timedelta(hours=2)
        s2, _ = history.update(s1, feed(item("p:a:1", cop_pick=7)), None, t1, volatile=("published_at", "cop_pick"))
        self.assertEqual(s2["open"]["p:a:1"]["updates"], 0)

    def test_an_item_caught_between_runs_is_new_and_ended_at_once_and_only_once(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        missed = item("p:a:9", data_as_of="2026-11-14T02:20:00Z", valid_until="2026-11-14T03:00:00Z")
        s2, lines = history.update(s1, feed(item("p:a:1")), health(t1, "src-a"), t1, [missed, item("p:a:1")])
        self.assertEqual([(x["change"], x["id"], x["seen_live"]) for x in lines],
                         [("new", "p:a:9", False), ("ended", "p:a:9", False)])
        self.assertEqual((lines[1]["first_seen"], lines[1]["ended_at"]), ("2026-11-14T02:20:00Z", "2026-11-14T03:00:00Z"))
        _, again = history.update(s2, feed(item("p:a:1")), health(t2, "src-a"), t2, [missed])
        self.assertEqual(again, [])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "history"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_file_per_day_then_gzipped_once_with_the_same_bytes_anywhere(self):
        day1, day2 = datetime(2026, 11, 13, 22, 0, tzinfo=timezone.utc), datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
        history.run(feed(item("p:a:1")), self.root, day1, health(day1, "src-a"))
        self.assertTrue(history.log_path(self.root, "2026-11-13").exists())
        history.run(feed(item("p:a:2")), self.root, day2, health(day2, "src-a"))
        closed = history.log_path(self.root, "2026-11-13", closed=True)
        self.assertTrue(closed.exists())
        self.assertFalse(history.log_path(self.root, "2026-11-13").exists())
        first = closed.read_bytes()
        self.assertEqual(first[4:8], b"\x00\x00\x00\x00")                # no timestamp in the gzip header
        lines = history.read_days(self.root, "2026-11-13", "2026-11-14")
        self.assertEqual([(x["change"], x["id"]) for x in lines],
                         [("new", "p:a:1"), ("new", "p:a:2"), ("ended", "p:a:1")])

    def test_state_round_trip_one_item_per_line(self):
        history.run(feed(item("p:a:1"), item("p:a:2")), self.root, T0, health(T0, "src-a"))
        text = (self.root / "state.json").read_text(encoding="utf-8")
        self.assertEqual(len(text.splitlines()), 4)
        self.assertEqual(sorted(history.load_state(self.root)["open"]), ["p:a:1", "p:a:2"])

    def test_the_ended_list_holds_recent_ends_that_are_not_open_again(self):
        t1, t2, t3 = (T0 + timedelta(hours=h) for h in (2, 4, 6))
        history.run(feed(item("p:a:1"), item("p:a:2"), item("p:a:3")), self.root, T0, health(T0, "src-a"))
        history.run(feed(item("p:a:3")), self.root, t1, health(t1, "src-a"))                 # 1 and 2 end
        history.run(feed(item("p:a:2"), item("p:a:3")), self.root, t2, health(t2, "src-a"))  # 2 is back
        coll = history.ended_collection(self.root, history.load_state(self.root), t3, program="testprog")
        self.assertEqual([f["properties"]["id"] for f in coll["features"]], ["p:a:1"])
        self.assertEqual((coll["format"], coll["program"], coll["window_days"]), ("tic-history/1", "testprog", 7))
        self.assertEqual(coll["features"][0]["history"]["ended_at"], "2026-11-14T04:00:00Z")
        self.assertNotIn("history", coll["features"][0]["properties"])
        old = history.ended_collection(self.root, history.load_state(self.root), t3 + timedelta(days=8))
        self.assertEqual(old["features"], [])


class CommandLine(unittest.TestCase):
    def test_the_command_logs_a_feed_file_and_writes_the_ended_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "feed.geojson").write_text(json.dumps(feed(item("p:a:1"), item("p:a:2"), health=health(T0, "src-a"))),
                                              encoding="utf-8")
            args = [str(tmp / "feed.geojson"), "--dir", str(tmp / "history"), "--ended", str(tmp / "site" / "ended.geojson")]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(history.main(args + ["--now", "2026-11-14T02:00:00Z"]), 0)
            self.assertIn("2 new, 0 changed, 0 ended (health record)", out.getvalue())
            t1 = T0 + timedelta(hours=2)
            (tmp / "feed.geojson").write_text(json.dumps(feed(item("p:a:2"), health=health(t1, "src-a"))), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(history.main(args + ["--now", "2026-11-14T04:00:00Z"]), 0)
            self.assertIn("0 new, 0 changed, 1 ended", out.getvalue())
            ended = json.loads((tmp / "site" / "ended.geojson").read_text(encoding="utf-8"))
            self.assertEqual([f["properties"]["id"] for f in ended["features"]], ["p:a:1"])
            self.assertEqual(ended["program"], "testprog")

    def test_a_lane_the_health_record_does_not_name_is_warned_about_and_can_be_mapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rec = health(T0, "embassies")
            (tmp / "feed.geojson").write_text(json.dumps(feed(item("p:e:1", lane="embassy-mx"), health=rec)),
                                              encoding="utf-8")
            base = [str(tmp / "feed.geojson"), "--now", "2026-11-14T02:00:00Z"]
            with redirect_stdout(io.StringIO()) as out:
                history.main(base + ["--dir", str(tmp / "plain")])
            self.assertIn("WARNING 1 open items", out.getvalue())
            self.assertIn("embassy-mx", out.getvalue())
            with redirect_stdout(io.StringIO()) as out:
                history.main(base + ["--dir", str(tmp / "mapped"), "--lane-map", "embassy-*=embassies"])
            self.assertNotIn("WARNING", out.getvalue())
            self.assertEqual(history.load_state(tmp / "mapped")["open"]["p:e:1"]["lane"], "embassies")

    def test_an_exact_lane_name_wins_over_a_prefix(self):
        lane_of = history.mapped_lane({"embassy-*": "embassies", "embassy-mx": "mexico"})
        self.assertEqual(lane_of(item("a", lane="embassy-mx")), "mexico")
        self.assertEqual(lane_of(item("a", lane="embassy-ht")), "embassies")
        self.assertEqual(lane_of(item("a", lane="other")), "other")

    def test_tic_py_knows_the_command(self):
        text = (ROOT / "tic.py").read_text(encoding="utf-8")
        self.assertIn('cmd == "history"', text)

    def test_a_closed_day_reads_back_through_gzip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history.append_log(root, [{"at": "2026-11-12T01:00:00Z", "change": "new", "id": "p:a:1"}])
            history.close_days(root, "2026-11-14")
            with gzip.open(history.log_path(root, "2026-11-12", closed=True), "rt", encoding="utf-8") as fh:
                self.assertEqual(json.loads(fh.readline())["id"], "p:a:1")


if __name__ == "__main__":
    unittest.main()
