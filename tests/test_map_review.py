import json
import subprocess
import sys
from pathlib import Path

import pytest

from parcelcase.map_source import import_map
from parcelcase.map_review import issue, plans, review
from parcelcase.report import report
from parcelcase.store import connect

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
FIVE = ["roll-jia", "roll-yi", "roll-bing", "roll-ding", "roll-wu"]


def _import(db, names=("jia", "yi", "bing", "ding", "wu")):
    for name in names:
        import_map(db, FIX / f"map_roll_{name}.json")


def _review5(db):
    return review(db, [(name, 1) for name in FIVE])


def test_two_minimal_groups_and_tied_minimum_cost_plans(tmp_path):
    db = tmp_path / "state.db"
    _import(db)
    result = _review5(db)
    assert result["status"] == "recorded"
    assert result["consistent"] is False
    by_rolls = {tuple(sorted(x["source_id"] for x in c["rolls"])): c
                for c in result["contradictions"]}
    assert set(by_rolls) == {("roll-bing", "roll-jia", "roll-yi"),
                             ("roll-ding", "roll-jia", "roll-wu")}
    abc = by_rolls[("roll-bing", "roll-jia", "roll-yi")]["witness"]
    assert {leg["sheet_id"] for leg in abc["cycle"]} == {"jia-ab", "yi-bc", "bing-ac"}
    assert abc["implied_zero_interval"] == [-100, -100]
    assert abc["violation"] == "zero_above_high"
    assert all(leg["revision"] == 1 for leg in abc["cycle"])
    df = by_rolls[("roll-ding", "roll-jia", "roll-wu")]["witness"]
    assert {leg["sheet_id"] for leg in df["cycle"]} == {"jia-de", "ding-ef", "wu-df"}
    options = {tuple(sorted(x["source_id"] for x in p["rolls"])): p for p in result["plans"]}
    assert set(options) == {("roll-jia",), ("roll-bing", "roll-wu")}
    assert all(p["cost"] == 2 for p in options.values())
    jia = options[("roll-jia",)]
    assert {s["sheet_id"] for s in jia["segments"]} == {"jia-ab", "jia-de"}
    assert jia["suspended_tiles"] == ["tile-1", "tile-2"]
    assert options[("roll-bing", "roll-wu")]["suspended_tiles"] == ["tile-4", "tile-6"]
    assert jia["remaining_state"] == "consistent_unverified"
    assert result["map_status"] == "unverified_pending_field_remeasure"


def test_issue_order_is_durable_and_idempotent(tmp_path):
    db = tmp_path / "state.db"
    _import(db)
    result = _review5(db)
    plan = next(p for p in result["plans"] if [r["source_id"] for r in p["rolls"]] == ["roll-jia"])
    order = issue(db, result["review_id"], plan["index"])
    assert order["status"] == "issued"
    assert order["cost"] == 2
    assert order["suspended_tiles"] == ["tile-1", "tile-2"]
    assert {s["sheet_id"] for s in order["segments"]} == {"jia-ab", "jia-de"}
    again = issue(db, result["review_id"], plan["index"])
    assert again["status"] == "already_issued"
    assert again["order_id"] == order["order_id"]
    con = connect(db)
    assert con.execute("SELECT count(*) FROM map_order").fetchone()[0] == 1
    con.close()
    shown = report(db)
    assert len(shown["map_reviews"]) == 1
    assert shown["map_reviews"][0]["contradictions"] == result["contradictions"]
    assert shown["map_reviews"][0]["plans"] == result["plans"]
    assert len(shown["map_orders"]) == 1
    kept = shown["map_orders"][0]
    assert kept["id"] == order["order_id"]
    assert kept["suspended_tiles"] == ["tile-1", "tile-2"]
    assert kept["map_status"] == "unverified_pending_field_remeasure"


def test_consistent_rolls_get_no_work_order(tmp_path):
    db = tmp_path / "state.db"
    _import(db, ("jia", "yi"))
    result = review(db, [("roll-jia", 1), ("roll-yi", 1)])
    assert result["consistent"] is True
    assert result["contradictions"] == [] and result["plans"] == []
    with pytest.raises(ValueError, match="no_contradictions"):
        issue(db, result["review_id"], 0)
    assert report(db)["map_orders"] == []


