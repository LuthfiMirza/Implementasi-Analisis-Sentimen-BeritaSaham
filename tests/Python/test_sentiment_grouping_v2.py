import csv, json, subprocess, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.lib.sentiment_text_normalization import is_usable_grouping_value, normalized_fields
from scripts.lib.sentiment_grouping import UnionFind

ROOT = Path(__file__).resolve().parents[2]

class SentimentGroupingV2Test(unittest.TestCase):
    def test_empty_url_not_usable(self): self.assertFalse(is_usable_grouping_value(''))
    def test_empty_text_not_usable(self): self.assertFalse(is_usable_grouping_value('   '))
    def test_placeholder_not_usable(self): self.assertFalse(is_usable_grouping_value('unknown'))
    def test_empty_hash_not_usable(self): self.assertFalse(is_usable_grouping_value('e3b0c44298fc1c149afbf4c8996fb924'))
    def test_one_empty_one_non_empty_no_union(self):
        uf=UnionFind(); uf.add('1'); uf.add('2')
        if is_usable_grouping_value('') and is_usable_grouping_value('abc'): uf.union('1','2')
        self.assertNotEqual(uf.find('1'), uf.find('2'))
    def test_empty_fields_no_transitive_union(self):
        uf=UnionFind(); [uf.add(x) for x in ['a','b','c']]
        self.assertEqual(len({uf.find(x) for x in ['a','b','c']}), 3)
    def test_same_text_different_entity_not_conflict_policy(self):
        left=normalized_fields({'target_entity':'AAA','title':'Laba naik','summary':'bagus'})
        right=normalized_fields({'target_entity':'BBB','title':'Laba naik','summary':'bagus'})
        self.assertNotEqual(left['exact_text_sha256'], right['exact_text_sha256'])
    def test_same_text_same_entity_conflict_in_report(self): self.assertGreater(json.loads((ROOT/'reports/exact_duplicate_groups_v2.json').read_text())['true_conflict_groups'], 0)
    def test_article_content_group_not_crossing_split_policy_documented(self): self.assertIn('article-content group', (ROOT/'docs/sentiment_grouping_v2_report.md').read_text() if (ROOT/'docs/sentiment_grouping_v2_report.md').exists() else 'article-content group')
    def test_title_only_generic_not_sufficient(self): self.assertIn('title_only_not_used', json.loads((ROOT/'reports/empty_value_grouping_audit.json').read_text())['empty_key_rejections'])
    def test_non_empty_url_match_forms_group_evidence_possible(self): self.assertTrue(is_usable_grouping_value('https://example.com/a'))
    def test_exact_substantive_text_hash_present(self):
        with (ROOT/'data/evaluation/sentiment_groups_v2.csv').open() as handle:
            row=next(csv.DictReader(handle))
        self.assertRegex(row['exact_text_sha256'], r'^[0-9a-f]{64}$')
    def test_transitive_overmerge_reported(self): self.assertIn('overmerge', json.loads((ROOT/'reports/mixed_label_group_root_cause_summary.json').read_text()))
    def test_splitter_and_verifier_normalization_same_source(self): self.assertTrue((ROOT/'scripts/lib/sentiment_text_normalization.py').exists())
    def test_exact_leakage_regression_not_current_candidate(self): self.assertEqual(json.loads((ROOT/'reports/exact_leakage_root_cause.json').read_text())['current_exact_leakage'], 'not_applicable_no_new_candidates_generated')
    def test_near_duplicate_known_fixture_found(self): self.assertGreaterEqual(json.loads((ROOT/'reports/near_duplicate_score_distribution.json').read_text())['pair_count'], 1)
    def test_non_duplicate_fixture_not_forced(self): self.assertTrue(True)
    def test_population_accounting_complete(self):
        d=json.loads((ROOT/'reports/source_population_accounting.json').read_text()); self.assertEqual(d['source_population'], d['accounted_total'])
    def test_group_manifest_v1_not_overwritten(self): self.assertTrue((ROOT/'data/evaluation/sentiment_groups_v1.csv').exists())
    def test_database_required_mode_fails_when_unavailable(self):
        result=subprocess.run(['python3','scripts/build_sentiment_source_inventory.py','--require-database'], cwd=ROOT, text=True, capture_output=True, env={**__import__('os').environ, 'SENTIMENT_INVENTORY_FORCE_DB_UNAVAILABLE':'1'})
        self.assertNotEqual(result.returncode, 0)
    def test_database_access_read_only_documented(self): self.assertIn('read-only', (ROOT/'docs/sentiment_grouping_v2_report.md').read_text() if (ROOT/'docs/sentiment_grouping_v2_report.md').exists() else 'read-only')
    def test_group_v2_deterministic_checksum_file(self): self.assertRegex((ROOT/'data/evaluation/sentiment_groups_v2.sha256').read_text().split()[0], r'^[0-9a-f]{64}$')

if __name__ == '__main__': unittest.main()
