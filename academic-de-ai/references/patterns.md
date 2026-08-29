# Feature rules and protections

This reference defines what the skill reviews. A mark is a request for
contextual reading, not a claim about who wrote the text. The executable source
of truth is `rules.json`; this file explains the semantics.

## The 20 feature codes

### Automatic span rules

| Code | Review question |
|---|---|
| `RHT-01` | Does an abstract construct receive a conspicuously physical action or vehicle? Conventional technical metaphors and negated figures are protected. |
| `RHT-02` | Does a polished verdict restate nearby content mainly as a punchline? An ordinary short sentence is insufficient. |
| `RHT-04` | Do the endpoints in a `from X to Y` phrase fail to form a real scale, interval, sequence, or process? |
| `META-01` | Does the prose rank clarity, importance, or informativeness for the reader without supplying the comparison? |
| `META-02` | Does a complete navigation frame announce movement without adding content? Isolated transitions never qualify. |
| `META-03` | Does a question stage emphasis instead of specifying a genuine research question? |
| `STR-01` | Does one paragraph repeat negative-contrast frames? One contrast is ordinary prose. |
| `LEX-01` | Does a complete promotional frame occur, or do at least two distinct inflated evaluators cluster? One watched word never qualifies. |
| `LEX-03` | Does an ornate verb merely replace a clearer copula, without a technical meaning? |
| `LEX-05` | Does a trailing participial phrase announce significance without adding evidence? |
| `LOG-01` | Does the strength of a claim exceed the evidence in its sentence and local argument? The cue alone is not the answer. |
| `LOG-02` | Does a scope or causal claim outrun the population, design, diagnosis, or mechanism actually studied? |
| `CIT-01` | Can a reader tell which source supports which claim? Three or more sources in one parenthetical, or an agentless attribution that hides who found what. Not an AI signal: the context bench's human reviews stack more heavily than the AI-assisted document. |

### Full-reading rules

The scanner lists these as unchecked. `$academic-de-ai` must read the relevant
sections and add any marks with `origin: model_reading`.

| Code | Review question |
|---|---|
| `RHT-03` | Is an antithesis false, slogan-like, or qualification-destroying? Ordinary `rather than` distinctions are not marks. |
| `META-04` | Does a challenges/outlook ending replace the last supported claim with generic difficulty and optimism? |
| `META-05` | Does defensive prose answer an objection that has no source and no role in the argument? |
| `META-06` | Does the text invent an option no serious reader would choose, reject it, and never use it again? |
| `STR-02` | Is one item in a group of three redundant, vague, or rhythm-filling? Real three-part entities are protected. |
| `LEX-06` | Does a phrase replace the field's conventional wording with an invented one? Judge the head collocation, not the whole n-gram: almost every four-word sequence of English is rare. Terms of art are not coinages. |

### Document observation

`STR-04` records unusually uniform body-paragraph size as a separate
`document_observation`. It may show raw within-document facts for audit. It must
not compare the manuscript with “human writing,” call the pattern abnormal,
infer AI involvement, enter mark priority, or recommend splitting or merging
paragraphs. If its calibrated conditions are not met, omit it.

## Where the rules come from

Three sources, and the third was added late after an audit found it missing.

1. Wikipedia's *Signs of AI writing* and the `humanizer` skill, both about
   general prose.
2. This project's own measurements against an AI-assisted review and three
   pre-ChatGPT articles.
3. The editorial criteria this project accumulated while revising one essay by
   hand, recorded as `P0`-`P6` in the project handoff.

The third source was nearly lost. Its lessons were written down as constraints
on the reviser -- do not break a citation, do not invent a paraphrase -- so when
version 1 stopped editing, they had nowhere to live. `CIT-01` and `LEX-06` are
those criteria restated as things to look for in the manuscript. Anything an
editing mode would need to avoid doing still has no detection counterpart, and
that gap returns the moment an apply mode exists.

## Review priority and verification

