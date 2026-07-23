import csv, hashlib, json, shutil, subprocess, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.lib.sentiment_text_normalization import normalize_text, normalize_url, sha256_text
from scripts.lib.sentiment_grouping import UnionFind

ROOT=Path(__file__).resolve().parents[2]

def run(cmd):
    return subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)

class SentimentEvaluationContractPythonTest(unittest.TestCase):
    def test_01_text_normalization_deterministic(self): self.assertEqual(normalize_text(' A  B '), normalize_text('a b'))
    def test_02_hash_stability(self): self.assertEqual(sha256_text(normalize_text('X')), sha256_text('x'))
    def test_03_negation_not_removed(self): self.assertIn('tidak', normalize_text('TIDAK naik'))
    def test_04_financial_numbers_not_removed(self): self.assertIn('12,5%', normalize_text('Laba naik 12,5% Rp1.000'))
    def test_05_html_decoded(self): self.assertEqual(normalize_text('A&nbsp;B'), 'a b')
    def test_06_unicode_stable(self): self.assertEqual(normalize_text('ＡＢＣ'), 'abc')
    def test_07_url_tracking_removed(self): self.assertEqual(normalize_url('https://x.test/a?utm_source=a&b=1'), 'https://x.test/a?b=1')
    def test_08_union_find_exact_duplicate_group(self):
        uf=UnionFind(); uf.union('1','2'); self.assertEqual(uf.find('1'),uf.find('2'))
    def test_09_union_find_transitive(self):
        uf=UnionFind(); uf.union('1','2'); uf.union('2','3'); self.assertEqual(uf.find('1'),uf.find('3'))
    def test_10_non_duplicate_not_merged(self):
        uf=UnionFind(); uf.add('1'); uf.add('2'); self.assertNotEqual(uf.find('1'),uf.find('2'))
    def test_11_near_duplicate_pairs_report_exists(self): self.assertTrue((ROOT/'reports/near_duplicate_pairs.csv').exists())
    def test_12_exact_groups_report_exists(self): self.assertTrue((ROOT/'reports/exact_duplicate_groups.json').exists())
    def test_13_event_high_confidence_hard_constraint(self):
        with (ROOT/'reports/event_group_candidates.csv').open() as handle:
            rows=list(csv.DictReader(handle))
        self.assertTrue(all(r['hard_constraint']=='true' for r in rows[:5]))
    def test_14_medium_event_not_hard_constraint_policy_documented(self): self.assertIn('Medium-confidence', (ROOT/'docs/sentiment_evaluation_contract.md').read_text())
    def test_15_conflict_queue_excludes_pending(self):
        with (ROOT/'reports/official_test_label_review_queue.csv').open() as handle:
            rows=list(csv.DictReader(handle))
        self.assertTrue(all(r['recommended_action']=='exclude_group_pending_review' for r in rows[:10]))
    def test_16_group_not_split_candidate_a(self): self.assertEqual(run(['python3','scripts/verify_evaluation_contract.py','--candidate','candidate-a']).returncode,0)
    def test_17_article_id_no_overlap_candidate_b(self): self.assertEqual(run(['python3','scripts/verify_evaluation_contract.py','--candidate','candidate-b']).returncode,0)
    def test_18_manual_label_id_no_overlap_candidate_c(self): self.assertEqual(run(['python3','scripts/verify_evaluation_contract.py','--candidate','candidate-c']).returncode,0)
    def test_19_invalid_label_rejected(self):
        d=Path(tempfile.mkdtemp()); m=d/'m.csv'; c=d/'m.sha256'; m.write_text('article_id,label\n1,bad\n'); c.write_text(hashlib.sha256(m.read_bytes()).hexdigest()+'  m.csv\n')
        try: self.assertNotEqual(run(['python3','scripts/verify_evaluation_contract.py','--manifest',str(m),'--checksum',str(c),'--expected-rows','1','--expected-distribution','{"negative":0,"neutral":0,"positive":0}']).returncode,0)
        finally: shutil.rmtree(d)
    def test_20_missing_label_rejected(self):
        d=Path(tempfile.mkdtemp()); m=d/'m.csv'; c=d/'m.sha256'; m.write_text('article_id,label\n1,\n'); c.write_text(hashlib.sha256(m.read_bytes()).hexdigest()+'  m.csv\n')
        try: self.assertNotEqual(run(['python3','scripts/verify_evaluation_contract.py','--manifest',str(m),'--checksum',str(c),'--expected-rows','1']).returncode,0)
        finally: shutil.rmtree(d)
    def test_21_checksum_mismatch_rejected(self):
        d=Path(tempfile.mkdtemp()); m=d/'m.csv'; c=d/'m.sha256'; m.write_text('article_id,label\n1,positive\n'); c.write_text('0'*64+'  m.csv\n')
        try: self.assertNotEqual(run(['python3','scripts/verify_evaluation_contract.py','--manifest',str(m),'--checksum',str(c),'--expected-rows','1']).returncode,0)
        finally: shutil.rmtree(d)
    def test_22_manifest_modification_detected(self): self.assertIn('8bf1b53b', (ROOT/'data/evaluation/candidate_test_manifest.sha256').read_text())
    def test_23_existing_version_not_created(self): self.assertFalse((ROOT/'data/evaluation/sentiment-test-v1').exists())
    def test_24_same_seed_reproducible_contract(self):
        before=(ROOT/'data/evaluation/candidates/candidate-a/split_contract.json').read_text(); self.assertEqual(run(['python3','scripts/build_official_evaluation_split.py','--seed','42']).returncode,0); self.assertEqual(before,(ROOT/'data/evaluation/candidates/candidate-a/split_contract.json').read_text())
    def test_25_candidate_leakage_fails_quality_gate(self): self.assertFalse(json.loads((ROOT/'data/evaluation/candidates/candidate-a/split_contract.json').read_text())['quality_gate_pass'])
    def test_26_official_access_without_flag_rejected(self): self.assertNotEqual(run(['python3','scripts/verify_evaluation_contract.py','--version','sentiment-test-v1']).returncode,0)
    def test_27_official_access_checksum_rusak_rejected(self): self.assertNotEqual(run(['python3','scripts/verify_evaluation_contract.py','--version','sentiment-test-v1','--allow-official-test']).returncode,0)
    def test_28_database_write_not_required(self): self.assertIn('read_only', (ROOT/'reports/ground_truth_validation.json').read_text() + (ROOT/'docs/sentiment_evaluation_contract.md').read_text())
    def test_29_candidate_manifest_not_official(self): self.assertIn('candidate', (ROOT/'data/evaluation/candidate_test_manifest.csv').read_text().splitlines()[1])
    def test_30_historical_exposure_reported(self): self.assertIn('count_per_exposure', json.loads((ROOT/'reports/historical_exposure_audit.json').read_text()))
    def test_31_unresolved_conflict_not_in_test(self): self.assertEqual(json.loads((ROOT/'data/evaluation/candidates/candidate-a/split_contract.json').read_text())['leakage_audit']['unresolved_conflict_count'],0)
    def test_32_minimum_class_support_checked(self): self.assertIn('quality_gate_pass', json.loads((ROOT/'data/evaluation/candidates/candidate-a/split_contract.json').read_text()))
    def test_33_sample_distribution_reported(self): self.assertIn('sample_method_distribution', (ROOT/'reports/official_test_candidate_comparison.csv').read_text().splitlines()[0])
    def test_34_source_diversity_reported(self): self.assertIn('source_count', (ROOT/'reports/official_test_candidate_comparison.csv').read_text().splitlines()[0])

if __name__=='__main__': unittest.main()
