"""Command line entry points for three business subsystems."""
import argparse,json,tempfile
from pathlib import Path
from .store import connect
from .adoption import adopt
from .assessment import assess
from .settlement import settle
from .report import report

def _source_arg(text):
    source_id,sep,revision=text.rpartition(":")
    if not sep or not source_id.strip():raise ValueError("source_revision_required")
    try:return source_id,int(revision)
    except ValueError:raise ValueError("source_revision_required") from None

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    i=sub.add_parser("init");i.add_argument("--db",required=True)
    for name in ("adopt","assess","settle"):
        cmd=sub.add_parser(name);cmd.add_argument("--db",required=True);cmd.add_argument("--input",required=True)
    mi=sub.add_parser("map-import");mi.add_argument("--db",required=True);mi.add_argument("--input",required=True)
    mr=sub.add_parser("map-review");mr.add_argument("--db",required=True);mr.add_argument("--source",action="append",required=True)
    mp=sub.add_parser("map-plans");mp.add_argument("--db",required=True);mp.add_argument("--review",required=True,type=int)
    mo=sub.add_parser("map-issue");mo.add_argument("--db",required=True);mo.add_argument("--review",required=True,type=int);mo.add_argument("--plan",required=True,type=int)
    r=sub.add_parser("report");r.add_argument("--db",required=True);r.add_argument("--out")
    d=sub.add_parser("demo");d.add_argument("--workdir")
    tc=sub.add_parser("title-claim");tc.add_argument("--db",required=True);tc.add_argument("--id",required=True);tc.add_argument("--parcel",required=True);tc.add_argument("--owner",required=True);tc.add_argument("--share",required=True,type=int);tc.add_argument("--evidence",required=True)
    tr=sub.add_parser("title-resolve");tr.add_argument("--db",required=True);tr.add_argument("--parcel",required=True);tr.add_argument("--chosen",required=True);tr.add_argument("--resolution",required=True)
    a=p.parse_args()
    if a.command=="init":
        db=connect(a.db);db.close();print(a.db)
    elif a.command=="adopt":print(json.dumps(adopt(a.db,a.input),ensure_ascii=False))
    elif a.command=="assess":print(json.dumps(assess(a.db,a.input),ensure_ascii=False))
    elif a.command=="settle":print(json.dumps(settle(a.db,a.input),ensure_ascii=False))
    elif a.command=="map-import":
        from .map_source import import_map
        print(json.dumps(import_map(a.db,a.input),ensure_ascii=False))
    elif a.command=="map-review":
        from .map_review import review
        print(json.dumps(review(a.db,[_source_arg(x) for x in a.source]),ensure_ascii=False))
    elif a.command=="map-plans":
        from .map_review import plans
        print(json.dumps(plans(a.db,a.review),ensure_ascii=False))
    elif a.command=="map-issue":
        from .map_review import issue
        print(json.dumps(issue(a.db,a.review,a.plan),ensure_ascii=False))
    elif a.command=="report":print(json.dumps(report(a.db,a.out),ensure_ascii=False))
    elif a.command=="title-claim":
        from .rights import claim
        print(claim(a.db,a.id,a.parcel,a.owner,a.share,a.evidence))
    elif a.command=="title-resolve":
        from .rights import resolve
        print(resolve(a.db,a.parcel,a.chosen,a.resolution))
    else:
        work=Path(a.workdir or tempfile.mkdtemp(prefix="source-case-"));work.mkdir(parents=True,exist_ok=True)
        fixture=Path(__file__).resolve().parent.parent/"fixtures"
        db=work/"state.db"
        config=__import__(__package__+".policy",fromlist=["DEMO"]).DEMO
        print(adopt(db,fixture/config["adopt"]))
        print(assess(db,fixture/config["assess"]))
        print(settle(db,fixture/config["settle"]))
        print(work/"report.json")
        report(db,work/"report.json")
if __name__=="__main__":main()

