"""Adopt a public notice while preserving conflicting and superseded evidence."""
from .source import read,digest,canonical,utc
from .store import connect
from .policy import TABLES,validate_notice

def adopt(db_path,input_path):
    doc=read(input_path)
    for key in ("source_id","revision","published_at","effective_from","effective_until","payload"):
        if key not in doc: raise ValueError("notice_missing_"+key)
    if not isinstance(doc["revision"],int) or doc["revision"]<1: raise ValueError("bad_revision")
    if utc(doc["effective_from"])>=utc(doc["effective_until"]): raise ValueError("bad_window")
    utc(doc["published_at"])
    state,reason=validate_notice(doc)
    db=connect(db_path);t=TABLES;fingerprint=digest(doc)
    db.execute("BEGIN IMMEDIATE")
    try:
        old=db.execute("SELECT digest FROM source_event WHERE source_id=? AND revision=?",
                       (doc["source_id"],doc["revision"])).fetchone()
        if old and old["digest"]!=fingerprint:
            db.execute("INSERT INTO source_conflict(source_id,revision,digest,reason) VALUES (?,?,?,?)",
                       (doc["source_id"],doc["revision"],fingerprint,"same_revision_different_bytes"))
            db.execute(f"UPDATE {t['notice']} SET state='conflict' WHERE id=?",(doc["source_id"],))
            _stale(db,doc["source_id"])
            result={"source":doc["source_id"],"revision":doc["revision"],"state":"conflict",
                    "reason":"same_revision_different_bytes"}
        elif old:
            row=db.execute(f"SELECT state,reason FROM {t['revision']} WHERE source_id=? AND revision=?",
                           (doc["source_id"],doc["revision"])).fetchone()
            result={"source":doc["source_id"],"revision":doc["revision"],"state":row["state"],"reason":row["reason"]}
        else:
            db.execute("INSERT INTO source_event VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                       (doc["source_id"],doc["revision"],fingerprint,canonical(doc)))
            current=db.execute(f"SELECT * FROM {t['notice']} WHERE id=?",(doc["source_id"],)).fetchone()
            if current and doc["revision"]<current["current_revision"]:
                state,reason="historical","older_revision_preserved"
            db.execute(f"INSERT INTO {t['revision']} VALUES (?,?,?,?,?,?,?,?,?)",
                       (doc["source_id"],doc["revision"],doc["published_at"],doc["effective_from"],
                        doc["effective_until"],fingerprint,state,reason,canonical(doc["payload"])))
            if not current:
                db.execute(f"INSERT INTO {t['notice']}(id,current_revision,state) VALUES (?,?,?)",
                           (doc["source_id"],doc["revision"],state))
            elif doc["revision"]>current["current_revision"]:
                db.execute(f"UPDATE {t['revision']} SET state='superseded' WHERE source_id=? AND revision=?",
                           (doc["source_id"],current["current_revision"]))
                db.execute(f"UPDATE {t['notice']} SET current_revision=?,state=?,changed_at=CURRENT_TIMESTAMP WHERE id=?",
                           (doc["revision"],state,doc["source_id"]))
                _stale(db,doc["source_id"])
            result={"source":doc["source_id"],"revision":doc["revision"],"state":state,"reason":reason}
        db.commit()
    except Exception:
        db.rollback();raise
    finally: db.close()
    return result

def _stale(db,source_id):
    t=TABLES
    db.execute(f"UPDATE {t['assessment']} SET stale=1 WHERE case_id IN (SELECT id FROM {t['case']} WHERE source_id=?)",
               (source_id,))
    db.execute(f"UPDATE {t['obligation']} SET state='stale' WHERE assessment_id IN "
               f"(SELECT a.id FROM {t['assessment']} a JOIN {t['case']} c ON c.id=a.case_id WHERE c.source_id=?)",
               (source_id,))