def test_rerun_and_new_revision_keep_old_evidence_snapshot(tmp_path):
    db = tmp_path / "state.db"
    _import(db)
    first = _review5(db)
    rerun = _review5(db)
    assert rerun["status"] == "existing"
    assert rerun["review_id"] == first["review_id"]
    order = issue(db, first["review_id"], 0)
    changed = json.loads((FIX / "map_roll_bing.json").read_text(encoding="utf-8"))
    changed["revision"] = 2
    changed["sheets"][0]["low"] = changed["sheets"][0]["high"] = 90
    path = tmp_path / "bing_v2.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert import_map(db, path)["status"] == "imported"
    second = review(db, [("roll-jia", 1), ("roll-yi", 1), ("roll-bing", 2),
                         ("roll-ding", 1), ("roll-wu", 1)])
    assert second["status"] == "recorded"
    assert second["review_id"] != first["review_id"]
    assert second["consistent"] is False
    shown = report(db)
    assert [r["id"] for r in shown["map_reviews"]] == [first["review_id"], second["review_id"]]
    assert shown["map_reviews"][0]["contradictions"] == first["contradictions"]
    assert shown["map_reviews"][0]["plans"] == first["plans"]
    assert len(shown["map_orders"]) == 1
    assert shown["map_orders"][0]["created_at"] == order["created_at"]
    assert shown["map_orders"][0]["cost"] == order["cost"]


def test_limits_and_unknown_source(tmp_path):
    db = tmp_path / "state.db"
    with pytest.raises(ValueError, match="unknown_source_revision"):
        review(db, [("ghost", 1)])
    for i in range(9):
        doc = {"source_id": f"r{i}", "revision": 1,
               "sheets": [{"sheet_id": f"s{i}", "tile_id": f"t{i}", "from": f"P{i}",
                           "to": f"Q{i}", "low": 0, "high": 0, "remeasure_cost": 1}]}
        path = tmp_path / f"r{i}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        import_map(db, path)
    with pytest.raises(ValueError, match="too_many_rolls"):
        review(db, [(f"r{i}", 1) for i in range(9)])
    doc = {"source_id": "big", "revision": 1,
           "sheets": [{"sheet_id": f"b{i}", "tile_id": "t", "from": f"A{i}", "to": f"B{i}",
                       "low": 0, "high": 0, "remeasure_cost": 1} for i in range(13)]}
    path = tmp_path / "big.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    import_map(db, path)
    with pytest.raises(ValueError, match="too_many_sheets"):
        review(db, [("big", 1)])


def test_fractional_intervals_still_review_consistently(tmp_path):
    db = tmp_path / "state.db"
    import_map(db, FIX / "map_sheets_normal.json")
    result = review(db, [("survey-north", 1)])
    assert result["consistent"] is True
    assert result["map_status"] == "unverified_pending_field_remeasure"


def test_single_roll_can_contradict_itself(tmp_path):
    db = tmp_path / "state.db"
    doc = {"source_id": "self", "revision": 1,
           "sheets": [
               {"sheet_id": "s1", "tile_id": "t1", "from": "A", "to": "B",
                "low": 0, "high": 0, "remeasure_cost": 3},
               {"sheet_id": "s2", "tile_id": "t2", "from": "A", "to": "B",
                "low": 50, "high": 50, "remeasure_cost": 4}]}
    path = tmp_path / "self.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    import_map(db, path)
    result = review(db, [("self", 1)])
    assert result["consistent"] is False
    assert [[r["source_id"] for r in c["rolls"]] for c in result["contradictions"]] == [["self"]]
    assert len(result["plans"]) == 1
    plan = result["plans"][0]
    assert plan["cost"] == 7
    assert plan["suspended_tiles"] == ["t1", "t2"]
    order = issue(db, result["review_id"], 0)
    assert order["status"] == "issued" and order["cost"] == 7


def test_plans_view_and_bad_identifiers(tmp_path):
    db = tmp_path / "state.db"
    _import(db)
    result = _review5(db)
    viewed = plans(db, result["review_id"])
    assert viewed["plans"] == result["plans"]
    assert viewed["contradictions"] == result["contradictions"]
    with pytest.raises(ValueError, match="review_not_found"):
        plans(db, 999)
    with pytest.raises(ValueError, match="plan_not_found"):
        issue(db, result["review_id"], len(result["plans"]))


def test_cli_review_plans_issue_and_report(tmp_path):
    db = tmp_path / "cli.db"

    def run(*args):
        out = subprocess.run([sys.executable, "-m", "parcelcase", *args],
                             cwd=ROOT, capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    for name in ("jia", "yi", "bing", "ding", "wu"):
        assert run("map-import", "--db", str(db),
                   "--input", str(FIX / f"map_roll_{name}.json"))["status"] == "imported"
    sources = [x for name in FIVE for x in ("--source", f"{name}:1")]
    result = run("map-review", "--db", str(db), *sources)
    assert result["consistent"] is False
    assert len(result["contradictions"]) == 2
    assert len(result["plans"]) == 2
    viewed = run("map-plans", "--db", str(db), "--review", str(result["review_id"]))
    assert viewed["plans"] == result["plans"]
    order = run("map-issue", "--db", str(db), "--review", str(result["review_id"]), "--plan", "0")
    assert order["status"] == "issued"
    assert order["cost"] == 2
    shown = run("report", "--db", str(db))
    assert len(shown["map_reviews"]) == 1
    assert len(shown["map_orders"]) == 1
    assert shown["map_orders"][0]["suspended_tiles"] == order["suspended_tiles"]
