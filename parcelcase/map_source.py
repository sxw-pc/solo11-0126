"""Import field survey sheets as immutable evidence, without inferring a true map."""
import hashlib
import json
from pathlib import Path

from .store import connect


def import_map(db_path, input_path):
    raw = Path(input_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("object_required")
    source_id = doc.get("source_id")
    revision = doc.get("revision")
    sheets = doc.get("sheets")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id_required")
    if type(revision) is not int or revision < 1:
        raise ValueError("positive_revision_required")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("sheets_required")
    checked = []
    seen = set()
    for item in sheets:
        if not isinstance(item, dict):
            raise ValueError("sheet_object_required")
        sheet_id, tile_id = item.get("sheet_id"), item.get("tile_id")
        point_a, point_b = item.get("from"), item.get("to")
        if any(not isinstance(v, str) or not v.strip() for v in (sheet_id, tile_id, point_a, point_b)):
            raise ValueError("sheet_identity_required")
        if sheet_id in seen or point_a == point_b:
            raise ValueError("duplicate_sheet_or_same_point")
        seen.add(sheet_id)
        low, high, cost = item.get("low"), item.get("high"), item.get("remeasure_cost")
        if any(type(v) not in (int, float) for v in (low, high, cost)) or low > high or cost <= 0:
            raise ValueError("invalid_measurement_or_cost")
        checked.append((sheet_id, tile_id, point_a, point_b, low, high, cost))
    db = connect(db_path)
    try:
        old = db.execute("SELECT digest FROM map_source WHERE source_id=? AND revision=?", (source_id, revision)).fetchone()
        if old:
            if old["digest"] != digest:
                raise ValueError("source_revision_conflict")
            return {"source_id": source_id, "revision": revision, "status": "already_imported", "sheets": len(checked)}
        with db:
            db.execute("INSERT INTO map_source(source_id,revision,digest,raw) VALUES(?,?,?,?)",
                       (source_id, revision, digest, raw.decode("utf-8")))
            db.executemany("""INSERT INTO map_sheet(source_id,revision,sheet_id,tile_id,point_a,point_b,low,high,remeasure_cost)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           ((source_id, revision, *row) for row in checked))
        return {"source_id": source_id, "revision": revision, "status": "imported", "sheets": len(checked)}
    finally:
        db.close()
