#!/usr/bin/env python3
"""Stage a JATS/NLM XML article as main-body prose Markdown.

This testbed utility extracts main-body prose and reports every dropped section.
Only `<body>` is read, so title, author information, affiliations, abstract, and
keywords are excluded by construction: they live in `<front>`. References,
acknowledgements, funding, conflict statements, author contributions, data
statements, and publisher notes live in `<back>` and are excluded the same way.

Inside `<body>` the converter still has work to do, because publishers put
back-matter sections in the body, and because tables, figures, boxed material,
and formulae are interleaved with prose.

In-text citation markers are kept. They are part of the sentence, they are a
protected element downstream, and the context-bench documents carry them, so
removing them here would make the corpora non-comparable.

This is a staging tool, not a detector. It makes no judgement about prose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET

# Body-level sections that belong to back matter. Publishers place these
# inconsistently; H01-H03 are Frontiers, which puts several of them in <body>.
BACK_MATTER_TITLES = (
    r"references?", r"reference\s+list", r"bibliography",
    r"acknowledg(?:e)?ments?",
    r"(?:author\s+)?contributions?", r"author\s+note",
    r"(?:conflicts?\s+of\s+interest|competing\s+interests?)(?:\s+statement)?",
    r"fundings?(?:\s+statement)?", r"financial\s+(?:support|disclosure)",
    r"data\s+availability(?:\s+statement)?", r"data\s+and\s+code\s+availability",
    r"ethics(?:\s+statement)?", r"ethical\s+approval",
    r"supplementary\s+(?:material|materials|information|data)",
    r"abbreviations?", r"glossary",
    r"publisher'?s?\s+note", r"disclaimer",
    r"(?:declaration|statement)s?\s+.*\b(?:ai|artificial\s+intelligence|generative\s+ai)\b",
    r"abstract", r"keywords?",
)
BACK_MATTER_RE = re.compile(r"^(?:%s)$" % "|".join(BACK_MATTER_TITLES), re.I)

# Elements whose entire subtree is out of scope: tables, figures, boxed
# material, formulae, media, and footnotes.
DROP_TAGS = frozenset({
    "table-wrap", "table-wrap-foot", "table", "fig", "fig-group", "graphic",
    "media", "inline-graphic", "boxed-text", "supplementary-material",
    "disp-formula", "disp-formula-group", "inline-formula", "tex-math", "mml:math",
    "fn", "fn-group", "author-notes", "ref-list", "app", "app-group",
    "notes", "glossary", "def-list", "array", "chem-struct-wrap",
    "label", "caption", "attrib", "permissions", "object-id",
})


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def inline_text(node: ET.Element) -> str:
    """Flatten an element to text, dropping out-of-scope subtrees.

    `<xref>` is deliberately kept: an in-text citation is part of the sentence.
    """
    parts = [node.text or ""]
    for child in node:
        if local(child.tag) not in DROP_TAGS:
            parts.append(inline_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()


def section_title(sec: ET.Element) -> str:
    title = sec.find("title")
    return clean(inline_text(title)) if title is not None else ""


def match_key(title: str) -> str:
    """Fold a section title to a form the back-matter patterns can match.

    Frontiers renders `Publisher's Note` with U+2019, so an ASCII apostrophe in
    the pattern misses it and 78 words of publisher disclaimer reach the scored
    prose. Fold the quotation marks and dashes publishers actually use.
    """
    folded = title.rstrip(":").strip()
    for source, target in (("’", "'"), ("‘", "'"), ("ʼ", "'"),
                           ("“", '"'), ("”", '"'),
                           ("–", "-"), ("—", "-"), ("−", "-")):
        folded = folded.replace(source, target)
    return folded


def walk(sec: ET.Element, depth: int, out: list[str], dropped: list[str]) -> None:
    title = section_title(sec)
    if title and BACK_MATTER_RE.match(match_key(title)):
        dropped.append(title)
        return
    if title:
        out.append("%s %s" % ("#" * min(6, depth), title))
    for child in sec:
        tag = local(child.tag)
        if tag in DROP_TAGS or tag == "title":
            continue
        if tag == "sec":
            walk(child, depth + 1, out, dropped)
        elif tag in ("p", "disp-quote", "statement", "verse-group", "speech"):
            text = clean(inline_text(child))
            if text:
                out.append(text)
        elif tag == "list":
            for item in child.iter():
                if local(item.tag) == "list-item":
                    text = clean(inline_text(item))
                    if text:
                        out.append(text)


def convert(path: Path) -> tuple[str, dict]:
    root = ET.parse(path).getroot()
    article = root if local(root.tag) == "article" else root.find(".//article")
    if article is None:
        raise SystemExit("no <article> element in %s" % path)
    front, body = article.find("front"), article.find("body")
    if body is None:
        raise SystemExit("no <body> element in %s" % path)

    title_el = front.find(".//article-title") if front is not None else None
    doi = None
    if front is not None:
        doi = next((clean(inline_text(e)) for e in front.iter("article-id")
                    if e.get("pub-id-type") == "doi"), None)

    out: list[str] = []
    dropped: list[str] = []
    title = clean(inline_text(title_el)) if title_el is not None else ""
    if title:
        out.append("# " + title)
    for child in body:
        tag = local(child.tag)
        if tag in DROP_TAGS:
            continue
        if tag == "sec":
            walk(child, 2, out, dropped)
        elif tag == "p":
            text = clean(inline_text(child))
            if text:
                out.append(text)

    text = "\n\n".join(out) + "\n"
    prose_blocks = [b for b in out if not b.startswith("#")]
    meta = {
        "source": str(path),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "doi": doi,
        "title": title,
        "blocks": len(out),
        "heading_blocks": len(out) - len(prose_blocks),
        "prose_blocks": len(prose_blocks),
        "prose_words": sum(len(b.split()) for b in prose_blocks),
        "dropped_body_sections": dropped,
        "scope": "main-body prose; non-prose back matter reported as dropped",
    }
    return text, meta


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    text, meta = convert(args.source)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    meta["output"] = str(args.out)
    meta["output_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    rendered = json.dumps(meta, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
