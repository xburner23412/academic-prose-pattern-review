#!/usr/bin/env python3
"""Mark academic-prose features for review; never judge AI authorship or edit."""
from __future__ import annotations

import argparse, hashlib, json, re, statistics, sys, unicodedata, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "rules.json"
KINDS = {"regex", "slots", "pair", "frame", "reading", "doc_stat"}
PRIORITY = {"high": 0, "low": 1}
WORD_RE = re.compile(r"\b[A-Za-z]+(?:['’][A-Za-z]+)?\b")
ABBREVIATIONS = ("et al.", "e.g.", "i.e.", "cf.", "fig.", "figs.", "p.", "pp.", "vs.", "dr.", "prof.", "no.", "vol.")
PROTECTED_SECTIONS = {"references", "reference list", "bibliography", "acknowledgements", "acknowledgments", "publisher's note", "publisher’s note"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def stdout_utf8():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return h.hexdigest()

def fold(s):
    return unicodedata.normalize("NFKC", s).replace("’", "'").replace("–", "-").replace("—", "-")

def words(s): return WORD_RE.findall(s)

def validate_rules(data):
    rules, lists = data.get("detection_rules", []), data.get("word_lists", {})
    codes = [r.get("code") for r in rules]
    # The count lives in the data, not here: adding a rule must stay a JSON
    # edit. Declaring it still catches a truncated or half-merged file.
    declared = data.get("rule_count")
    if data.get("schema") != "1.0" or not rules or len(codes) != len(set(codes)):
        raise ValueError("rules.json must use schema 1.0 and carry unique, non-empty rules")
    if declared is not None and declared != len(rules):
        raise ValueError(f"rules.json declares {declared} rules but contains {len(rules)}")
    for r in rules:
        if r.get("kind") not in KINDS or r.get("review_priority") not in PRIORITY: raise ValueError(f"{r.get('code')}: invalid kind or priority")
        v = r.get("verification", {})
        if v.get("status") not in {"verified", "regression_only", "unverified"} or v.get("rule_revision") != r.get("rule_revision"):
            raise ValueError(f"{r.get('code')}: stale or invalid verification")
        for p in r.get("patterns", []):
            re.compile(p["regex"], re.I | re.S)
            if "exclude" in p: re.compile(p["exclude"], re.I | re.S)
        for key in ("list_a", "list_b"):
            if key in r and r[key] not in lists: raise ValueError(f"{r['code']}: missing list {r[key]}")
        if r.get("cluster",{}).get("scope") not in {None,"sentence","paragraph"}: raise ValueError(f"{r['code']}: invalid cluster scope")
        if r.get("kind")=="doc_stat":
            band=r.get("band_words")
            if not isinstance(band,list) or len(band)!=2 or not all(isinstance(x,int) for x in band) or band[0]>=band[1]: raise ValueError(f"{r['code']}: invalid band_words")
    for p in data.get("protections", []):
        for pattern in p.get("patterns", []): re.compile(pattern, re.I | re.S)

def load_rules(path):
    data = json.loads(path.read_text(encoding="utf-8")); validate_rules(data); return data

def role_for_heading(heading):
    h = fold(heading).lower().strip().rstrip(":")
    if h in PROTECTED_SECTIONS or h.startswith("references"): return "reference"
    if re.search(r"\b(?:declaration|statement)\b.*\b(?:ai|artificial intelligence|generative ai)\b", h): return "protected_section"
    if re.search(r"appendix.*method|method.*appendix", h): return "protected_section"
    return "prose"

def record(path, n, text, section, role, **extra):
    out = {"paragraph_id": f"p{n:04d}", "source_locator": f"{path.name}:paragraph[{n}]", "section": section, "content_role": role, "text": text}
    out.update(extra); return out

def load_markdown(path):
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    out, section, role = [], "", "prose"
    for block in map(str.strip, blocks):
        if not block: continue
        m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", block)
        if m:
            section = re.sub(r"[*_`]", "", m.group(1)).strip(); role = role_for_heading(section)
            out.append(record(path, len(out)+1, block, section, "heading"))
        else: out.append(record(path, len(out)+1, block, section, role))
    return out, {"format":"markdown", "comments_excluded":0, "tracked_changes":False}

def docx_text(node, view):
    chunks=[]
    def walk(x, deleted=False, inserted=False):
        local=x.tag.rsplit("}",1)[-1]; deleted=deleted or local in {"del","moveFrom"}; inserted=inserted or local in {"ins","moveTo"}
        include=not (view=="accepted" and deleted) and not (view=="original" and inserted)
        if local in {"t","delText"} and include and x.text: chunks.append(x.text)
        elif local=="tab" and include: chunks.append("\t")
        elif local in {"br","cr"} and include: chunks.append("\n")
        for child in x: walk(child, deleted, inserted)
    walk(node); return "".join(chunks).strip()

def load_docx(path, view):
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist()); root=ET.fromstring(z.read("word/document.xml"))
        changed=any(root.find(f".//{W}{tag}") is not None for tag in ("ins","del","moveFrom","moveTo"))
        if changed and not view: raise ValueError("DOCX contains tracked changes/moves; use --revision-view accepted|original")
        view=view or "accepted"; comments=0
        if "word/comments.xml" in names: comments=len(list(ET.fromstring(z.read("word/comments.xml")).iter(f"{W}comment")))
        out=[]; section=""; role="prose"
        for p in root.iter(f"{W}p"):
            text=docx_text(p,view)
            if not text: continue
            style=""; ppr=p.find(f"{W}pPr")
            if ppr is not None:
                ps=ppr.find(f"{W}pStyle")
                if ps is not None: style=ps.attrib.get(f"{W}val","")
            heading=style.lower().startswith("heading") or style.lower() in {"title","subtitle"}
            if heading: section=text; role=role_for_heading(text)
            out.append(record(path,len(out)+1,text,section,"heading" if heading else role,docx_style=style))
        non_body=[name for name in names if re.match(r"word/(?:header|footer)\d*\.xml$|word/(?:footnotes|endnotes)\.xml$",name)]
        text_boxes=len(list(root.iter(f"{W}txbxContent")))
    return out,{"format":"docx","comments_excluded":comments,"tracked_changes":changed,"revision_view":view,"non_body_parts_not_scanned":sorted(non_body),"text_boxes_detected":text_boxes,"custom_heading_styles_resolved":False}

