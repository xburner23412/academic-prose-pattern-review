#!/usr/bin/env python3
"""Render a lightweight academic-de-ai review JSON as a self-contained HTML."""
from __future__ import annotations
import argparse, html, json, sys
from pathlib import Path

TEXT = {
 "en": {"title":"Academic prose review","scope":"Scope","marks":"Review marks","adjudications":"Contextual adjudications","obs":"Document observations","protected":"Protected passages","coverage":"Reading coverage","limits":"Limits","none":"None","partial":"Partial: the reading rules below were not checked by the fast scan.","experimental":"Experimental rule","source":"Source","priority":"Review priority","trigger":"Trigger","codes":"Feature codes"},
 "zh": {"title":"学术文本复查","scope":"扫描范围","marks":"复查标记","adjudications":"语境裁决","obs":"文档层观察","protected":"受保护内容","coverage":"阅读覆盖","limits":"边界说明","none":"无","partial":"不完整：快速扫描未检查下列全文阅读规则。","experimental":"实验性规则","source":"来源","priority":"复查优先级","trigger":"触发方式","codes":"特征代码"}
}

def esc(value): return html.escape(str(value), quote=True)
def list_html(items): return "<ul>"+"".join(f"<li>{esc(x)}</li>" for x in items)+"</ul>" if items else "<p>—</p>"

def render(data, lang):
    t=TEXT.get(lang,TEXT["en"]); marks=data.get("span_marks",[]); obs=data.get("document_observations",[]); protected=data.get("protected",[]); coverage=data.get("reading_coverage",{})
    cards=[]; adjudication_cards=[]
    for m in marks:
        badge="" if m.get("experimental") else f'<span class="badge">{esc(m["review_priority"])}</span>'
        exp=f'<span class="experimental">{esc(t["experimental"])}</span>' if m.get("experimental") else ""
        status=m.get("review_status","unreviewed")
        rationale=f'<p><b>Rationale:</b> {esc(m.get("rationale"))}</p>' if m.get("rationale") else ""
        card=f'<article class="card"><h3>{esc(", ".join(m.get("codes",[])))} {badge} {exp}</h3><blockquote>{esc(m.get("quote",""))}</blockquote><p><b>Status:</b> {esc(status)}</p><p><b>{esc(t["source"])}:</b> {esc(m.get("source_locator"))}</p><p><b>{esc(t["trigger"])}:</b> {esc(", ".join(m.get("trigger_families",[])))}</p><p><b>Protections:</b> {esc(", ".join(m.get("protections",[])) or "—")}</p>{rationale}</article>'
        if status in {"keep","unreviewed"}: cards.append(card)
        else: adjudication_cards.append(card)
    observations=[]
    for o in obs:
        facts=o.get("facts",{}); fact_lines=[f"{k}: {v}" for k,v in facts.items()]
        exp=f'<span class="experimental">{esc(t["experimental"])}</span>' if o.get("experimental") else ""
        observations.append(f'<article class="card observation"><h3>{esc(o.get("code"))} {exp}</h3>{list_html(fact_lines)}<p>{esc(o.get("interpretation_boundary",""))}</p></article>')
    protected_cards=[f'<article class="card protected"><h3>{esc(", ".join(p.get("protection_codes",[])))}</h3><blockquote>{esc(p.get("quote",""))}</blockquote><p>{esc(p.get("reason",""))}</p><p>{esc(p.get("source_locator",""))}</p></article>' for p in protected]
    source=data.get("source",{}); scope=data.get("scope",{}); extraction=data.get("extraction",{})
    coverage_note=t["partial"] if coverage.get("status")!="complete" else "Complete"
    return f'''<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8"><title>{esc(t["title"])}</title><style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#202124;line-height:1.55}}h1,h2{{letter-spacing:-.02em}}.notice{{background:#fff5cc;border-left:4px solid #d6a300;padding:.8rem 1rem}}.card{{border:1px solid #d8dce3;border-radius:10px;padding:1rem;margin:.8rem 0;background:#fff}}blockquote{{margin:.7rem 0;padding:.5rem .8rem;border-left:3px solid #8190a5;background:#f7f8fa}}.badge{{font-size:.75rem;background:#e7edf8;border-radius:1rem;padding:.18rem .5rem}}.experimental{{font-size:.75rem;color:#8a4b00;background:#fff0dd;border-radius:1rem;padding:.18rem .5rem}}.observation{{border-color:#9aa9c0;background:#f8faff}}.protected{{border-color:#79a884;background:#f5fbf6}}code{{background:#f1f3f5;padding:.1rem .3rem;border-radius:4px}}small{{color:#5f6368}}
</style></head><body><h1>{esc(t["title"])}</h1><p class="notice">{esc(data.get("limitations",[""])[0])}</p><p><b>{esc(t["source"])}:</b> <code>{esc(source.get("path"))}</code><br><small>SHA-256 {esc(source.get("sha256"))}</small></p>
<h2>{esc(t["scope"])}</h2><p>{scope.get("paragraphs_reviewed_by_scan",0)} / {scope.get("paragraphs_total",0)} paragraphs scanned. Excluded: {esc(json.dumps(scope.get("excluded_by_role",{}),ensure_ascii=False))}. Comments excluded: {esc(extraction.get("comments_excluded",0))}.</p>
<h2>{esc(t["coverage"])}</h2><p class="notice">{esc(coverage_note)}</p>{list_html(coverage.get("reading_rule_codes",[]))}
<h2>{esc(t["marks"])}</h2>{''.join(cards) or '<p>—</p>'}
<h2>{esc(t["adjudications"])}</h2>{''.join(adjudication_cards) or '<p>—</p>'}
<h2>{esc(t["obs"])}</h2>{''.join(observations) or '<p>—</p>'}
<h2>{esc(t["protected"])}</h2>{''.join(protected_cards) or '<p>—</p>'}
<h2>{esc(t["limits"])}</h2>{list_html(data.get("limitations",[]))}</body></html>'''

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("review",type=Path); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--lang",choices=("en","zh"),default="en"); args=ap.parse_args()
    try:
        if args.out.exists(): raise ValueError(f"refusing to overwrite existing output: {args.out}")
        data=json.loads(args.review.read_text(encoding="utf-8"))
        if data.get("schema")!="academic-de-ai-review-1.0": raise ValueError("unsupported review schema")
        args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(render(data,args.lang),encoding="utf-8"); print(f"Wrote {args.out}"); return 0
    except (OSError,ValueError,json.JSONDecodeError) as e: print(f"error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
