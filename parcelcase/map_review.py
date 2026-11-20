"""Re-survey review: minimal conflicting roll groups, minimum-cost plans, work orders.

A review pins a set of imported map sources (whole rolls) and asks whether one
assignment of control-point coordinates can explain every sheet at once.  Each
sheet constrains (to - from) to an integer-millimetre interval; the origin is
free, so sheets become difference constraints and a contradiction is exactly a
negative cycle.  Reviews, candidate plans and issued orders are stored as
immutable evidence: re-runs return the stored review, new measurements arrive
as new sources or revisions, and a consistent remainder is reported as
unverified, never as a proven-true map.
"""
import json
from fractions import Fraction
from itertools import combinations

from .source import canonical, digest
from .store import connect

MAX_ROLLS = 8
MAX_SHEETS = 12
MAP_STATUS = "unverified_pending_field_remeasure"
REMAINING_STATE = "consistent_unverified"


def _num(value):
    frac = Fraction(value)
    return frac.numerator if frac.denominator == 1 else float(frac)


def _normalize(sources):
    pairs = set()
    for item in sources:
        source_id, revision = item
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_revision_required")
        if type(revision) is not int or revision < 1:
            raise ValueError("source_revision_required")
        pairs.add((source_id, revision))
    if not pairs:
        raise ValueError("sources_required")
    return sorted(pairs)


def _load_rolls(db, pairs):
    rolls = []
    for source_id, revision in pairs:
        known = db.execute("SELECT 1 FROM map_source WHERE source_id=? AND revision=?",
                           (source_id, revision)).fetchone()
        if not known:
            raise ValueError("unknown_source_revision")
        rows = db.execute(
            "SELECT sheet_id,tile_id,point_a,point_b,low,high,remeasure_cost FROM map_sheet "
            "WHERE source_id=? AND revision=? ORDER BY sheet_id", (source_id, revision)).fetchall()
        sheets = [{"sheet_id": x["sheet_id"], "tile_id": x["tile_id"],
                   "source_id": source_id, "revision": revision,
                   "from": x["point_a"], "to": x["point_b"],
                   "low": Fraction(x["low"]), "high": Fraction(x["high"]),
                   "cost": Fraction(x["remeasure_cost"])} for x in rows]
        rolls.append({"source_id": source_id, "revision": revision, "sheets": sheets,
                      "cost": sum((s["cost"] for s in sheets), Fraction(0)),
                      "tiles": sorted({s["tile_id"] for s in sheets})})
    return rolls


def _negative_cycle(sheets):
    """One contradictory directed cycle of sheets, or None when the sheets are consistent."""
    points = sorted({s["from"] for s in sheets} | {s["to"] for s in sheets})
    edges = []
    for sheet in sheets:
        edges.append((sheet["from"], sheet["to"], sheet["high"], sheet, "forward"))
        edges.append((sheet["to"], sheet["from"], -sheet["low"], sheet, "backward"))
    dist = {point: Fraction(0) for point in points}
    pred = {}
    touched = None
    for _ in range(len(points)):
        touched = None
        for u, v, weight, sheet, direction in edges:
            if dist[u] + weight < dist[v]:
                dist[v] = dist[u] + weight
                pred[v] = (u, sheet, direction)
                touched = v
        if touched is None:
            return None
    node = touched
    for _ in range(len(points)):
        node = pred[node][0]
    cycle = []
    start = node
    while True:
        u, sheet, direction = pred[node]
        cycle.append({"from": u, "to": node, "sheet": sheet, "direction": direction})
        node = u
        if node == start:
            break
    cycle.reverse()
    return cycle