def pdf_damage(pages):
    text="\n".join(pages); total=max(1,len(words(text))); lines=[x.strip() for x in text.splitlines() if x.strip()]
    metrics={"glued_word_ratio":round(len(re.findall(r"\b[A-Za-z]{18,}\b",text))/total,4),"replacement_character_ratio":round(text.count("�")/max(1,len(text)),4),"very_short_line_share":round(sum(len(words(x))<=2 for x in lines)/max(1,len(lines)),4)}
    signals=[]
    if metrics["glued_word_ratio"]>=.01: signals.append("glued_word_ratio")
    if metrics["replacement_character_ratio"]>=.001: signals.append("replacement_character_ratio")
    if metrics["very_short_line_share"]>=.40: signals.append("fragmented_line_ratio")
    return signals,metrics

def load_pdf(path, accept):
    try: from pypdf import PdfReader
    except ImportError as e: raise ValueError("PDF support requires pypdf") from e
    pages=[p.extract_text() or "" for p in PdfReader(str(path)).pages]; signals,metrics=pdf_damage(pages)
    if len(signals)>=2: raise ValueError("PDF extraction refused: multiple damage signals: "+", ".join(signals))
    if len(signals)==1 and not accept: raise ValueError("PDF extraction needs confirmation or alternate format; inspect then use --accept-pdf-warning")
    out=[]; section=""; role="prose"
    for page_no,page in enumerate(pages,1):
        for block in re.split(r"\n\s*\n|(?<=\.)\n(?=[A-Z])",page):
            block=re.sub(r"(?<=\w)-\n(?=\w)","",block); block=re.sub(r"\s*\n\s*"," ",block).strip()
            if not block: continue
            heading=len(words(block))<=12 and not re.search(r"[.!?]$",block)
            if heading: section=block; role=role_for_heading(block)
            out.append(record(path,len(out)+1,block,section,"heading" if heading else role,page=page_no))
    return out,{"format":"pdf","comments_excluded":0,"tracked_changes":False,"damage_signals":signals,"damage_metrics":metrics,"warning_accepted":bool(signals and accept),"heading_heuristic":"Blocks of 12 or fewer words without terminal punctuation are treated as headings."}

def load_source(path, view, accept):
    if path.suffix.lower() in {".md",".txt"}: return load_markdown(path)
    if path.suffix.lower()==".docx": return load_docx(path,view)
    if path.suffix.lower()==".pdf": return load_pdf(path,accept)
    raise ValueError("supported inputs: .md, .txt, .docx, .pdf")

