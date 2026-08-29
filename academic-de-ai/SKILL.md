---
name: academic-de-ai
description: Review English social-science and psychology prose for formulaic, over-performed, mechanically polished, or evidence-straining features. Use only when explicitly invoked. Review and mark only; never estimate AI authorship or edit the manuscript.
metadata:
  version: "1.0.0-pre"
---

# Academic De-AI

Review prose features without claiming to detect authorship. A mark means “read
this in context,” not “AI wrote this.” Prefer abstention to a weak mark.

Source prose stays English. Explanations follow the user's language. JSON field
names stay English.

## Scope

- English social-science and psychology prose.
- Markdown, TXT, DOCX and PDF.
- Version 1 reviews and marks only. It does not rewrite, apply edits, compare
  versions, profile an author, or optimize detector scores.
- Invoke only when the user explicitly asks for `$academic-de-ai`.

## Required reference

Read [references/patterns.md](references/patterns.md) before reviewing. Treat
`rules.json` as the executable rule table.

## Run

1. Run `scripts/mark_patterns.py SOURCE --out review.json`.
2. Inspect extraction status, excluded roles, source hash and partial reading
   coverage before interpreting marks.
3. Read all included prose. Apply the five reading rules in `patterns.md`,
   adjudicate automatic marks in context, and run the protection pass.
4. Set every automatic mark to `keep`, `protected_or_functional`, or
   `rule_misfire` with a brief rationale. Add reading marks with `origin:
   model_reading`; retain exact paragraph,
   offsets, quote and source locator. Change `reading_coverage.status` to
   `complete` only after every included section has been read.
5. Render with `scripts/render_marked_report.py review.json --out report.html
   --lang LANG`, where `LANG` follows the user's language (`en` fallback). Add
   `--source SOURCE` to lay the manuscript out with every mark in place; the
   file must still hash to the value recorded in the review, and rendering is
   refused when it does not. Without `--source` the report lists quotations
   only, so a review JSON stays shareable without the manuscript.
6. Report the marks, protected passages, document observations and limits. Do
   not silently turn a mark into a proposed edit.

Direct use of `mark_patterns.py` is a fast scan only. It must list the reading
rules it did not check. Normal skill invocation includes both the scan and the
full reading pass.

## Interpretation

Sort verified marks by review priority, then by the number of distinct
co-occurring feature codes, then document order. Do not display a score.
Experimental marks remain outside priority layers.

Judge patterns as constructions and discourse moves. A single word never
constitutes a mark. Rarity alone never requires rejection. A feature that also
appears in human writing is not therefore a misfire.

The primary effectiveness question is whether the rules consistently recover
review-worthy features across varied AI-generated or AI-assisted academic
texts. Human context-bench hits are used to understand legitimate contexts and
protect meaning, not to eliminate a rule. Do not claim stable effectiveness
from the single A01 development pilot.

`STR-04` is a separate document observation. Report only raw facts internal to
the manuscript. Never call it abnormal, compare it with “human writing,” infer
AI use, or suggest splitting/merging paragraphs to change it.

## Safety and abstention

- Never edit or overwrite the source. Refuse an existing output path.
- Preserve citations, quantities, terminology, scope, negation, hedges, causal
  strength, cross-references and AI-use statements.
- Exclude headings, references, acknowledgements, AI declarations, methods
  appendices and comments from prose scanning. Protect an inline AI-use
  statement even when it has no heading.
- For tracked DOCX changes, stop until `--revision-view accepted|original` is
  explicitly selected.
- For PDF, refuse after two independent extraction-damage signals. With one,
  require inspection plus `--accept-pdf-warning`, or request another format.
- PDF heading detection remains heuristic, and DOCX custom heading styles and
  non-body parts require inspection. Prefer normalized Markdown or DOCX for
  high-stakes work when extraction scope is uncertain.
- If reading coverage is incomplete, label the report partial and list the
  unreviewed sections.
- If evidence is insufficient, say: `Insufficient evidence. No change
  recommended.`

## Output boundary

Never output an AI score, probability, mark-density interpretation,
per-thousand-word rate, or authorship conclusion. Verification establishes that
a rule implementation was reread; it does not establish that a marked passage
is bad prose.
