#!/usr/bin/env python3
"""Validate a lightweight review against its unchanged source and rule table."""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("academic_de_ai_marker",HERE/"mark_patterns.py"); marker=importlib.util.module_from_spec(spec); spec.loader.exec_module(marker)

def validate(data, source, rules, revision_view=None, accept_pdf_warning=False):
    errors=[]
    try: rule_data=marker.load_rules(rules)
    except Exception as e: return [f"rule table load failed: {e}"]
    all_codes={r["code"] for r in rule_data["detection_rules"] if r.get("enabled")}
    reading_codes={r["code"] for r in rule_data["detection_rules"] if r.get("enabled") and r["kind"]=="reading"}
    automatic_codes={r["code"] for r in rule_data["detection_rules"] if r.get("enabled") and r["kind"] not in {"reading","doc_stat"}}
    if data.get("schema")!="academic-de-ai-review-1.0": errors.append("unsupported schema")
    if data.get("source",{}).get("sha256")!=marker.digest(source): errors.append("source hash is stale")
    if data.get("rules",{}).get("sha256")!=marker.digest(rules): errors.append("rule table hash is stale")
    try: paragraphs,_=marker.load_source(source,revision_view,accept_pdf_warning)
    except Exception as e: return [f"source reload failed: {e}"]
    by_id={p["paragraph_id"]:p for p in paragraphs}; ids=set(); available_sections={p["section"] or "(unheaded prose)" for p in paragraphs if p["content_role"]=="prose"}
    for mark in data.get("span_marks",[]):
        mid=mark.get("mark_id")
        if not mid or mid in ids: errors.append(f"duplicate/missing mark_id: {mid}")
        ids.add(mid); p=by_id.get(mark.get("paragraph_id"))
        if not p: errors.append(f"{mid}: paragraph not found"); continue
        start,end=mark.get("start"),mark.get("end")
        if not isinstance(start,int) or not isinstance(end,int) or not (0<=start<end<=len(p["text"])): errors.append(f"{mid}: invalid offsets"); continue
        if " ".join(p["text"][start:end].split())!=mark.get("quote"): errors.append(f"{mid}: quote does not resolve")
        origin=mark.get("origin"); codes=mark.get("codes")
        if origin not in {"automatic_scan","model_reading"}: errors.append(f"{mid}: invalid origin")
        if not isinstance(codes,list) or not codes or not set(codes)<=all_codes or mark.get("review_priority") not in {"high","low"}: errors.append(f"{mid}: invalid codes or priority")
        elif origin=="automatic_scan" and not set(codes)<=automatic_codes: errors.append(f"{mid}: automatic mark uses a non-automatic rule")
        elif origin=="model_reading" and not set(codes)&reading_codes: errors.append(f"{mid}: model_reading mark lacks a reading-rule code")
        if mark.get("review_status") not in {"unreviewed","keep","protected_or_functional","rule_misfire"}: errors.append(f"{mid}: invalid review_status")
        if mark.get("review_status") != "unreviewed" and not mark.get("rationale"): errors.append(f"{mid}: adjudicated mark lacks rationale")
    coverage=data.get("reading_coverage",{})
    if coverage.get("status") not in {"partial","complete"}: errors.append("invalid reading coverage status")
    if set(coverage.get("reading_rule_codes",[]))!=reading_codes: errors.append("reading_rule_codes do not match the current rule table")
    reviewed=coverage.get("reviewed_sections",[]); unreviewed=coverage.get("unreviewed_sections",[])
    if not isinstance(reviewed,list) or not isinstance(unreviewed,list): errors.append("reviewed_sections and unreviewed_sections must be lists")
    else:
        reviewed_set,unreviewed_set=set(reviewed),set(unreviewed)
        if reviewed_set & unreviewed_set: errors.append("reviewed and unreviewed sections overlap")
        if reviewed_set | unreviewed_set != available_sections: errors.append("reading coverage does not partition the source prose sections")
    if coverage.get("status")=="complete" and coverage.get("unreviewed_sections"): errors.append("complete coverage has unreviewed sections")
    if coverage.get("status")=="complete" and any(x.get("review_status")=="unreviewed" for x in data.get("span_marks",[])): errors.append("complete coverage contains unreviewed marks")
    forbidden=("ai_score","probability","per_1000","mark_density","confidence")
    lowered=json.dumps(data,ensure_ascii=False).lower()
    for key in forbidden:
        if f'"{key}"' in lowered: errors.append(f"forbidden metric field: {key}")
    for observation in data.get("document_observations",[]):
        if observation.get("code")!="STR-04" or observation.get("origin")!="document_stat": errors.append("invalid document observation")
        if "not an ai indicator" not in observation.get("interpretation_boundary","").lower(): errors.append("STR-04 interpretation boundary missing")
    return errors

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("review",type=Path); ap.add_argument("--source",type=Path,required=True); ap.add_argument("--rules",type=Path,default=HERE.parent/"rules.json"); ap.add_argument("--revision-view",choices=("accepted","original")); ap.add_argument("--accept-pdf-warning",action="store_true"); args=ap.parse_args()
    try: data=json.loads(args.review.read_text(encoding="utf-8")); errors=validate(data,args.source,args.rules,args.revision_view,args.accept_pdf_warning)
    except (OSError,json.JSONDecodeError) as e: print(f"error: {e}",file=sys.stderr); return 2
    if errors:
        for e in errors: print("error: "+e,file=sys.stderr)
        return 1
    print("Review validation passed"); return 0
if __name__=="__main__": raise SystemExit(main())