def sentences(text):
    protected=text
    # Replace only the internal full stops so offsets remain identical to the
    # source.  Variable-length placeholders previously corrupted locators and
    # also hid a real boundary when the next sentence began with "Fig.".
    for a in ABBREVIATIONS:
        protected=re.sub(re.escape(a),lambda m:m.group(0).replace(".","§"),protected,flags=re.I)
    protected=re.sub(r"\b([A-Z])\.(?=\s*[A-Z]\.)",lambda m:m.group(1)+"§",protected); protected=re.sub(r"(?<=\d)\.(?=\d)","§",protected)
    cuts=[0]+[m.end() for m in re.finditer(r"[.!?](?:[\"'’”)]*)\s+(?=[A-Z0-9])",protected)]+[len(text)]
    out=[]
    for start,end in zip(cuts,cuts[1:]):
        while start<end and text[start].isspace(): start+=1
        while end>start and text[end-1].isspace(): end-=1
        if start<end: out.append((start,end,text[start:end]))
    return out

def protection_hits(text, protections):
    hits=[]
    for p in protections:
        if p.get("kind")=="section": continue
        for pattern in p.get("patterns",[]):
            for m in re.finditer(pattern,text,re.I|re.S): hits.append({"code":p["code"],"start":m.start(),"end":m.end(),"quote":m.group(0)})
    return hits

def cluster_matches(rule,text,lists):
    cluster=rule.get("cluster")
    if not cluster: return []
    watched=set(map(str.lower,lists[cluster["word_list"]])); present={x.lower() for x in words(text) if x.lower() in watched}
    return [(0,len(text),cluster["family"])] if len(present)>=cluster["min_distinct"] else []

def pattern_matches(pattern,text):
    """Matches for one pattern, minus any its `exclude` disqualifies.

    Python's re has no variable-width lookbehind, so a rule cannot say "not when
    a separation verb governs this from". `exclude` is tested against a window
    ending at the match, which reaches the governing verb without one lookbehind
    per verb form.
    """
    exclude=pattern.get("exclude"); window=int(pattern.get("exclude_window",60)); out=[]
    for m in re.finditer(pattern["regex"],text,re.I|re.S):
        if exclude and re.search(exclude,text[max(0,m.start()-window):m.end()],re.I|re.S): continue
        out.append((m.start(),m.end(),pattern["family"]))
    return out

def rule_matches(rule,text,lists,include_cluster=True):
    found=[]; kind=rule["kind"]
    if kind=="regex":
        for p in rule.get("patterns",[]): found += pattern_matches(p,text)
        if include_cluster: found += cluster_matches(rule,text,lists)
    elif kind=="slots":
        for f in rule["families"]:
            cop="|".join(map(re.escape,f["copulas"]))
            if "noun_list" in f:
                noun="|".join(map(re.escape,lists[f["noun_list"]])); adj="|".join(map(re.escape,lists[f["adjective_list"]])); pattern=rf"\b(?:the|this|these)\s+(?:{noun})\s+(?:{cop})\s+(?:{adj})\b"
            else:
                sup="|".join(map(re.escape,lists[f["superlative_list"]])); pattern=rf"\bthe\s+(?:{sup})\s+[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){{0,2}}\s+(?:{cop})\b"
            found += [(m.start(),m.end(),f["family"]) for m in re.finditer(pattern,text,re.I)]
    elif kind=="pair":
        a="|".join(map(re.escape,lists[rule["list_a"]]))+r"|[A-Za-z]+(?:tion|ment|ness|ity|ance|ence)s?"; b="|".join(map(re.escape,lists[rule["list_b"]])); gap=int(rule.get("max_tokens",8)); pattern=rf"\b(?:{a})\b(?:\W+\w+){{0,{gap}}}?\W+\b(?:{b})(?:s|ed|ing)?\b"
        found += [(m.start(),m.end(),"abstract_physical_pair") for m in re.finditer(pattern,text,re.I)]
    elif kind=="frame":
        raw=[]
        for p in rule.get("patterns",[]): raw += pattern_matches(p,text)
        if len(raw)>=int(rule.get("threshold",2)): found=raw
    return found

def expand_sentence(text,start,end):
    for s,e,_ in sentences(text):
        if s<=start<e: return s,e
    return start,end

def question_is_protected(text,start,end,protection_spans):
    if any(x["code"]=="PROT-QUESTION" and not (x["end"]<=start or x["start"]>=end) for x in protection_spans): return True
    sentence=text[start:end].lstrip()
    declared=any(x["code"]=="PROT-QUESTION" for x in protection_spans)
    enumerated=bool(re.match(r"(?:first|second|third|fourth|fifth|sixth|finally)\b",sentence,re.I))
    return declared and enumerated

