"""Daily scouting: discovers and adapts, but never automatically runs new providers.

A separate explicitly allowlisted synthetic probe can promote ONE source to
technical verification. Unrecognized provider code is NEVER imported.
"""
import argparse
import json
from pathlib import Path
from .scout import scan
from .probe import probe_one,ProbeError

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--catalog',default='registry/providers.json')
    a.add_argument('--max-candidates',type=int,default=9)
    a.add_argument('--probe-one',action='store_true',help='One synthetic test of an allowlisted compatible candidate')
    a.add_argument('--output',default='proof')
    args=a.parse_args()
    if not 1<=args.max_candidates<=15:raise SystemExit('MAX_CANDIDATES_OUT_OF_RANGE')
    data=scan(max_candidates=args.max_candidates)
    if args.probe_one:
        for candidate in data['candidates']:
            if candidate.get('status')!='schema_matched':continue
            try:
                report=probe_one(candidate,Path(args.output))
                candidate['probe']='verified_synthetic_video_only'
                candidate['probe_technical_result']=report
                # Never marks production-ready based on only one trial.
                break
            except ProbeError as e:
                candidate['probe']='skipped_or_failed'
                candidate['probe_reason']=str(e)[:120]
                continue
    out=Path(args.catalog);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    stats={}
    for c in data['candidates']:stats[c['status']]=stats.get(c['status'],0)+1
    print(json.dumps({'catalog':str(out),'count':len(data['candidates']),'states':stats,'probe_enabled':args.probe_one},ensure_ascii=False))

if __name__=='__main__':main()