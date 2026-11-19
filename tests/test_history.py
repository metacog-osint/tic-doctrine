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

    def test_a_reading_key_logs_a_new_reading_under_the_same_id(self):
        s1, _ = history.update({}, feed(item("p:fx:A", data_as_of="2026-11-13T00:00:00Z")), health(T0, "src-a"), T0,
                               reading_key="data_as_of")
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        same = item("p:fx:A", data_as_of="2026-11-13T00:00:00Z", title="Reworded")
        s2, quiet = history.update(s1, feed(same), health(t1, "src-a"), t1, reading_key="data_as_of")
        self.assertEqual(quiet, [])                                   # the same reading reworded is an update only
        nxt = item("p:fx:A", data_as_of="2026-11-16T00:00:00Z")
        s3, lines = history.update(s2, feed(nxt), health(t2, "src-a"), t2, reading_key="data_as_of")
        self.assertEqual([(x["change"], x["was"]["data_as_of"], x["was"]["tier"]) for x in lines],
                         [("changed", "2026-11-13T00:00:00Z", "routine")])
        self.assertEqual(lines[0]["item"]["properties"]["data_as_of"], "2026-11-16T00:00:00Z")
        # Without the option the same move is quiet, as before.
        _, off = history.update(s2, feed(nxt), health(t2, "src-a"), t2)
        self.assertEqual(off, [])

    def test_a_reading_key_reports_nothing_for_items_logged_before_it_was_used(self):
        s1, _ = history.update({}, feed(item("p:a:1", data_as_of="2026-11-13T00:00:00Z")), health(T0, "src-a"), T0)
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        s2, lines = history.update(s1, feed(item("p:a:1", data_as_of="2026-11-14T00:00:00Z")), health(t1, "src-a"), t1,
                                   reading_key="data_as_of")
        self.assertEqual(lines, [])                                   # first run with the option: stored, not reported
        _, lines = history.update(s2, feed(item("p:a:1", data_as_of="2026-11-15T00:00:00Z")), health(t2, "src-a"), t2,
                                  reading_key="data_as_of")
        self.assertEqual([x["change"] for x in lines], ["changed"])

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

    def test_a_source_whose_items_are_withheld_as_stale_ends_nothing(self):
        # Cordon withholds a frozen warning list: the source answered (last_ok == checked_at) but its state is stale.
        s1, _ = history.update({}, feed(item("p:a:1", lane="src-a"), item("p:b:1", lane="src-b")),
                               health(T0, "src-a", "src-b"), T0)
        t1 = T0 + timedelta(hours=2)
        rec = health(t1, "src-a", "src-b")
        rec["src-b"]["state"], rec["src-a"]["state"] = "stale", "fresh"
        s2, lines = history.update(s1, feed(), rec, t1)
        self.assertEqual(history.ended_ids_in(lines), {"p:a:1"})
        self.assertIn("p:b:1", s2["open"])
        self.assertEqual(history.lanes_ok({"x": {"last_ok": "t", "checked_at": "t", "state": "late"},
                                           "y": {"last_ok": "t", "checked_at": "t", "state": "never"}}), {"x"})

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


