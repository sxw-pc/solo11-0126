"""Business cases: a version-bound decision distinct from public-source adoption."""
from .source import read,digest,canonical,utc
from .store import connect
from .policy import TABLES,assess_case
import json

def assess(db_path,input_path):
    doc=read(input_path)
    for key in ("case_id","source_id","at","facts"):
        if key not in doc: raise ValueError("case_missing_"+key)
    moment=utc(doc["at"]);fingerprint=digest(doc);t=TABLES;db=connect(db_path)
    db.execute("BEGIN IMMEDIATE")
    try:
        case=db.execute(f"SELECT * FROM {t['case']} WHERE id=?",(doc["case_id"],)).fetchone()
        if case and case["input_hash"]!=fingerprint:raise ValueError("case_identity_conflict")
        if not case:
            db.execute(f"INSERT INTO {t['case']} VALUES (?,?,?,?,?)",
                       (doc["case_id"],doc["source_id"],doc["at"],canonical(doc["facts"]),fingerprint))
        existing=db.execute(f"SELECT * FROM {t['assessment']} WHERE case_id=? ORDER BY id DESC LIMIT 1",
                            (doc["case_id"],)).fetchone()
        if existing and not existing["stale"]:
            result=_describe(db,existing["id"]);db.commit();return result
        notice=db.execute(f"SELECT * FROM {t['notice']} WHERE id=?",(doc["source_id"],)).fetchone()
        revision=db.execute(f"SELECT * FROM {t['revision']} WHERE source_id=? AND revision=?",
                            (doc["source_id"],notice["current_revision"])).fetchone() if notice else None
        if not revision or notice["state"]=="conflict":
            decision={"state":"uncertain","outcome":"source_unresolved","detail":{"reason":"missing_or_conflicting_notice"},"obligations":[]}
        elif revision["state"] in ("cancelled","invalid"):
            decision={"state":"unaffected","outcome":"notice_not_active","detail":{"reason":revision["state"]},"obligations":[]}
        elif not (utc(revision["effective_from"])<=moment<utc(revision["effective_until"])):
            decision={"state":"unaffected","outcome":"outside_effective_window","detail":{"reason":"time_window"},"obligations":[]}
        else:
            from .rights import title_state
            has_titles=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_claim'").fetchone()
            if has_titles and db.execute('SELECT 1 FROM title_claim').fetchone():
                facts=doc['facts'];title=title_state(db,facts.get('parcel'),facts.get('owner'))
                if title:
                    doc={**doc,'facts':{**facts,'rights_conflict':title['conflict'],
                                       'owner':title['owner'] or facts.get('owner')}}
            decision=assess_case(doc, json.loads(revision["payload"]))
        if not isinstance(decision.get("obligations"),list):raise ValueError("policy_obligations_required")
        cur=db.execute(f"INSERT INTO {t['assessment']}(case_id,source_revision,state,outcome,detail) VALUES (?,?,?,?,?)",
                       (doc["case_id"],revision["revision"] if revision else None,decision["state"],
                        decision["outcome"],canonical(decision["detail"])))
        assessment_id=cur.lastrowid
        for ob in decision["obligations"]:
            if ob["required"]<1:raise ValueError("invalid_obligation")
            db.execute(f"INSERT INTO {t['obligation']} VALUES (?,?,?,?,?,?,?)",
                       (f"{assessment_id}:{ob['target']}",assessment_id,ob["target"],utc(ob["deadline"]).isoformat(),
                        ob["required"],canonical(ob.get("meta",{})),"pending"))
        result=_describe(db,assessment_id);db.commit()
    except Exception:
        db.rollback();raise
    finally: db.close()
    return result

def _describe(db,assessment_id):
    t=TABLES
    row=db.execute(f"SELECT * FROM {t['assessment']} WHERE id=?",(assessment_id,)).fetchone()
    obs=[dict(x) for x in db.execute(f"SELECT * FROM {t['obligation']} WHERE assessment_id=? ORDER BY target",(assessment_id,))]
    return {"assessment_id":assessment_id,"case":row["case_id"],"state":row["state"],
            "outcome":row["outcome"],"detail":json.loads(row["detail"]),
            "revision":row["source_revision"],"stale":bool(row["stale"]),"obligations":obs}