def _witness(cycle):
    """Reviewable evidence: composing the cycle's intervals must allow zero, and does not."""
    legs = []
    low = Fraction(0)
    high = Fraction(0)
    for leg in cycle:
        sheet = leg["sheet"]
        if leg["direction"] == "forward":
            lo, hi = sheet["low"], sheet["high"]
        else:
            lo, hi = -sheet["high"], -sheet["low"]
        low += lo
        high += hi
        legs.append({"sheet_id": sheet["sheet_id"], "source_id": sheet["source_id"],
                     "revision": sheet["revision"], "from": leg["from"], "to": leg["to"],
                     "direction": leg["direction"], "interval": [_num(lo), _num(hi)]})
    violation = "zero_above_high" if high < 0 else "zero_below_low"
    path = "->".join([legs[0]["from"]] + [leg["to"] for leg in legs])
    return {"cycle": legs, "implied_zero_interval": [_num(low), _num(high)],
            "violation": violation,
            "summary": f"{path} closes with implied displacement [{_num(low)},{_num(high)}] mm, which excludes 0"}


def _minimal_conflicting_groups(rolls):
    """Every roll set that is jointly inconsistent but consistent once any one roll is dropped."""
    found = []
    count = len(rolls)
    for size in range(1, count + 1):
        for combo in combinations(range(count), size):
            idx = frozenset(combo)
            if any(group <= idx for group, _ in found):
                continue
            sheets = [s for i in combo for s in rolls[i]["sheets"]]
            cycle = _negative_cycle(sheets)
            if cycle is not None:
                found.append((idx, cycle))
    return found


def _plan(rolls, mask):
    chosen = [i for i in range(len(rolls)) if mask >> i & 1]
    segments = []
    tiles = set()
    cost = Fraction(0)
    for i in chosen:
        cost += rolls[i]["cost"]
        tiles.update(rolls[i]["tiles"])
        for s in rolls[i]["sheets"]:
            segments.append({"sheet_id": s["sheet_id"], "source_id": s["source_id"],
                             "revision": s["revision"], "tile_id": s["tile_id"],
                             "from": s["from"], "to": s["to"],
                             "interval": [_num(s["low"]), _num(s["high"])],
                             "remeasure_cost": _num(s["cost"])})
    plan = {"rolls": [{"source_id": rolls[i]["source_id"], "revision": rolls[i]["revision"]}
                      for i in chosen],
            "cost": _num(cost), "segments": segments, "suspended_tiles": sorted(tiles),
            "remaining_rolls": [{"source_id": r["source_id"], "revision": r["revision"]}
                                for i, r in enumerate(rolls) if not mask >> i & 1],
            "remaining_state": REMAINING_STATE}
    return plan, cost


def _minimum_cost_plans(rolls, groups):
    """Every whole-roll set of minimum total cost whose re-survey breaks all groups."""
    count = len(rolls)
    best = None
    masks = []
    for mask in range(1, 1 << count):
        if not all(any(mask >> i & 1 for i in group) for group, _ in groups):
            continue
        cost = sum((rolls[i]["cost"] for i in range(count) if mask >> i & 1), Fraction(0))
        if best is None or cost < best:
            best, masks = cost, [mask]
        elif cost == best:
            masks.append(mask)
    masks.sort(key=lambda m: tuple((rolls[i]["source_id"], rolls[i]["revision"])
                                   for i in range(count) if m >> i & 1))
    return [{"index": index, **_plan(rolls, mask)[0]} for index, mask in enumerate(masks)]


def _public_sheet(sheet):
    return {"sheet_id": sheet["sheet_id"], "tile_id": sheet["tile_id"],
            "from": sheet["from"], "to": sheet["to"],
            "low": _num(sheet["low"]), "high": _num(sheet["high"]),
            "remeasure_cost": _num(sheet["cost"])}


def _snapshot(rolls):
    return {"sources": [{"source_id": r["source_id"], "revision": r["revision"]} for r in rolls],
            "sheets": [dict(_public_sheet(s), source_id=s["source_id"], revision=s["revision"])
                       for r in rolls for s in r["sheets"]]}


