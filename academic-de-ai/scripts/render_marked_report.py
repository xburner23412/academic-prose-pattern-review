#!/usr/bin/env python3
"""Render a lightweight academic-de-ai review JSON as a self-contained HTML."""
from __future__ import annotations
import argparse, hashlib, html, importlib.util, json, re, sys
from pathlib import Path

TEXT = {
 "en": {"title":"Academic prose review","scope":"Scope","marks":"Review marks","adjudications":"Contextual adjudications","obs":"Document observations","protected":"Protected passages","coverage":"Reading coverage","limits":"Limits","none":"None","partial":"Partial: the reading rules below were not checked by the fast scan.","experimental":"Experimental rule","source":"Source","priority":"Review priority","trigger":"Trigger","codes":"Feature codes","manuscript":"Manuscript with marks in place","stale":"Source not supplied: marks are listed as quotations only."},
 "zh": {"title":"学术文本复查","scope":"扫描范围","marks":"复查标记","adjudications":"语境裁决","obs":"文档层观察","protected":"受保护内容","coverage":"阅读覆盖","limits":"边界说明","none":"无","partial":"不完整：快速扫描未检查下列全文阅读规则。","experimental":"实验性规则","source":"来源","priority":"复查优先级","trigger":"触发方式","codes":"特征代码","manuscript":"原文与标注","stale":"未提供原文：标记仅以引文形式列出。"}
}

def esc(value): return html.escape(str(value), quote=True)
def list_html(items): return "<ul>"+"".join(f"<li>{esc(x)}</li>" for x in items)+"</ul>" if items else "<p>—</p>"

HEADING_MARKER = re.compile(r"^#+\s+")

def load_scanner():
    """Reuse the scanner's own reader.

    Mark offsets were produced by its paragraph splitting. A second
    implementation here would drift and put every highlight in the wrong place.
    """
    spec=importlib.util.spec_from_file_location("mark_patterns",Path(__file__).resolve().parent/"mark_patterns.py")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return h.hexdigest()

def manuscript_paragraphs(data,source,view,accept):
    """Paragraphs from the source, refusing a source that has moved on."""
    recorded=(data.get("source") or {}).get("sha256")
    actual=digest(source)
    if recorded and recorded!=actual:
        raise ValueError("source no longer matches the review: recorded %s, found %s. "
                         "Rescan before rendering inline." % (recorded[:12],actual[:12]))
    paragraphs,_=load_scanner().load_source(source,view,accept)
    return {p["paragraph_id"]:p for p in paragraphs},[p for p in paragraphs]

def weave(text,spans):
    """Highlight spans in one paragraph.

    Two marks can overlap and only one highlight can be drawn, so the longer
    span wins and records what it absorbed. Every drawn mark keeps its anchor,
    so no card is left pointing at unmarked text.
    """
    chosen=[]
    for s in sorted(spans,key=lambda x:(x["start"],-(x["end"]-x["start"]))):
        cover=next((c for c in chosen if s["start"]<c["end"] and c["start"]<s["end"]),None)
        if cover is not None: cover.setdefault("absorbs",[]).append(s["mark_id"]); s["absorbed_by"]=cover["mark_id"]; continue
        chosen.append(s)
    out=[]; cursor=0
    for s in chosen:
        start=max(cursor,min(s["start"],len(text))); end=max(start,min(s["end"],len(text)))
        out.append(esc(text[cursor:start]))
        cls=s.get("review_status") or "unreviewed"
        out.append(f'<mark class="m-{esc(cls)}" id="t-{esc(s["mark_id"])}">{esc(text[start:end])}'
                   f'<a href="#{esc(s["mark_id"])}">{esc(s["mark_id"])}</a></mark>')
        cursor=end
    out.append(esc(text[cursor:]))
    return "".join(out)