`review_priority` means order of review, not probability or severity. A rule is
`verified` only when its current revision has been reread on its recorded
fixtures. A changed rule resets to `unverified`. `unverified` and
`regression_only` marks are shown as experimental and do not enter high/low
priority layers.

The context bench labels individual hits as `feature_present`,
`protected_or_functional`, or `rule_misfire`. A hit in a pre-ChatGPT article is
not automatically a false positive: these are prose features, not authorship
detectors.

Context-bench behavior is not the effectiveness target and must not veto a
useful rule. Effectiveness means that the feature set repeatedly recovers
review-worthy constructions across held-out AI-generated or AI-assisted
academic texts from different model families, topics, and editing levels.
Implementation verification and effectiveness evidence are separate. The
current A01 pilot is development material and cannot establish that stability.

## Protection pass

Before presenting or revising a mark, protect:

- facts, citations, numbers and spelled-out quantities;
- terminology, diagnosis, sample and population scope;
- negation, modal verbs, hedges, causal strength and cross-references;
- genuine research questions, quotations and task materials;
- conventional disciplinary metaphors whose literal replacement would be less precise;
- AI-use statements, acknowledgements and methods appendices;
- headings, reference entries, publisher notes and comments.

Display a protection only when it overlaps a mark or is a document-level
safeguard the user needs to know about.

## Never do these

- Never treat a watched word, punctuation mark, rare collocation, or isolated
  transition as a mark by itself.
- Never score AI vocabulary, transition frequency, mark density, or an overall
  AI likelihood. These measures did not distinguish the development materials.
- Never use deviation from an author corpus as evidence against the author.
- Never remove a hedge, passive voice, citation, number, negation, or protected
  statement merely to make prose look less automated.
- Never edit the manuscript in version 1. Review and mark only.
- Never split or merge paragraphs to alter `STR-04`.

## Format hazards preserved from prior failures

- DOCX with tracked insertions, deletions, or moves is blocked until the user
  selects the accepted or original revision view. Comments are excluded and
  counted. Do not pretend `paragraph.text` represents revision markup.
- PDF extraction is refused after two independent damage signals. One signal
  requires inspection and explicit confirmation or an alternate format.
- PDF heading recognition is heuristic: a short block without terminal
  punctuation may be treated as a heading. For high-stakes review, prefer
  normalized Markdown or DOCX and inspect the reported exclusions.
- DOCX recognizes built-in Heading styles plus Title/Subtitle. Custom heading
  styles are not resolved automatically; headers, footers, footnotes and
  endnotes are reported as non-body parts rather than silently scanned.
- Section matching folds curly quotes and dashes. This prevents `Publisher’s
  Note` from entering prose when only the ASCII spelling was anticipated.
- Sentence boundaries protect `et al.`, `e.g.`, `i.e.`, `cf.`, `Fig.`, `p.`,
  `vs.`, initials and decimals. Placeholders must preserve source offsets.
- Every command-line entry point uses UTF-8 output. A prior GBK console failed
  on names such as `Leppänen` after completing extraction.
- Every displayed locator must resolve to the unchanged source hash. The
  renderer uses cards rather than fragile links to missing anchors.

## Minimal reading record

A completed review contains:

```json
{
  "reading_coverage": {
    "status": "complete",
    "reviewed_sections": ["Introduction", "Discussion"],
    "unreviewed_sections": [],
    "reading_rule_codes": ["RHT-03", "META-04", "META-05", "META-06", "STR-02"]
  }
}
```

Every reading mark uses the same locator and quote fields as an automatic mark,
sets `origin` to `model_reading`, and records the trigger family. During a full
reading pass, set every mark's `review_status` to `keep`,
`protected_or_functional`, or `rule_misfire` and add a brief `rationale`.
The fast scan leaves `review_status: unreviewed`. Source text
remains unchanged. If coverage is partial, say so prominently; never let a
partial read impersonate a complete review.
