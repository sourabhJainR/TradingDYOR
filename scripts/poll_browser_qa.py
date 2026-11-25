#!/usr/bin/env python3
"""Poll GitHub Actions browser-QA run status. Read-only; requires GH_TOKEN."""
import argparse, json, os, time, urllib.request, urllib.error

def request(url, token):
    req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','Authorization':f'Bearer {token}','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(req,timeout=20) as res: return json.loads(res.read())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',default='sourabhJainR/TradingDYOR')
    p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--poll-seconds',type=int,default=15)
    p.add_argument('--timeout-seconds',type=int,default=900)
    args=p.parse_args()
    token=os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
    if not token: raise SystemExit('GH_TOKEN is required')
    url=f'https://api.github.com/repos/{args.repo}/actions/runs/{args.run_id}'
    deadline=time.monotonic()+args.timeout_seconds
    while True:
        run=request(url,token)
        result={'run_id':args.run_id,'repo':args.repo,'head_sha':run.get('head_sha'),
                'expected_sha':args.expected_sha,'status':run.get('status'),
                'conclusion':run.get('conclusion'),'url':run.get('html_url')}
        if result['head_sha']!=args.expected_sha:
            result['state']='mismatch';print(json.dumps(result));return 2
        if run.get('status')=='completed':
            result['state']='passed' if run.get('conclusion')=='success' else 'failed'
            print(json.dumps(result));return 0 if result['state']=='passed' else 1
        if time.monotonic()>=deadline:
            result['state']='timeout';print(json.dumps(result));return 3
        print(json.dumps(result),flush=True);time.sleep(args.poll_seconds)
if __name__=='__main__': raise SystemExit(main())
