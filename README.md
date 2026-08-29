# academic-prose-pattern-review

[![tests](https://github.com/xburner23412/academic-prose-pattern-review/actions/workflows/tests.yml/badge.svg)](https://github.com/xburner23412/academic-prose-pattern-review/actions/workflows/tests.yml)

A review skill that marks formulaic, over-performed, or evidence-straining
features in English academic prose, so a person can read those passages again in
context.

**It is not an AI-authorship detector.** A mark means "read this in context," not
"a model wrote this." The skill reports no score, no probability, no
per-thousand-word rate, and no authorship conclusion. It never edits your
manuscript.

## Why not a detector

Detecting AI authorship from style does not work well enough to act on, and this
tool deliberately does not try.

Published research finds humans at or near chance when separating LLM text from
human text; a 2025 study of German theses reports 57% recognition of AI text and
64% of human text. Automated detectors carry non-trivial error rates and are
defeated by paraphrase and markup changes. Human and model prose are also
converging, so a signal that separated the two last year may not this year.

More concretely: while this rule table was being built, the same feature that
looked most discriminating on a ratio turned out, on reading every hit, to be
firing on ordinary enumerations — brain regions, database names, and an author
list. The ratio said keep; reading said cut.

So the design question here is not "does this pattern identify an author" but
"is this passage worth a second look."

## What it does

- Reads Markdown, TXT, DOCX and PDF.
- Excludes headings, references, acknowledgements, AI-use declarations and
  methods appendices from scanning, and reports what it excluded.
- Applies 20 feature rules — 14 automatic, 6 requiring a full read.
- Runs a protection pass so a marked span that carries a citation, a quantity, a
  hedge, a negation or a research question is labelled protected rather than
  offered as a problem.
- Emits a review JSON and renders a self-contained HTML report in English or
  Chinese.

Marks are ordered by review priority, then by how many distinct feature codes
co-occur in the same paragraph, then by document order. Several different
features firing in one paragraph is the signal; the same rule firing five times
usually means that rule is misfiring there.

## Install

Copy the `academic-de-ai` folder into your skills directory.

Claude Code:

```
~/.claude/skills/academic-de-ai
```

Codex:

```
%USERPROFILE%\.codex\skills\academic-de-ai
```

Restart, then invoke it explicitly:

```
$academic-de-ai
```

The skill is `explicit-only`; it will not trigger on its own.

PDF support needs one dependency:

```bash
pip install pypdf
```

## Run the scanner directly

```bash
python academic-de-ai/scripts/mark_patterns.py article.md --out review.json
python academic-de-ai/scripts/render_marked_report.py review.json --out report.html --lang en
python academic-de-ai/scripts/validate_review.py review.json --source article.md
```

Add `--source article.md` to the renderer to lay the manuscript out with every
mark highlighted in place, coloured by how the mark was adjudicated. The file
must still hash to the value recorded in the review; a source that has moved on
is refused rather than annotated with stale offsets. Without `--source` the
report lists quotations only, which keeps a review JSON shareable without the
manuscript attached.

Running the script by itself is a **fast scan**. It prints the reading rules it
did not check, and the report is labelled partial. A full review — scan plus a
reading pass over the whole text, plus contextual adjudication of every
automatic mark — happens when you invoke the skill.

`render_marked_report.py` refuses to overwrite an existing output path.

## Rule codes

`RHT` rhetoric · `META` metadiscourse · `STR` structure · `LEX` lexis ·
`LOG` logic and evidence

| Code | Feature | Kind |
|---|---|---|
| `RHT-01` | manufactured metaphor or personification | automatic |
| `RHT-02` | aphoristic or punchline-style sentence | automatic |
| `RHT-03` | artificial antithesis or slogan | reading |
| `RHT-04` | false `from X to Y` range | automatic |
| `META-01` | reader-directed evaluation | automatic |
| `META-02` | mechanical navigation or metadiscourse | automatic |
| `META-03` | rhetorical question or staged self-answer | automatic |
| `META-04` | formulaic challenges-and-outlook closing | reading |
| `META-05` | answering an objection no one raised | reading |
| `META-06` | artificial alternative setup | reading |
| `STR-01` | repeated negative-contrast frame | automatic |
| `STR-02` | forced group of three | reading |
| `STR-04` | uniform paragraph size | document observation |
| `LEX-01` | promotional or inflated evaluation | automatic |
| `LEX-03` | copula avoidance | automatic |
| `LEX-05` | shallow significance participle | automatic |
| `LOG-01` | claim strength exceeds evidence | automatic |
| `LOG-02` | scope or causal overgeneralization | automatic |
| `CIT-01` | citation placement and stacking | automatic |
| `LEX-06` | invented paraphrase of a standard expression | reading |

A single watched word never produces a mark. A promotional word has to form a
complete construction or cluster with other features.

`STR-04` reports only facts internal to the manuscript — paragraph count, mean
length, the band most paragraphs fall in. It never calls a distribution abnormal
and never suggests splitting or merging paragraphs to change the number.

The rule table is `academic-de-ai/rules.json`. Adding a rule of an existing kind
(`regex`, `slots`, `pair`, `frame`) is a JSON edit; a new kind needs code.
`academic-de-ai/references/patterns.md` explains what each rule is for and what
must never be touched.

## What it will not do

These are constraints, not preferences.

| Never | Because |
|---|---|
| Remove or weaken a hedge | It strengthens a claim the evidence does not support |
| Remove passive voice | Normative in methods and results sections |
| Change dashes, quotation marks, bold or heading case | House style, not authorship |
| Delete a negated figure | The negation is often the argument |
| Edit a paragraph containing an AI-use declaration without re-surfacing it | An accepted change elsewhere can make the declaration untrue |
| Drop a citation, a number, or a spelled-out quantity | `among at least three` → `among several` loses a count with no digit in it |
| Score vocabulary density or transition-word frequency | Measured on this project's own material, a 2021 human paper scored *higher* than the AI-assisted document on both |

## Known limits

- **PDF.** Extraction damage is real: headings, reference entries and running
  headers land in the prose, and words run together. The scanner refuses outright
  after two independent damage signals, and requires `--accept-pdf-warning` after
  one. Prefer Markdown or DOCX for anything that matters.
- **DOCX.** Tracked changes stop the run until you choose
  `--revision-view accepted|original`, because `python-docx`-style flattening
  silently drops text inside `w:ins` and would put every offset in the wrong
  place. Comments are excluded and counted. Custom heading styles and non-body
  parts — headers, footers, footnotes, text boxes — need inspection.
- **Language and field.** English social-science and psychology prose. The rules
  were built and read against that register.
- **Six rules need a human.** `RHT-03`, `META-04`, `META-05`, `META-06`,
  `STR-02` and `LEX-06` have no automatic implementation and are listed as
  unchecked in a fast scan.

## Status

**Rules run; overall effectiveness is not established.**

Each rule carries a `verification` block recording the last time a person reread
its hits, bound to a rule revision so it goes stale when the rule changes. That
establishes the implementation was reread. It does not establish that a marked
passage is bad prose, and it does not measure recall.

Development used a single AI-assisted review article plus three open-access
Frontiers reviews published in 2017, 2019 and 2021 — before ChatGPT — as a
context bench. The bench exists to show how these constructions appear in
legitimate academic prose, so the protections can be written correctly. **A hit
on a human paper is not defined as a false positive**, and no rule is vetoed by
one.

Stable effectiveness would need held-out AI-generated academic texts across
several model families, topics and editing levels. That work has not been done.

`academic-de-ai/testbed/manifest.json` records the SHA-256 of every document
used, and `context-bench-review.json` records how each automatic mark was
labelled. The document texts are third-party articles and are not redistributed;
the hashes let you verify you have the same bytes.

## Licence

MIT, for the code and rule table — see [LICENSE](LICENSE).

The articles referenced in `testbed/manifest.json` are not covered by it and are
not distributed here.
