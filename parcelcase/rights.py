"""Independent parcel title claims and contested-owner resolution."""
import json
from .store import connect
from .policy import TABLES

SCHEMA="""
CREATE TABLE IF NOT EXISTS title_claim(
 id TEXT PRIMARY KEY, parcel TEXT NOT NULL, owner TEXT NOT NULL,
 share INTEGER NOT NULL CHECK(share>0 AND share<=100), evidence_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('verified','disputed','revoked')));
CREATE TABLE IF NOT EXISTS title_dispute(
 id INTEGER PRIMARY KEY, parcel TEXT NOT NULL, claim_ids TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('open','resolved')), resolution_ref TEXT);
"""

def claim(db_path,claim_id,parcel,owner,share,evidence_hash):
    if not parcel or not owner or not evidence_hash or not 1<=share<=100:
        raise ValueError('invalid_title_claim')
    db=connect(db_path);db.executescript(SCHEMA);db.execute('BEGIN IMMEDIATE')
    try:
        old=db.execute('SELECT * FROM title_claim WHERE id=?',(claim_id,)).fetchone()
        if old:
            if (old['parcel'],old['owner'],old['share'],old['evidence_hash'])!=(parcel,owner,share,evidence_hash):
                raise ValueError('title_identity_conflict')
            state=old['state']
        else:
            db.execute('INSERT INTO title_claim VALUES (?,?,?,?,?,?)',(claim_id,parcel,owner,share,evidence_hash,'verified'))
            claims=db.execute("SELECT * FROM title_claim WHERE parcel=? AND state!='revoked' ORDER BY id",(parcel,)).fetchall()
            conflict=sum(x['share'] for x in claims)>100 or len(claims)>1
            if conflict:
                db.execute("UPDATE title_claim SET state='disputed' WHERE parcel=? AND state!='revoked'",(parcel,))
                ids=json.dumps([x['id'] for x in claims])
                open_dispute=db.execute("SELECT id FROM title_dispute WHERE parcel=? AND state='open'",(parcel,)).fetchone()
                if open_dispute:db.execute('UPDATE title_dispute SET claim_ids=? WHERE id=?',(ids,open_dispute['id']))
                else:db.execute("INSERT INTO title_dispute(parcel,claim_ids,state) VALUES (?,?,'open')",(parcel,ids))
            state='disputed' if conflict else 'verified'
            _stale_parcel(db,parcel)
        db.commit()
    except Exception:
        db.rollback();raise
    finally:db.close()
    return {'claim':claim_id,'state':state,'parcel':parcel}

def resolve(db_path,parcel,chosen_claim,resolution_ref):
    if not resolution_ref:raise ValueError('resolution_evidence_required')
    db=connect(db_path);db.executescript(SCHEMA);db.execute('BEGIN IMMEDIATE')
    try:
        dispute=db.execute("SELECT * FROM title_dispute WHERE parcel=? AND state='open' ORDER BY id DESC LIMIT 1",(parcel,)).fetchone()
        if not dispute:raise ValueError('open_title_dispute_required')
        ids=json.loads(dispute['claim_ids'])
        if chosen_claim not in ids:raise ValueError('chosen_claim_outside_dispute')
        db.execute("UPDATE title_claim SET state='revoked' WHERE parcel=? AND id!=?",(parcel,chosen_claim))
        db.execute("UPDATE title_claim SET state='verified' WHERE id=?",(chosen_claim,))
        db.execute("UPDATE title_dispute SET state='resolved',resolution_ref=? WHERE id=?",(resolution_ref,dispute['id']))
        _stale_parcel(db,parcel);db.commit()
    except Exception:
        db.rollback();raise
    finally:db.close()
    return {'parcel':parcel,'chosen':chosen_claim,'state':'resolved'}

def _stale_parcel(db,parcel):
    t=TABLES
    for row in db.execute(f'SELECT id,facts FROM {t["case"]}'):
        if json.loads(row['facts']).get('parcel')==parcel:
            db.execute(f'UPDATE {t["assessment"]} SET stale=1 WHERE case_id=?',(row['id'],))
            db.execute(f"UPDATE {t['obligation']} SET state='stale' WHERE assessment_id IN "
                       f"(SELECT id FROM {t['assessment']} WHERE case_id=?)",(row['id'],))

def title_state(db,parcel,claimed_owner):
    rows=db.execute("SELECT owner,state FROM title_claim WHERE parcel=? AND state!='revoked'",(parcel,)).fetchall()
    if not rows:return None
    if any(x['state']=='disputed' for x in rows) or len(rows)!=1:
        return {'conflict':True,'owner':None}
    return {'conflict':claimed_owner not in (None,rows[0]['owner']),'owner':rows[0]['owner']}