def claim_cue_is_negated(text):
    cue=r"(?:prov(?:e|es|ed|en)|demonstrat(?:e|es|ed|ing)|establish(?:es|ed|ing)?|rul(?:e|es|ed|ing)\s+out|settl(?:e|es|ed|ing))"
    direct=rf"\b(?:(?:do|does|did|can|could|may|might|would|should|is|are|was|were|has|have|had)\s+not|cannot|never)\s+(?:\w+[ -]){{0,3}}{cue}\b"
    passive=rf"\b(?:is|are|was|were|has|have|had)\s+not\s+(?:\w+[ -]){{0,2}}(?:proven|demonstrated|established|settled)\b"
    return bool(re.search(direct,text,re.I) or re.search(passive,text,re.I))

def make_mark(rule,p,start,end,family,protections):
    if rule.get("span")=="sentence": start,end=expand_sentence(p["text"],start,end)
    overlap=sorted({x["code"] for x in protections if not(x["end"]<=start or x["start"]>=end)})
    status=rule["verification"]["status"]
    return {"codes":[rule["code"]],"origin":"automatic_scan","paragraph_id":p["paragraph_id"],"source_locator":p["source_locator"],"start":start,"end":end,"quote":re.sub(r"\s+"," ",p["text"][start:end]).strip(),"trigger_families":[family],"review_priority":rule["review_priority"],"verification":status,"experimental":status!="verified","protections":overlap,"review_status":"unreviewed","rationale":None}

def merge_marks(marks):
    groups={}
    for x in marks: groups.setdefault((x["paragraph_id"],x["start"],x["end"]),[]).append(x)
    out=[]
    for same in groups.values():
        x=sorted(same,key=lambda y:(PRIORITY[y["review_priority"]],y["codes"][0]))[0].copy(); x["codes"]=sorted({c for y in same for c in y["codes"]}); x["trigger_families"]=sorted({c for y in same for c in y["trigger_families"]}); x["protections"]=sorted({c for y in same for c in y["protections"]}); out.append(x)
    out.sort(key=lambda x:(x["experimental"],PRIORITY[x["review_priority"]] if not x["experimental"] else 9,-len(x["codes"]) if not x["experimental"] else 0,x["source_locator"],x["start"]))
    for i,x in enumerate(out,1): x["mark_id"]=f"M{i:04d}"
    return out

def doc_observation(rule,prose):
    # Paragraph rhythm is a body-prose observation. Abstracts and keyword
    # blocks obey different editorial constraints and would distort it.
    counts=[len(words(p["text"])) for p in prose if fold(p.get("section", "")).strip().lower() != "abstract" and len(words(p["text"]))>=20]
    if len(counts)<int(rule.get("min_paragraphs",8)): return None
    mean=statistics.mean(counts); cv=statistics.pstdev(counts)/mean if mean else 0
    # The calibrated observation is the fixed 50--100-word band, not a
    # data-selected modal bin.  Selecting a bin after seeing the document would
    # manufacture apparent regularity.
    band_start,band_end=map(int,rule["band_words"]); n=sum(band_start <= value <= band_end for value in counts); share=n/len(counts)
    if cv>rule["max_cv"] or share<rule["min_band_share"]: return None
    status=rule["verification"]["status"]
    return {"observation_id":"D001","code":rule["code"],"origin":"document_stat","verification":status,"experimental":status!="verified","facts":{"eligible_paragraphs":len(counts),"paragraphs_in_configured_word_band":n,"fixed_band_words":[band_start,band_end],"shortest_paragraph_words":min(counts),"longest_paragraph_words":max(counts),"paragraph_length_cv":round(cv,3)},"interpretation_boundary":"Within-document observation only; not an AI indicator and not an instruction to split or merge paragraphs."}

