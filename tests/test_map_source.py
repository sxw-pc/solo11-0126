import json
from pathlib import Path

import pytest

from parcelcase.map_source import import_map
from parcelcase.report import report


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "map_sheets_normal.json"


def test_map_source_evidence_and_idempotence(tmp_path):
    db = tmp_path / "map.db"
    assert import_map(db, FIXTURE)["status"] == "imported"
    assert import_map(db, FIXTURE)["status"] == "already_imported"
    shown = report(db)["auxiliary"]
    assert len(shown["map_source"]) == 1
    assert [x["sheet_id"] for x in shown["map_sheet"]] == ["north-ab", "north-bc"]
    changed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed["sheets"][0]["high"] = 0.2
    altered = tmp_path / "changed.json"
    altered.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="source_revision_conflict"):
        import_map(db, altered)
    assert len(report(db)["auxiliary"]["map_sheet"]) == 2
