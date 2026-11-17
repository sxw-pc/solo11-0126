import json
from pathlib import Path
from parcelcase.adoption import adopt
from parcelcase.assessment import assess
from parcelcase.settlement import settle
from parcelcase.report import report
from parcelcase.rights import claim,resolve

FIX=Path(__file__).resolve().parent.parent/'fixtures'

def changed(tmp_path,name,mutate):
    doc=json.loads((FIX/name).read_text(encoding='utf-8'));mutate(doc)
    path=tmp_path/(str(len(list(tmp_path.glob('*.json'))))+'.json')
    path.write_text(json.dumps(doc),encoding='utf-8');return path

def test_boundary_and_land_use_are_distinct_impact_reasons(tmp_path):
    db=tmp_path/'state.db';adopt(db,FIX/'plan_normal.json')
    no_change=changed(tmp_path,'parcel_normal.json',lambda d:(d.update(case_id='none'),d['facts'].update(boundary_overlap=False,new_use='housing')))
    assert assess(db,no_change)['outcome']=='no_material_change'
    use_only=changed(tmp_path,'parcel_normal.json',lambda d:(d.update(case_id='use'),d['facts'].update(boundary_overlap=False)))
    assert assess(db,use_only)['detail']['land_use_changed'] is True

def test_competing_title_claims_suspend_then_restore_objection_eligibility(tmp_path):
    normal=json.loads((FIX/'title_normal.json').read_text(encoding='utf-8'))
    conflict=json.loads((FIX/'title_conflict.json').read_text(encoding='utf-8'))
    args={k:v for k,v in conflict.items() if k!='resolution_ref'}
    db=tmp_path/'state.db';adopt(db,FIX/'plan_normal.json')
    assert claim(db,**normal)['state']=='verified'
    assert assess(db,FIX/'parcel_normal.json')['state']=='eligible'
    assert claim(db,**args)['state']=='disputed'
    assert report(db)['cases'][0]['stale'] is True
    assert assess(db,FIX/'parcel_normal.json')['outcome']=='rights_conflict'
    assert resolve(db,'P-1','TITLE-O1',conflict['resolution_ref'])['state']=='resolved'
    assert assess(db,FIX/'parcel_normal.json')['state']=='eligible'

def test_verified_postmark_changes_late_intake_result(tmp_path):
    db=tmp_path/'state.db';adopt(db,FIX/'plan_normal.json');assess(db,FIX/'parcel_normal.json')
    assert settle(db,FIX/'objection_late.json')['status']=='overdue'
    assert settle(db,FIX/'objection_postmark.json')['status']=='complete'
    receipt=report(db)['cases'][0]['obligations'][0]['receipts']
    assert any(x['reason']=='verified_postmark_before_intake' for x in receipt)

def test_wrong_version_or_unaffected_parcel_cannot_be_received(tmp_path):
    db=tmp_path/'state.db';adopt(db,FIX/'plan_normal.json')
    outside=changed(tmp_path,'parcel_normal.json',lambda d:(d.update(case_id='outside'),d['facts'].update(parcel='P-2')))
    assert assess(db,outside)['outcome']=='parcel_outside_display'
    assess(db,FIX/'parcel_normal.json')
    wrong=changed(tmp_path,'objection_normal.json',lambda d:d['receipts'][0].update(version=0))
    assert settle(db,wrong)['status']=='pending'

def test_corrected_display_reopens_window_and_out_of_order_notice_does_not_replace_it(tmp_path):
    db=tmp_path/'state.db';adopt(db,FIX/'plan_normal.json');assess(db,FIX/'parcel_normal.json')
    corrected=changed(tmp_path,'plan_normal.json',lambda d:(d.update(revision=3),d['payload'].update(round='R2',objection_until='2026-06-05T00:00:00Z')))
    assert adopt(db,corrected)['state']=='active'
    assert report(db)['cases'][0]['stale'] is True
    new=assess(db,FIX/'parcel_normal.json')
    assert new['obligations'][0]['deadline'].startswith('2026-06-05T00:00:00')
    old=changed(tmp_path,'plan_normal.json',lambda d:d.update(revision=2))
    assert adopt(db,old)['state']=='historical'
    assert assess(db,FIX/'parcel_normal.json')['revision']==3
