"""Public display rounds, parcel impacts and objection-intake rules."""
TABLES={"notice":"plan_notice","revision":"display_round","case":"parcel_revision",
"assessment":"impact_case","obligation":"objection","receipt":"intake_receipt"}
DEMO={"adopt":"plan_normal.json","assess":"parcel_normal.json","settle":"objection_normal.json"}
EXTRA_TABLES=["title_claim","title_dispute"]
def validate_notice(doc):
    p=doc["payload"]
    if p.get("authority")!="planning_office":return "invalid","untrusted_planning_office"
    if p.get("action")=="withdraw":return "cancelled","display_withdrawn"
    if p.get("action")!="display" or not p.get("round") or not p.get("objection_until"):
        return "invalid","invalid_display_round"
    return "active","accepted_display_round"
def assess_case(doc,p):
    f=doc["facts"];parcel=f.get("parcel")
    if f.get("rights_conflict"):return {"state":"uncertain","outcome":"rights_conflict",
      "detail":{"parcel":parcel},"obligations":[]}
    if parcel not in p.get("parcels",[]):return {"state":"unaffected","outcome":"parcel_outside_display",
      "detail":{"parcel":parcel},"obligations":[]}
    if not f.get("boundary_overlap") and f.get("old_use")==f.get("new_use"):
        return {"state":"unaffected","outcome":"no_material_change","detail":{"parcel":parcel},"obligations":[]}
    if not f.get("owner"):return {"state":"uncertain","outcome":"owner_unknown","detail":{"parcel":parcel},"obligations":[]}
    ob={"target":f["owner"],"deadline":p["objection_until"],"required":1,
        "meta":{"parcel":parcel,"round":p["round"]}}
    return {"state":"eligible","outcome":"objection_window_open",
      "detail":{"parcel":parcel,"boundary_overlap":bool(f.get("boundary_overlap")),
                "land_use_changed":f.get("old_use")!=f.get("new_use")},"obligations":[ob]}
def receipt_verdict(r,ob,version):
    import json
    meta=json.loads(ob["meta"])
    if r["version"]!=version:return "invalid","old_display_version"
    if r.get("parcel")!=meta["parcel"] or r.get("round")!=meta["round"]:
        return "invalid","wrong_parcel_or_round"
    if not r.get("signed_digest"):return "invalid","unsigned_objection"
    if r["amount"]!=1:return "invalid","intake_count_invalid"
    return "valid","objection_received"

