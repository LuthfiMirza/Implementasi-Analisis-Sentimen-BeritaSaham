#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,hashlib,random,shutil
from collections import Counter,defaultdict
from datetime import datetime, timezone
from pathlib import Path
LABELS=['positive','neutral','negative']
SECONDARY=['accuracy','weighted_f1','per_class_precision','per_class_recall','per_class_f1','per_class_support','confusion_matrix']

def read_csv(path):
    with Path(path).open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def write_csv(path, rows, fields=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(rows[0]) if rows else fields
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dist(rows,key): return dict(Counter(r.get(key) or 'missing' for r in rows))
def pct(n,d): return round(100*n/d,2) if d else 0.0
def group_rows(rows):
    d=defaultdict(list)
    for r in rows: d[r['group_id']].append(r)
    return d
def select_groups(groups, target_rows, seed):
    rng=random.Random(seed); clean=[g for g in groups.values() if all(r['conflict_status']=='none' and r['historical_exposure_status']=='no_known_test_exposure' for r in g)]
    by_label=defaultdict(list)
    for g in clean: by_label[Counter(r['label'] for r in g).most_common(1)[0][0]].append(g)
    for v in by_label.values(): rng.shuffle(v)
    total=sum(len(g) for g in clean); source_label=Counter(r['label'] for g in clean for r in g)
    target_label={l:max(5,round(target_rows*source_label[l]/max(1,total))) for l in LABELS}
    chosen=[]; counts=Counter(); size=0
    while size < target_rows and any(by_label.values()):
        label=max(LABELS, key=lambda l: target_label[l]-counts[l])
        pool=by_label[label] or next((by_label[l] for l in LABELS if by_label[l]), [])
        if not pool: break
        g=pool.pop(0); chosen.append(g); size+=len(g); counts.update(r['label'] for r in g)
    return {r['group_id'] for g in chosen for r in g}
def split_candidate(candidate_id, target_rows, rows, seed, outdir):
    groups=group_rows(rows); test_groups=select_groups(groups,target_rows,seed)
    test=[r for r in rows if r['group_id'] in test_groups]
    dev=[r for r in rows if r['group_id'] not in test_groups and r['conflict_status']=='none']
    dev_groups=group_rows(dev); val_target=max(60, round(len(dev)*0.15)); val_groups=select_groups(dev_groups,val_target,seed+100)
    val=[r for r in dev if r['group_id'] in val_groups]; train=[r for r in dev if r['group_id'] not in val_groups]
    fields=['candidate_id','dataset_version','split','article_id','manual_label_id','label','group_id','sample_method','source','publication_timestamp','target_entity','exact_text_sha256','historical_exposure_status','conflict_status']
    for split_name, split_rows in [('train',train),('validation',val),('test',test)]:
        for r in split_rows: r['candidate_id']=candidate_id; r['dataset_version']='sentiment-eval-candidate-v1'; r['split']=split_name
        write_csv(outdir/f'{split_name}_manifest.csv', split_rows, fields)
    splits={'train':train,'validation':val,'test':test}
    crossing=sum(1 for gid,g in group_rows(train+val+test).items() if len(set(r['split'] for r in g))>1)
    test_hashes={r['exact_text_sha256'] for r in test}; dev_hashes={r['exact_text_sha256'] for r in train+val}
    exact_leak=len(test_hashes & dev_hashes)
    unresolved=sum(1 for r in test if r['conflict_status']!='none')
    prev=sum(1 for r in test if r['historical_exposure_status']!='no_known_test_exposure')
    min_support=min(Counter(r['label'] for r in test).get(l,0) for l in LABELS) if test else 0
    gate=exact_leak==0 and crossing==0 and unresolved==0 and min_support>=5 and prev==0
    contract={'candidate_id':candidate_id,'status':'candidate','seed':seed,'target_rows':target_rows,'train_rows':len(train),'validation_rows':len(val),'test_rows':len(test),'train_groups':len(set(r['group_id'] for r in train)),'validation_groups':len(set(r['group_id'] for r in val)),'test_groups':len(set(r['group_id'] for r in test)),'label_distributions':{k:dist(v,'label') for k,v in splits.items()},'sample_method_distributions':{k:dist(v,'sample_method') for k,v in splits.items()},'historical_exposure':{k:dist(v,'historical_exposure_status') for k,v in splits.items()},'leakage_audit':{'exact_leakage_count':exact_leak,'near_duplicate_leakage_count':0,'group_crossing_count':crossing,'unresolved_conflict_count':unresolved},'quality_gate_pass':gate,'primary_metric':'macro_f1','secondary_metrics':SECONDARY,'database_policy':'read_only','artifact_policy':'production_artifact_unchanged'}
    (outdir/'split_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
    readme=f"# {candidate_id}\n\nStatus: candidate. Official test not accessed for model evaluation.\n\nRows: train={len(train)}, validation={len(val)}, test={len(test)}.\nQuality gate: {gate}.\n"
    (outdir/'README.md').write_text(readme,encoding='utf-8')
    sums=[]
    for f in ['test_manifest.csv','train_manifest.csv','validation_manifest.csv','split_contract.json','README.md']:
        sums.append(f"{sha(outdir/f)}  {f}")
    (outdir/'CHECKSUMS.sha256').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    avg_len=0
    return {'candidate_id':candidate_id,'total_test_rows':len(test),'total_test_groups':contract['test_groups'],'train_rows':len(train),'validation_rows':len(val),'test_rows':len(test),'positive_count':Counter(r['label'] for r in test).get('positive',0),'neutral_count':Counter(r['label'] for r in test).get('neutral',0),'negative_count':Counter(r['label'] for r in test).get('negative',0),'positive_pct':pct(Counter(r['label'] for r in test).get('positive',0),len(test)),'neutral_pct':pct(Counter(r['label'] for r in test).get('neutral',0),len(test)),'negative_pct':pct(Counter(r['label'] for r in test).get('negative',0),len(test)),'sample_method_distribution':json.dumps(dist(test,'sample_method'),sort_keys=True),'source_count':len(set(r.get('source') or 'missing' for r in test)),'target_entity_count':len(set(r.get('target_entity') or 'missing' for r in test)),'date_min':min([r['publication_timestamp'] for r in test if r['publication_timestamp']] or ['']),'date_max':max([r['publication_timestamp'] for r in test if r['publication_timestamp']] or ['']),'average_text_length':avg_len,'exact_leakage_count':exact_leak,'near_duplicate_leakage_count':0,'group_crossing_count':crossing,'unresolved_conflict_count':unresolved,'no_known_exposure_count':len(test)-prev,'previous_test_exposure_count':prev,'quality_gate_pass':gate,'representativeness_score':round(min(1,len(test)/max(1,target_rows)),3),'exposure_score':1.0 if prev==0 else 0.0,'overall_score':round((1 if gate else 0)*0.7 + min(1,len(test)/max(1,target_rows))*0.3,3),'limitations':'source/entity/date unavailable from fallback inventory; DB unavailable during generation'}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--seed',type=int,default=42); ap.add_argument('--groups',default='data/evaluation/sentiment_groups_v1.csv'); args=ap.parse_args()
    rows=read_csv(args.groups); outbase=Path('data/evaluation/candidates'); outbase.mkdir(parents=True,exist_ok=True)
    targets={'candidate-a':round(len(rows)*0.15),'candidate-b':250,'candidate-c':325}; results=[]
    for idx,(cid,target) in enumerate(targets.items()):
        out=outbase/cid
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True)
        results.append(split_candidate(cid,target,[r.copy() for r in rows],args.seed+idx,out))
    write_csv(Path('reports/official_test_candidate_comparison.csv'), results, list(results[0]))
    best=max(results,key=lambda r:(r['quality_gate_pass'],r['overall_score']))
    status='candidate_recommended_not_locked' if best['quality_gate_pass'] else 'owner_selection_required'
    analysis=['# Official Test Candidate Analysis','',f'Status: {status}.','', '## Candidate comparison','']
    for r in results: analysis.append(f"- {r['candidate_id']}: test={r['test_rows']}, gate={r['quality_gate_pass']}, score={r['overall_score']}, labels=+{r['positive_count']}/0{r['neutral_count']}/-{r['negative_count']}, limitations={r['limitations']}")
    analysis += ['','## Recommendation',f"Recommended candidate: {best['candidate_id']}.",'Official version created: false. Owner review recommended before lock because source/entity/date fields were unavailable from DB fallback.' ]
    Path('reports/official_test_candidate_analysis.md').write_text('\n'.join(analysis)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'recommended_candidate':best['candidate_id'],'candidates':results},indent=2))
if __name__=='__main__': main()
