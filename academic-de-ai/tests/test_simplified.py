import hashlib, importlib.util, json, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/filename); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

MARK=load("mark_patterns_simplified","mark_patterns.py")
RENDER=load("render_marked_report_simplified","render_marked_report.py")
VALIDATE=load("validate_review_simplified","validate_review.py")
RULES=MARK.load_rules(ROOT/"rules.json")

class SimplifiedRules(unittest.TestCase):
    def setUp(self): self.lists=RULES["word_lists"]; self.by_code={r["code"]:r for r in RULES["detection_rules"]}
    def hits(self,code,text): return MARK.rule_matches(self.by_code[code],text,self.lists)
    def test_exactly_eighteen_semantic_codes(self):
        self.assertEqual(len(self.by_code),18); self.assertFalse(any(c.startswith("OTHER-") for c in self.by_code))
        for rule in self.by_code.values(): self.assertEqual(rule["verification"]["rule_revision"],rule["rule_revision"])
    def test_automatic_positive_examples(self):
        cases={
          "RHT-01":"The theory became a mental brake on interpretation.",
          "RHT-02":"The point is straightforward.",
          "RHT-04":"The claim jumps from attention to certainty.",
          "META-01":"The clearest research gap is developmental comparison.",
          "META-02":"We now turn to the second account.",
          "META-03":"What could be clearer?",
          "STR-01":"It concerns evidence rather than style, and mechanism rather than label.",
          "LEX-01":"This particularly promising account can advance the field.",
          "LEX-03":"The construct serves as an explanation.",
          "LEX-05":"The result changed, highlighting its importance.",
          "LOG-01":"These data prove the claim.",
          "LOG-02":"The mechanism is universal across all groups.",
        }
        for code,text in cases.items():
            with self.subTest(code=code): self.assertTrue(self.hits(code,text))
    def test_reading_rules_are_explicit_not_scanned(self):
        reading={r["code"] for r in RULES["detection_rules"] if r["kind"]=="reading"}
        self.assertEqual(reading,{"RHT-03","META-04","META-05","META-06","STR-02"})
    def test_single_inflated_word_is_not_a_mark(self): self.assertFalse(self.hits("LEX-01","The estimate was robust."))
    def test_lex_cluster_uses_paragraph_scope_across_sentences(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"x.md"; path.write_text("# T\n\nThe account is compelling. The estimate is robust.",encoding="utf-8")
        result=MARK.scan(path,ROOT/"rules.json",None,False)
        clusters=[x for x in result["span_marks"] if "LEX-01" in x["codes"] and "evaluative_cluster" in x["trigger_families"]]
        self.assertEqual(len(clusters),1); self.assertEqual(clusters[0]["quote"],"The account is compelling. The estimate is robust.")
    def test_isolated_transition_is_not_a_mark(self): self.assertFalse(self.hits("META-02","However, the estimate changed."))
    def test_single_contrast_is_not_a_mark(self): self.assertFalse(self.hits("STR-01","Evidence matters rather than style."))
    def test_abbreviation_sentence_boundaries(self):
        text="Smith et al. (2020) reported it. The N2 was reduced vs. controls. Fig. 2 shows M = 3.4."
        self.assertEqual(len(MARK.sentences(text)),3)
        long_text=("A. B. reported a value of 3.14 vs. controls. "+"word "*500+"Done.")
        spans=MARK.sentences(long_text)
        self.assertTrue(all(0 <= start < end <= len(long_text) for start,end,_ in spans))

class SourceAndSafety(unittest.TestCase):
    def scan_text(self,text):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"x.md"; path.write_text(text,encoding="utf-8"); return MARK.scan(path,ROOT/"rules.json",None,False)
    def test_headings_references_and_ai_declaration_sections_are_excluded(self):
        result=self.scan_text("# T\n\n## Body\n\nThe point is straightforward.\n\n## Declaration of AI use\n\nThe point is straightforward.\n\n## References\n\nThe point is straightforward.")
        self.assertEqual(len(result["span_marks"]),1); self.assertEqual(result["scope"]["excluded_by_role"]["protected_section"],1); self.assertEqual(result["scope"]["excluded_by_role"]["reference"],1)
    def test_inline_ai_statement_is_protected(self):
        result=self.scan_text("# T\n\nThis review was AI-assisted, and the point is straightforward.")
        self.assertEqual(result["span_marks"],[]); self.assertTrue(result["protected"])
    def test_negated_metaphor_is_protected(self):
        result=self.scan_text("# T\n\nFrontalization does not prove that the mechanism is a localized brake.")
        self.assertFalse(any("RHT-01" in x["codes"] for x in result["span_marks"])); self.assertTrue(any("PROT-NEGATION" in x["protection_codes"] for x in result["protected"]))
    def test_declared_research_questions_are_protected(self):
        result=self.scan_text("# T\n\nThis review asks the following research question: What does inhibition measure?")
        self.assertFalse(any("META-03" in x["codes"] for x in result["span_marks"])); self.assertTrue(result["protected"])
    def test_formal_and_rhetorical_questions_in_one_paragraph_are_separated(self):
        result=self.scan_text("# T\n\nThis review asks one research question: What does inhibition measure? But who could possibly disagree?")
        questions=[x for x in result["span_marks"] if "META-03" in x["codes"]]
        self.assertEqual(len(questions),1); self.assertEqual(questions[0]["quote"],"But who could possibly disagree?")
        self.assertTrue(any("What does inhibition measure?" in x["quote"] for x in result["protected"]))
    def test_attributed_quoted_question_is_protected_but_staged_self_quote_is_not(self):
        attributed=self.scan_text('# T\n\nSmith asked, "What does inhibition measure?"')
        self.assertFalse(any("META-03" in x["codes"] for x in attributed["span_marks"])); self.assertTrue(attributed["protected"])
        staged=self.scan_text('# T\n\nThe question shifts from "Is the effect smaller?" to "Does the mechanism change?"')
        self.assertTrue(any("META-03" in x["codes"] for x in staged["span_marks"]))
    def test_directly_negated_claim_cue_is_protected(self):
        negated=self.scan_text("# T\n\nThese data do not prove a unique mechanism.")
        self.assertFalse(any("LOG-01" in x["codes"] for x in negated["span_marks"])); self.assertTrue(any("directly negated" in x["reason"] for x in negated["protected"]))
        affirmed=self.scan_text("# T\n\nThese data prove a unique mechanism.")
        self.assertTrue(any("LOG-01" in x["codes"] for x in affirmed["span_marks"]))
    def test_document_observation_is_separate_and_nonprescriptive(self):
        body="\n\n".join(" ".join(["word"]*60)+"." for _ in range(10)); result=self.scan_text("# T\n\n## Body\n\n"+body)
        self.assertEqual(len(result["document_observations"]),1); self.assertNotIn("STR-04",[c for x in result["span_marks"] for c in x["codes"]]); self.assertIn("not an instruction",result["document_observations"][0]["interpretation_boundary"]); self.assertEqual(result["document_observations"][0]["facts"]["fixed_band_words"],[50,100])
    def test_no_authorship_metrics(self):
        result=self.scan_text("# T\n\nThe point is straightforward."); keys=json.dumps(result).lower()
        for forbidden in ('"ai_score"','"probability"','"per_1000"','"mark_density"','"confidence"'): self.assertNotIn(forbidden,keys)
    def test_output_refuses_overwrite_contract(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); source=Path(td.name)/"x.md"; output=Path(td.name)/"existing.json"; source.write_text("# T\n\nThe point is straightforward.",encoding="utf-8"); output.write_text("sentinel",encoding="utf-8")
        run=subprocess.run([sys.executable,str(ROOT/"scripts"/"mark_patterns.py"),str(source),"--out",str(output)],capture_output=True,text=True)
        self.assertEqual(run.returncode,2); self.assertIn("refusing to overwrite",run.stderr); self.assertEqual(output.read_text(encoding="utf-8"),"sentinel")
    def make_docx(self,path,changed=False,comments=False):
        ins='<w:ins w:id="1"><w:r><w:t>inserted</w:t></w:r></w:ins>' if changed else ''
        document=f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Body</w:t></w:r></w:p><w:p><w:r><w:t>The point is straightforward.</w:t></w:r>{ins}</w:p></w:body></w:document>'
        with zipfile.ZipFile(path,"w") as z:
            z.writestr("word/document.xml",document)
            if comments: z.writestr("word/comments.xml",'<?xml version="1.0"?><w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:comment w:id="0"><w:p><w:r><w:t>secret</w:t></w:r></w:p></w:comment></w:comments>')
    def test_docx_comments_counted_and_tracked_changes_blocked(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); clean=Path(td.name)/"clean.docx"; changed=Path(td.name)/"changed.docx"; self.make_docx(clean,comments=True); self.make_docx(changed,changed=True)
        _,meta=MARK.load_docx(clean,None); self.assertEqual(meta["comments_excluded"],1)
        with self.assertRaises(ValueError): MARK.load_docx(changed,None)
        paras,meta=MARK.load_docx(changed,"accepted"); self.assertTrue(meta["tracked_changes"]); self.assertIn("inserted",paras[-1]["text"])
    def test_pdf_damage_gate_calibration(self):
        signals,_=MARK.pdf_damage(["short\nlines\nAReallyLongGluedAlphabeticalTokenHere �"])
        self.assertGreaterEqual(len(signals),2)
    def test_renderer_preserves_source_quote_and_shows_partial_coverage(self):
        result=self.scan_text("# T\n\nThe point is straightforward."); page=RENDER.render(result,"zh")
        self.assertIn("The point is straightforward.",page); self.assertIn("不完整",page); self.assertNotIn("AI 概率",page)
    def test_renderer_keeps_contextual_adjudications_visible(self):
        result=self.scan_text("# T\n\nThe point is straightforward. These data prove the claim.")
        result["span_marks"][0]["review_status"]="protected_or_functional"; result["span_marks"][0]["rationale"]="The sentence states a section function that must be retained."
        result["span_marks"][1]["review_status"]="rule_misfire"; result["span_marks"][1]["rationale"]="The verb describes task establishment, not evidential certainty."
        page=RENDER.render(result,"en")
        self.assertIn("Contextual adjudications",page); self.assertIn("protected_or_functional",page); self.assertIn("rule_misfire",page); self.assertIn("task establishment",page)
    def test_lightweight_validator_resolves_every_quote(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"x.md"; path.write_text("# T\n\nThe point is straightforward.",encoding="utf-8"); result=MARK.scan(path,ROOT/"rules.json",None,False)
        self.assertEqual(VALIDATE.validate(result,path,ROOT/"rules.json"),[])
        result["span_marks"][0]["quote"]="wrong"
        self.assertTrue(any("does not resolve" in x for x in VALIDATE.validate(result,path,ROOT/"rules.json")))
    def test_complete_reading_requires_every_mark_to_be_adjudicated(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"x.md"; path.write_text("# T\n\nThe point is straightforward.",encoding="utf-8"); result=MARK.scan(path,ROOT/"rules.json",None,False)
        result["reading_coverage"]={"status":"complete","reviewed_sections":["T"],"unreviewed_sections":[],"reading_rule_codes":["RHT-03","META-04","META-05","META-06","STR-02"]}
        self.assertTrue(any("unreviewed marks" in x for x in VALIDATE.validate(result,path,ROOT/"rules.json")))
        result["span_marks"][0]["review_status"]="keep"; result["span_marks"][0]["rationale"]="The sentence restates the preceding claim as a punchline."
        self.assertEqual(VALIDATE.validate(result,path,ROOT/"rules.json"),[])
    def test_validator_ties_reading_codes_and_sections_to_current_source(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"x.md"; path.write_text("# T\n\nThe point is straightforward.",encoding="utf-8"); result=MARK.scan(path,ROOT/"rules.json",None,False)
        result["reading_coverage"]["reading_rule_codes"]=[]
        self.assertTrue(any("reading_rule_codes" in x for x in VALIDATE.validate(result,path,ROOT/"rules.json")))
        result=MARK.scan(path,ROOT/"rules.json",None,False); result["reading_coverage"]={"status":"partial","reviewed_sections":["Invented"],"unreviewed_sections":["T"],"reading_rule_codes":["RHT-03","META-04","META-05","META-06","STR-02"]}
        self.assertTrue(any("partition" in x or "overlap" in x for x in VALIDATE.validate(result,path,ROOT/"rules.json")))
        result=MARK.scan(path,ROOT/"rules.json",None,False); result["span_marks"][0]["origin"]="model_reading"; result["span_marks"][0]["codes"]=["LOG-01"]
        self.assertTrue(any("lacks a reading-rule" in x for x in VALIDATE.validate(result,path,ROOT/"rules.json")))
    def test_testbed_hashes_and_manual_labels_are_auditable(self):
        """Audit the testbed record.

        The reviewed documents are third-party articles and are not
        redistributed, so hash verification runs only where the text is present.
        The metadata is always checked: it is the provenance record behind every
        rule's `verification` block, and it must stand on its own.
        """
        manifest=json.loads((ROOT/"testbed"/"manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["documents"],"manifest lists no documents")
        checked=0
        for doc in manifest["documents"]:
            self.assertEqual(64,len(doc["sha256"]),doc["document_id"])
            self.assertIn(doc["role"],{"development_pilot","context_bench"})
            path=ROOT/doc["path"]
            if path.exists():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),doc["sha256"],doc["document_id"])
                checked+=1
        review=json.loads((ROOT/"testbed"/"context-bench-review.json").read_text(encoding="utf-8"))
        ids={d["document_id"] for d in manifest["documents"]}
        self.assertEqual(set(review["labels"]),ids,"labels and manifest disagree on documents")
        for doc_id,labels in review["labels"].items():
            actual=[mid for group in ("feature_present","protected_or_functional","rule_misfire") for mid in labels[group]]
            self.assertEqual(len(actual),len(set(actual)),f"{doc_id}: a mark carries two labels")
        runs=review.get("reviewed_runs")
        if not runs:
            self.assertIn("reviewed_runs_not_distributed",review,
                          "a testbed without run snapshots must say why")
            return
        for doc_id,run_rel in runs.items():
            run=json.loads((ROOT/run_rel).read_text(encoding="utf-8"))
            expected={x["mark_id"] for x in run["span_marks"]}
            labels=review["labels"][doc_id]
            actual={mid for group in ("feature_present","protected_or_functional","rule_misfire") for mid in labels[group]}
            self.assertEqual(actual,expected,f"{doc_id}: labels do not cover the run's marks")


if __name__=="__main__": unittest.main()