class Subjects(unittest.TestCase):
    """Kit 0.6.0: the log keys on subject_id when an item has one (contract revision 2.1), on id otherwise."""

    def test_a_dated_id_with_a_subject_is_one_open_entry_not_new_and_ended_every_day(self):
        t1 = T0 + timedelta(days=1)
        s1, l1 = history.update({}, feed(item("p:fx:TRY:2026-11-13", subject_id="p:fx:TRY")), health(T0, "src-a"), T0)
        s2, l2 = history.update(s1, feed(item("p:fx:TRY:2026-11-14", subject_id="p:fx:TRY")), health(t1, "src-a"), t1)
        self.assertEqual([(x["change"], x["id"], x["subject_id"]) for x in l1], [("new", "p:fx:TRY:2026-11-13", "p:fx:TRY")])
        self.assertEqual(l2, [])
        self.assertEqual(list(s2["open"]), ["p:fx:TRY"])
        self.assertEqual(s2["open"]["p:fx:TRY"]["item"]["properties"]["id"], "p:fx:TRY:2026-11-14")
        self.assertEqual(s2["open"]["p:fx:TRY"]["updates"], 1)
        t2 = t1 + timedelta(days=1)
        _, l3 = history.update(s2, feed(item("p:fx:TRY:2026-11-15", subject_id="p:fx:TRY", tier="anomaly")),
                               health(t2, "src-a"), t2)
        self.assertEqual([(x["change"], x["id"], x["subject_id"], x["was"]["tier"]) for x in l3],
                         [("changed", "p:fx:TRY:2026-11-15", "p:fx:TRY", "routine")])

    def test_without_a_subject_a_dated_id_is_still_new_and_ended(self):
        t1 = T0 + timedelta(days=1)
        s1, _ = history.update({}, feed(item("p:fx:TRY:2026-11-13")), health(T0, "src-a"), T0)
        _, lines = history.update(s1, feed(item("p:fx:TRY:2026-11-14")), health(t1, "src-a"), t1)
        self.assertEqual(sorted((x["change"], x["id"]) for x in lines),
                         [("ended", "p:fx:TRY:2026-11-13"), ("new", "p:fx:TRY:2026-11-14")])
        self.assertNotIn("subject_id", lines[0])

    def test_the_first_run_with_subject_ids_moves_each_open_entry_to_its_subject(self):
        s1, _ = history.update({}, feed(item("p:a:1")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(item("p:a:1", subject_id="p:thing:1")), health(t1, "src-a"), t1)
        self.assertEqual(lines, [])
        self.assertEqual(list(s2["open"]), ["p:thing:1"])
        self.assertEqual(s2["open"]["p:thing:1"]["first_seen"], "2026-11-14T02:00:00Z")

    def test_a_second_item_of_one_subject_in_a_feed_is_kept_under_its_own_id(self):
        both = feed(item("p:r:new-1", subject_id="p:region:1"), item("p:r:ended-1", subject_id="p:region:1"))
        s1, lines = history.update({}, both, health(T0, "src-a"), T0)
        self.assertEqual(sorted(s1["open"]), ["p:r:ended-1", "p:region:1"])
        self.assertEqual(len(lines), 2)

    def test_an_item_the_linter_dropped_is_not_ended_under_its_subject(self):
        s1, _ = history.update({}, feed(item("p:a:1:d1", subject_id="p:a:1")), health(T0, "src-a"), T0)
        t1 = T0 + timedelta(hours=2)
        s2, lines = history.update(s1, feed(dropped=[{"id": "p:a:1:d1"}]), health(t1, "src-a"), t1)
        self.assertEqual(lines, [])
        self.assertIn("p:a:1", s2["open"])

    def test_a_source_names_its_lane(self):
        f = item("p:a:1", lane="usembassy-sa")
        f["properties"]["sources"][0]["lane"] = "us-embassy-alerts"
        self.assertEqual(history.lane(f), "us-embassy-alerts")
        self.assertEqual(history.lane(item("p:a:1", lane="src-a")), "src-a")

    def test_a_reading_key_works_on_a_subject_and_leaves_last_change_alone(self):
        t1 = T0 + timedelta(days=1)
        a = item("p:fx:TRY:2026-11-13", subject_id="p:fx:TRY", data_as_of="2026-11-13T00:00:00Z")
        b = item("p:fx:TRY:2026-11-14", subject_id="p:fx:TRY", data_as_of="2026-11-14T00:00:00Z")
        s1, _ = history.update({}, feed(a), health(T0, "src-a"), T0, reading_key="data_as_of")
        s2, lines = history.update(s1, feed(b), health(t1, "src-a"), t1, reading_key="data_as_of")
        self.assertEqual([(x["change"], x["subject_id"], x["was"]["data_as_of"]) for x in lines],
                         [("changed", "p:fx:TRY", "2026-11-13T00:00:00Z")])
        self.assertEqual(s2["open"]["p:fx:TRY"]["last_change"], "none", "a new reading is not a change of state")

    def test_a_move_is_raised_lowered_or_changed(self):
        self.assertEqual(history.move(["routine", None], ["anomaly", None]), "raised")
        self.assertEqual(history.move(["warning", None], ["anomaly", None]), "lowered")
        self.assertEqual(history.move(["anomaly", "usgs_volcano:advisory"], ["anomaly", "usgs_volcano:watch"]), "raised")
        self.assertEqual(history.move(["routine", "pager:orange"], ["routine", "pager:yellow"]), "lowered")
        self.assertEqual(history.move(["routine", "pager:orange"], ["routine", "gdacs:orange"]), "changed")
        self.assertEqual(history.move(["routine", None], ["routine", "pager:green"]), "changed")


class FillLastChange(unittest.TestCase):
    """Kit 0.6.0: last_change and last_change_at from the log, for items that do not state them."""

    def test_standing_new_and_moved(self):
        t1, t2 = T0 + timedelta(hours=2), T0 + timedelta(hours=4)
        f0 = feed(item("p:a:1"))
        s1, _ = history.update({}, f0, health(T0, "src-a"), T0)
        self.assertEqual(s1["since"], "2026-11-14T02:00:00Z")
        self.assertEqual(history.fill_last_change(f0, s1), 1)
        self.assertEqual(f0["features"][0]["properties"]["last_change"], "none")
        self.assertNotIn("last_change_at", f0["features"][0]["properties"])
        f1 = feed(item("p:a:1"), item("p:a:2"))
        s2, _ = history.update(s1, f1, health(t1, "src-a"), t1)
        history.fill_last_change(f1, s2)
        self.assertEqual([(f["properties"]["last_change"], f["properties"].get("last_change_at")) for f in f1["features"]],
                         [("none", None), ("new", "2026-11-14T04:00:00Z")])
        f2 = feed(item("p:a:1", tier="anomaly"), item("p:a:2"))
        s3, _ = history.update(s2, f2, health(t2, "src-a"), t2)
        history.fill_last_change(f2, s3)
        self.assertEqual([(f["properties"]["last_change"], f["properties"].get("last_change_at")) for f in f2["features"]],
                         [("raised", "2026-11-14T06:00:00Z"), ("new", "2026-11-14T04:00:00Z")])

    def test_a_program_that_states_it_keeps_its_own(self):
        f = feed(item("p:a:1", last_change="raised", last_change_at="2026-11-13T21:04:48Z"))
        s1, _ = history.update({}, f, health(T0, "src-a"), T0)
        self.assertEqual(history.fill_last_change(f, s1), 0)
        self.assertEqual(f["features"][0]["properties"]["last_change_at"], "2026-11-13T21:04:48Z")

    def test_a_log_begun_before_0_6_0_takes_its_start_from_its_first_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history.run(feed(item("p:a:1")), root, T0, health(T0, "src-a"))
            old = history.load_state(root)                 # make it look like a 0.5.x state
            old.pop("since")
            for e in old["open"].values():
                e.pop("last_change"), e.pop("last_change_at")
            history.save_state(root, old)
            self.assertEqual(history.first_run(root), "2026-11-14T02:00:00Z")
            t1 = T0 + timedelta(hours=2)
            f = feed(item("p:a:1"), item("p:a:2"))
            history.run(f, root, t1, health(t1, "src-a"), fill=True)
            self.assertEqual([x["properties"]["last_change"] for x in f["features"]], ["none", "new"])
            self.assertEqual(history.load_state(root)["since"], "2026-11-14T02:00:00Z")
            logged = history.read_days(root, "2026-11-14", "2026-11-14")[-1]
            self.assertEqual(logged["item"]["properties"]["last_change"], "new", "the log carries the filled item")

    def test_the_command_rewrites_the_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = tmp / "feed.geojson"
            path.write_text(json.dumps(feed(item("p:a:1"), health=health(T0, "src-a"))), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                history.main([str(path), "--dir", str(tmp / "h"), "--now", "2026-11-14T02:00:00Z",
                              "--fill-last-change"])
            self.assertIn("last_change on 1 of 1 items", out.getvalue())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["features"][0]["properties"]["last_change"],
                             "none")

    def test_without_now_the_run_takes_the_feeds_own_time_and_the_contract_check_passes(self):
        """Kit 0.6.3. Blackout, 18 Nov 2026: the history step ran seconds after the build set published_at, stamped
        a new item's last_change_at with the wall clock, and the contract check failed every deploy."""
        from tic_doctrine import contract
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = tmp / "feed.geojson"
            for gen, ids in (("2026-11-14T02:00:00Z", ["p:a:1"]), ("2026-11-14T04:00:00Z", ["p:a:1", "p:a:2"])):
                f = feed(*(item(i, published_at=gen) for i in ids), generated_at=gen)
                path.write_text(json.dumps(f), encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(history.main([str(path), "--dir", str(tmp / "h"), "--fill-last-change"]), 0)
            out = json.loads(path.read_text(encoding="utf-8"))
            p = {x["properties"]["id"]: x["properties"] for x in out["features"]}
            self.assertEqual((p["p:a:2"]["last_change"], p["p:a:2"].get("last_change_at")), ("new", "2026-11-14T04:00:00Z"))
            self.assertEqual(p["p:a:1"]["last_change"], "none")
            for x in out["features"]:
                errors = [m for _, lvl, m in contract.check(x) if lvl == "error"]
                self.assertEqual(errors, [], x["properties"]["id"])

    def test_the_run_time_is_the_feeds_unless_it_is_missing_or_ahead_of_the_clock(self):
        wall = datetime(2026, 11, 18, 22, 14, tzinfo=timezone.utc)
        self.assertEqual(history.run_time({"generated_at": "2026-11-18T22:13:50Z"}, wall),
                         datetime(2026, 11, 18, 22, 13, 50, tzinfo=timezone.utc))
        self.assertEqual(history.run_time({}, wall), wall)
        self.assertEqual(history.run_time({"generated_at": "2026-11-19T00:00:00Z"}, wall), wall)


if __name__ == "__main__":
    unittest.main()
