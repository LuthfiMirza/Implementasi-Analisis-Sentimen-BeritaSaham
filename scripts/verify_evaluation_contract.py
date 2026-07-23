#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,sys
from pathlib import Path
VALID_LABELS={'positive','neutral','negative'}
REQUIRED_VERSION_FILES=['official_test_manifest.csv','train_manifest.csv','validation_manifest.csv','split_contract.json','CHECKSUMS.sha256','README.md','access_log.jsonl']
REQUIRED_CANDIDATE_FILES=['test_manifest.csv','train_manifest.csv','validation_manifest.csv','split_contract.json','CHECKSUMS.sha256','README.md']

def sha256_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
def rows(path):
    with Path(path).open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def fail(msg): print('ERROR: '+msg); return 1
def checksum_map(dir):
    p=Path(dir)/'CHECKSUMS.sha256'
    if not p.exists(): return {}
    out={}
    for line in p.read_text().splitlines():
        if line.strip():
            digest,name=line.split(None,1); out[name.strip()]=digest
    return out
def verify_dir(dir, official=False, allow=False):
    d=Path(dir); req=REQUIRED_VERSION_FILES if official else REQUIRED_CANDIDATE_FILES
    if official and not allow: return fail('official test access requires --allow-official-test')
    if not d.is_dir(): return fail(f'directory not found: {d}')
    for f in req:
        if not (d/f).exists(): return fail(f'missing required file: {f}')
    sums=checksum_map(d)
    for f,digest in sums.items():
        if sha256_file(d/f)!=digest: return fail(f'checksum mismatch: {f}')
    contract=json.loads((d/'split_contract.json').read_text())
    manifests={'train':rows(d/'train_manifest.csv'),'validation':rows(d/'validation_manifest.csv'),'test':rows(d/('official_test_manifest.csv' if official else 'test_manifest.csv'))}
    all_ids=[]; all_mids=[]; group_split={}; text_split={}
    for split,rs in manifests.items():
        expected=contract.get(f'{split}_rows')
        if expected is not None and len(rs)!=expected: return fail(f'{split} row count mismatch')
        for r in rs:
            if r.get('label') not in VALID_LABELS: return fail('invalid label found')
            if not r.get('manual_label_id'): return fail('missing manual_label_id')
            all_ids.append((split,r.get('article_id'))); all_mids.append((split,r.get('manual_label_id')))
            gid=r.get('group_id'); text=r.get('exact_text_sha256')
            if gid and gid in group_split and group_split[gid]!=split: return fail('group crossing found')
            group_split[gid]=split
            if text and text in text_split and text_split[text]!=split: return fail('exact text overlap found')
            text_split[text]=split
            if official and split=='test' and r.get('conflict_status')!='none': return fail('unresolved conflict in official test')
    ids=[i for _,i in all_ids]; mids=[i for _,i in all_mids]
    if len(ids)!=len(set(ids)): return fail('article_id overlap found')
    if len(mids)!=len(set(mids)): return fail('manual_label_id overlap found')
    if contract.get('primary_metric')!='macro_f1': return fail('primary metric must be macro_f1')
    print(json.dumps({'status':'ok','directory':str(d),'official':official,'read_only':True},indent=2)); return 0
def verify_legacy(args):
    manifest=Path(args.manifest); checksum=Path(args.checksum)
    if not manifest.exists(): return fail(f'manifest not found: {manifest}')
    if not checksum.exists(): return fail(f'checksum not found: {checksum}')
    expected=checksum.read_text().split()[0]; actual=sha256_file(manifest)
    if actual!=expected: return fail(f'checksum mismatch: expected {expected}, got {actual}')
    rs=rows(manifest)
    if len(rs)!=args.expected_rows: return fail(f'row count mismatch: expected {args.expected_rows}, got {len(rs)}')
    ids=[r.get('article_id','') for r in rs]
    if len(ids)!=len(set(ids)): return fail('duplicate article_id found')
    labels=[r.get('label','') for r in rs]
    invalid=sorted(set(labels)-VALID_LABELS)
    if invalid: return fail('invalid labels found: '+', '.join(invalid))
    expected_dist=json.loads(args.expected_distribution); actual={l:labels.count(l) for l in sorted(VALID_LABELS)}
    if actual!=expected_dist: return fail(f'label distribution mismatch: expected {expected_dist}, got {actual}')
    for other in args.no_overlap_manifest:
        overlap=set(ids)&{r.get('article_id','') for r in rows(other)}
        if overlap: return fail('article_id overlap with '+other+': '+', '.join(sorted(overlap)[:20]))
    print(json.dumps({'status':'ok','manifest':str(manifest),'sha256':actual,'rows':len(rs),'label_distribution':actual,'read_only':True},indent=2)); return 0
def main():
    p=argparse.ArgumentParser(); p.add_argument('--version'); p.add_argument('--candidate'); p.add_argument('--allow-official-test',action='store_true')
    p.add_argument('--manifest',default='data/evaluation/candidate_test_manifest.csv'); p.add_argument('--checksum',default='data/evaluation/candidate_test_manifest.sha256'); p.add_argument('--expected-rows',type=int,default=148); p.add_argument('--expected-distribution',default='{"negative": 15, "neutral": 87, "positive": 46}'); p.add_argument('--no-overlap-manifest',action='append',default=[])
    args=p.parse_args()
    if args.version: return verify_dir(Path('data/evaluation')/args.version, True, args.allow_official_test)
    if args.candidate: return verify_dir(Path('data/evaluation/candidates')/args.candidate, False, False)
    return verify_legacy(args)
if __name__=='__main__': raise SystemExit(main())