def manuscript_html(data,paragraphs,t):
    by_para={}
    for m in data.get("span_marks",[]): by_para.setdefault(m.get("paragraph_id"),[]).append(dict(m))
    rows=[]
    for p in paragraphs:
        if p["content_role"]=="heading":
            heading=HEADING_MARKER.sub("",p["text"])
            rows.append(f'<h3 class="ms-h">{esc(heading)}</h3>'); continue
        if p["content_role"]!="prose":
            rows.append(f'<p class="ms-out"><span class="pid">{esc(p["paragraph_id"])}</span>'
                        f'<span class="role">{esc(p["content_role"])}</span> {esc(p["text"][:120])}…</p>'); continue
        rows.append(f'<p class="ms-p"><span class="pid">{esc(p["paragraph_id"])}</span>'
                    f'{weave(p["text"],by_para.get(p["paragraph_id"],[]))}</p>')
    return f'<h2>{esc(t["manuscript"])}</h2><div class="ms">{"".join(rows)}</div>'

def render(data, lang, paragraphs=None):
    t=TEXT.get(lang,TEXT["en"]); marks=data.get("span_marks",[]); obs=data.get("document_observations",[]); protected=data.get("protected",[]); coverage=data.get("reading_coverage",{})
    cards=[]; adjudication_cards=[]
    for m in marks:
        badge="" if m.get("experimental") else f'<span class="badge">{esc(m["review_priority"])}</span>'
        exp=f'<span class="experimental">{esc(t["experimental"])}</span>' if m.get("experimental") else ""
        status=m.get("review_status","unreviewed")
        rationale=f'<p><b>Rationale:</b> {esc(m.get("rationale"))}</p>' if m.get("rationale") else ""
        back=f' <a class="back" href="#t-{esc(m["mark_id"])}">&#8593;</a>' if paragraphs else ""
        card=f'<article class="card" id="{esc(m["mark_id"])}"><h3>{esc(", ".join(m.get("codes",[])))} {badge} {exp}<span class="mid">{esc(m["mark_id"])}</span>{back}</h3><blockquote>{esc(m.get("quote",""))}</blockquote><p><b>Status:</b> {esc(status)}</p><p><b>{esc(t["source"])}:</b> {esc(m.get("source_locator"))}</p><p><b>{esc(t["trigger"])}:</b> {esc(", ".join(m.get("trigger_families",[])))}</p><p><b>Protections:</b> {esc(", ".join(m.get("protections",[])) or "—")}</p>{rationale}</article>'
        if status in {"keep","unreviewed"}: cards.append(card)
        else: adjudication_cards.append(card)
    observations=[]
    for o in obs:
        facts=o.get("facts",{}); fact_lines=[f"{k}: {v}" for k,v in facts.items()]
        exp=f'<span class="experimental">{esc(t["experimental"])}</span>' if o.get("experimental") else ""
        observations.append(f'<article class="card observation"><h3>{esc(o.get("code"))} {exp}</h3>{list_html(fact_lines)}<p>{esc(o.get("interpretation_boundary",""))}</p></article>')
    protected_cards=[f'<article class="card protected"><h3>{esc(", ".join(p.get("protection_codes",[])))}</h3><blockquote>{esc(p.get("quote",""))}</blockquote><p>{esc(p.get("reason",""))}</p><p>{esc(p.get("source_locator",""))}</p></article>' for p in protected]
    source=data.get("source",{}); scope=data.get("scope",{}); extraction=data.get("extraction",{})
    manuscript=manuscript_html(data,paragraphs,t) if paragraphs else f'<h2>{esc(t["manuscript"])}</h2><p class="notice">{esc(t["stale"])}</p>'
    coverage_note=t["partial"] if coverage.get("status")!="complete" else "Complete"
    return f'''<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8"><title>{esc(t["title"])}</title><style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#202124;line-height:1.55}}h1,h2{{letter-spacing:-.02em}}.notice{{background:#fff5cc;border-left:4px solid #d6a300;padding:.8rem 1rem}}.card{{border:1px solid #d8dce3;border-radius:10px;padding:1rem;margin:.8rem 0;background:#fff}}blockquote{{margin:.7rem 0;padding:.5rem .8rem;border-left:3px solid #8190a5;background:#f7f8fa}}.badge{{font-size:.75rem;background:#e7edf8;border-radius:1rem;padding:.18rem .5rem}}.experimental{{font-size:.75rem;color:#8a4b00;background:#fff0dd;border-radius:1rem;padding:.18rem .5rem}}.observation{{border-color:#9aa9c0;background:#f8faff}}.ms{{border:1px solid #d8dce3;border-radius:10px;padding:1rem 1.2rem;background:#fff;max-height:none}}.ms-p{{margin:0 0 .9rem;line-height:1.65}}.ms-h{{margin:1.4rem 0 .6rem;font-size:1rem;color:#3c4450}}.ms-out{{margin:0 0 .6rem;color:#8b93a1;font-size:.85rem}}.pid{{font:600 .7rem/1 ui-monospace,monospace;color:#98a1b0;margin-right:.5rem;vertical-align:super}}.role{{font-size:.7rem;background:#eef1f5;border-radius:.6rem;padding:.05rem .4rem;margin-right:.4rem}}mark{{background:#fff2c9;padding:.05rem 0;border-bottom:2px solid #d6a300}}mark.m-keep{{background:#ffe0dc;border-bottom-color:#c0392b}}mark.m-protected_or_functional{{background:#e2f3e6;border-bottom-color:#2f7a45}}mark.m-rule_misfire{{background:#eef1f5;border-bottom-color:#98a1b0}}mark a{{font:600 .65rem/1 ui-monospace,monospace;text-decoration:none;color:#5f6368;margin-left:.15rem;vertical-align:super}}.mid{{font:600 .7rem/1 ui-monospace,monospace;color:#98a1b0;margin-left:auto}}.back{{text-decoration:none;color:#5f6368;margin-left:.4rem}}.card h3{{display:flex;align-items:baseline;gap:.4rem}}:target{{outline:2px solid #d6a300;outline-offset:2px}}.protected{{border-color:#79a884;background:#f5fbf6}}code{{background:#f1f3f5;padding:.1rem .3rem;border-radius:4px}}small{{color:#5f6368}}
</style></head><body><h1>{esc(t["title"])}</h1><p class="notice">{esc(data.get("limitations",[""])[0])}</p><p><b>{esc(t["source"])}:</b> <code>{esc(source.get("path"))}</code><br><small>SHA-256 {esc(source.get("sha256"))}</small></p>
<h2>{esc(t["scope"])}</h2><p>{scope.get("paragraphs_reviewed_by_scan",0)} / {scope.get("paragraphs_total",0)} paragraphs scanned. Excluded: {esc(json.dumps(scope.get("excluded_by_role",{}),ensure_ascii=False))}. Comments excluded: {esc(extraction.get("comments_excluded",0))}.</p>
<h2>{esc(t["coverage"])}</h2><p class="notice">{esc(coverage_note)}</p>{list_html(coverage.get("reading_rule_codes",[]))}
{manuscript}<h2>{esc(t["marks"])}</h2>{''.join(cards) or '<p>—</p>'}
<h2>{esc(t["adjudications"])}</h2>{''.join(adjudication_cards) or '<p>—</p>'}
<h2>{esc(t["obs"])}</h2>{''.join(observations) or '<p>—</p>'}
<h2>{esc(t["protected"])}</h2>{''.join(protected_cards) or '<p>—</p>'}
<h2>{esc(t["limits"])}</h2>{list_html(data.get("limitations",[]))}</body></html>'''

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("review",type=Path); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--lang",choices=("en","zh"),default="en")
    ap.add_argument("--source",type=Path,help="Lay the manuscript out with marks in place. The file must still hash to the value recorded in the review.")
    ap.add_argument("--revision-view",choices=("accepted","original"))
    ap.add_argument("--accept-pdf-warning",action="store_true")
    args=ap.parse_args()
    try:
        if args.out.exists(): raise ValueError(f"refusing to overwrite existing output: {args.out}")
        data=json.loads(args.review.read_text(encoding="utf-8"))
        if data.get("schema")!="academic-de-ai-review-1.0": raise ValueError("unsupported review schema")
        paragraphs=None
        if args.source:
            _,paragraphs=manuscript_paragraphs(data,args.source,args.revision_view,args.accept_pdf_warning)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(render(data,args.lang,paragraphs),encoding="utf-8")
        print(f"Wrote {args.out}" + (" with the manuscript inline" if paragraphs else "")); return 0
    except (OSError,ValueError,json.JSONDecodeError) as e: print(f"error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