def scan(source,rules_path,view,accept):
    cfg=load_rules(rules_path); paras,extraction=load_source(source,view,accept); prose=[p for p in paras if p["content_role"]=="prose"]
    automatic=[r for r in cfg["detection_rules"] if r["enabled"] and r["kind"] not in {"reading","doc_stat"}]; reading=[r["code"] for r in cfg["detection_rules"] if r["enabled"] and r["kind"]=="reading"]
    raw=[]; protected=[]
    for p in prose:
        ph=protection_hits(p["text"],cfg["protections"])
        for r in automatic:
            units=sentences(p["text"]) if r.get("span") in {"sentence","clause"} else [(0,len(p["text"]),p["text"])]
            for offset,_,text in units:
                for start,end,family in rule_matches(r,text,cfg["word_lists"],include_cluster=r.get("cluster",{}).get("scope")!="paragraph"):
                    mark=make_mark(r,p,offset+start,offset+end,family,ph)
                    reason=None
                    if "PROT-AI" in mark["protections"]: reason="AI-use statement overlaps a review mark"
                    elif r["code"]=="RHT-01" and "PROT-NEGATION" in mark["protections"]: reason="negated figure; editing could reverse the claim"
                    elif r["code"]=="META-03" and question_is_protected(p["text"],mark["start"],mark["end"],ph): reason="genuine, attributed, or task-material question"
                    elif r["code"]=="LOG-01" and claim_cue_is_negated(mark["quote"]): reason="directly negated claim-strength cue"
                    if reason: protected.append({"codes":mark["codes"],"protection_codes":mark["protections"],"source_locator":p["source_locator"],"quote":mark["quote"],"reason":reason})
                    else: raw.append(mark)
            if r.get("cluster",{}).get("scope")=="paragraph":
                for start,end,family in cluster_matches(r,p["text"],cfg["word_lists"]):
                    cluster_rule=dict(r); cluster_rule["span"]="paragraph"
                    mark=make_mark(cluster_rule,p,start,end,family,ph)
                    if "PROT-AI" in mark["protections"]: protected.append({"codes":mark["codes"],"protection_codes":mark["protections"],"source_locator":p["source_locator"],"quote":mark["quote"],"reason":"AI-use statement overlaps a review mark"})
                    else: raw.append(mark)
    observations=[x for r in cfg["detection_rules"] if r["enabled"] and r["kind"]=="doc_stat" for x in [doc_observation(r,prose)] if x]
    excluded={}
    for p in paras:
        if p["content_role"]!="prose": excluded[p["content_role"]]=excluded.get(p["content_role"],0)+1
    limitations=["Marks identify passages for contextual review; they do not identify authorship or prove AI involvement.","Direct script use performs the automatic scan only; reading-rule coverage remains partial.","Unverified and regression-only rules are experimental and do not enter normal priority layers."]
    if extraction["format"]=="pdf": limitations.append("PDF heading detection is heuristic and may exclude short prose blocks. Prefer Markdown or DOCX for high-stakes review.")
    if extraction["format"]=="docx": limitations.append("DOCX custom heading styles and non-body parts are not resolved automatically; inspect extraction diagnostics and prefer normalized Markdown when scope is uncertain.")
    return {"schema":"academic-de-ai-review-1.0","source":{"path":str(source),"sha256":digest(source),"format":extraction["format"]},"rules":{"path":str(rules_path),"sha256":digest(rules_path),"rule_count":len(cfg["detection_rules"])},"scope":{"paragraphs_total":len(paras),"paragraphs_reviewed_by_scan":len(prose),"excluded_by_role":excluded},"extraction":extraction,"reading_coverage":{"status":"partial","reviewed_sections":[],"unreviewed_sections":sorted({p["section"] or "(unheaded prose)" for p in prose}),"reading_rule_codes":reading},"span_marks":merge_marks(raw),"document_observations":observations,"protected":protected,"limitations":limitations}

def main():
    stdout_utf8(); ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("source",type=Path); ap.add_argument("--rules",type=Path,default=DEFAULT_RULES); ap.add_argument("--out",type=Path); ap.add_argument("--revision-view",choices=("accepted","original")); ap.add_argument("--accept-pdf-warning",action="store_true"); args=ap.parse_args()
    try:
        if not args.source.is_file(): raise ValueError(f"source not found: {args.source}")
        if not args.rules.is_file(): raise ValueError(f"rules not found: {args.rules}")
        if args.out and args.out.exists(): raise ValueError(f"refusing to overwrite existing output: {args.out}")
        result=scan(args.source,args.rules,args.revision_view,args.accept_pdf_warning); rendered=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
        if args.out: args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(rendered,encoding="utf-8"); print(f"Wrote {args.out}")
        else: print(rendered,end="")
        print("Reading rules not checked by fast scan: "+", ".join(result["reading_coverage"]["reading_rule_codes"]),file=sys.stderr); return 0
    except (OSError,ValueError,json.JSONDecodeError,zipfile.BadZipFile) as e: print(f"error: {e}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