def review(db_path, sources):
    """Review the pinned source versions and store the immutable evidence snapshot."""
    pairs = _normalize(sources)
    db = connect(db_path)
    db.execute("BEGIN IMMEDIATE")
    try:
        rolls = _load_rolls(db, pairs)
        if len(rolls) > MAX_ROLLS:
            raise ValueError("too_many_rolls")
        if sum(len(r["sheets"]) for r in rolls) > MAX_SHEETS:
            raise ValueError("too_many_sheets")
        fingerprint = digest(_snapshot(rolls))
        old = db.execute("SELECT id FROM map_review WHERE input_digest=?", (fingerprint,)).fetchone()
        if old:
            result = _describe_review(db, old["id"], "existing")
            db.commit()
            return result
        groups = _minimal_conflicting_groups(rolls)
        contradictions = [
            {"rolls": [{"source_id": rolls[i]["source_id"], "revision": rolls[i]["revision"]}
                       for i in sorted(group)],
             "witness": _witness(cycle)}
            for group, cycle in groups]
        plans = _minimum_cost_plans(rolls, groups) if groups else []
        detail = {"rolls": [{"source_id": r["source_id"], "revision": r["revision"],
                             "cost": _num(r["cost"]), "tiles": r["tiles"],
                             "sheets": [_public_sheet(s) for s in r["sheets"]]} for r in rolls],
                  "contradictions": contradictions, "plans": plans, "map_status": MAP_STATUS}
        cur = db.execute(
            "INSERT INTO map_review(sources,input_digest,consistent,detail) VALUES(?,?,?,?)",
            (canonical([{"source_id": s, "revision": r} for s, r in pairs]), fingerprint,
             0 if groups else 1, canonical(detail)))
        result = _describe_review(db, cur.lastrowid, "recorded")
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _describe_review(db, review_id, status):
    row = db.execute("SELECT * FROM map_review WHERE id=?", (review_id,)).fetchone()
    if not row:
        raise ValueError("review_not_found")
    detail = json.loads(row["detail"])
    return {"review_id": row["id"], "status": status, "created_at": row["created_at"],
            "sources": json.loads(row["sources"]), "consistent": bool(row["consistent"]),
            "contradictions": detail["contradictions"], "plans": detail["plans"],
            "map_status": detail["map_status"]}


def plans(db_path, review_id):
    """Read back the stored contradictions and candidate plans of one review."""
    db = connect(db_path)
    try:
        return _describe_review(db, review_id, "stored")
    finally:
        db.close()


def issue(db_path, review_id, plan_index):
    """Issue a re-survey work order for one candidate plan of a contradictory review."""
    db = connect(db_path)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT * FROM map_review WHERE id=?", (review_id,)).fetchone()
        if not row:
            raise ValueError("review_not_found")
        if row["consistent"]:
            raise ValueError("no_contradictions")
        detail = json.loads(row["detail"])
        options = detail["plans"]
        if type(plan_index) is not int or not 0 <= plan_index < len(options):
            raise ValueError("plan_not_found")
        old = db.execute("SELECT id FROM map_order WHERE review_id=? AND plan_index=?",
                         (review_id, plan_index)).fetchone()
        if old:
            result = _describe_order(db, old["id"], "already_issued")
            db.commit()
            return result
        plan = options[plan_index]
        order = {"review_id": review_id, "plan_index": plan_index,
                 "sources": json.loads(row["sources"]), "rolls": plan["rolls"],
                 "cost": plan["cost"], "segments": plan["segments"],
                 "suspended_tiles": plan["suspended_tiles"],
                 "remaining_rolls": plan["remaining_rolls"],
                 "remaining_state": plan["remaining_state"], "map_status": MAP_STATUS}
        cur = db.execute(
            "INSERT INTO map_order(review_id,plan_index,sources,rolls,cost,suspended_tiles,detail) "
            "VALUES(?,?,?,?,?,?,?)",
            (review_id, plan_index, row["sources"], canonical(plan["rolls"]),
             json.dumps(plan["cost"]), canonical(plan["suspended_tiles"]), canonical(order)))
        result = _describe_order(db, cur.lastrowid, "issued")
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _describe_order(db, order_id, status):
    row = db.execute("SELECT * FROM map_order WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise ValueError("order_not_found")
    detail = json.loads(row["detail"])
    return {"order_id": row["id"], "status": status, "created_at": row["created_at"], **detail}
