#!/usr/bin/env python3
"""Read-only NVIDIA GPU donor eligibility check. No network, installation, jobs or uploads."""
from __future__ import annotations
import argparse,json,shutil,subprocess
from pathlib import Path
RECOMMENDED_VRAM_MIB=32768
RECOMMENDED_DISK_BYTES=100*1024**3

def check(query_gpu,docker_probe,disk_probe):
    try:raw=query_gpu()
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):raw=''
    devices=[]
    for line in raw.splitlines():
        try:
            name,memory=line.rsplit(',',1)
            mib=int(memory.strip())
            if name.strip() and mib>=128:
                devices.append({'name':name.strip(),'vram_mib':mib,
                    'recommended_for_ltx25':mib>=RECOMMENDED_VRAM_MIB})
        except (TypeError,ValueError):pass
    try:free=max(0,int(disk_probe()))
    except (OSError,ValueError):free=0
    try:docker=bool(docker_probe())
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):docker=False
    gpu=any(x['recommended_for_ltx25'] for x in devices)
    disk=free>=RECOMMENDED_DISK_BYTES
    warnings=[]
    if not gpu:warnings.append('No confirmed NVIDIA GPU with 32GiB+ VRAM')
    if not disk:warnings.append('Less than 100GiB free disk')
    if not docker:warnings.append('Docker daemon unavailable')
    return {'gpu_count':len(devices),'gpus':devices,'recommended_gpu_detected':gpu,
        'disk_free_gib':round(free/1024**3,1),'recommended_disk_available':disk,
        'docker_ready':docker,'eligible_for_operator_review':gpu and disk and docker,
        'worker_registered':False,'gpu_generation_proven':False,
        'user_media_transferred':False,'payments_started':False,'warnings':warnings}

def main():
    parser=argparse.ArgumentParser(description='Local read-only GPU compatibility check')
    parser.add_argument('--output',help='Optional new local JSON report file (never uploaded)')
    args=parser.parse_args()
    def gpu_query():
        r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total',
            '--format=csv,noheader,nounits'],capture_output=True,text=True,
            timeout=10,check=True)
        return r.stdout
    def docker_probe():
        return subprocess.run(['docker','info','--format','{{.ServerVersion}}'],
            capture_output=True,timeout=10,check=True).returncode==0
    result=check(gpu_query,docker_probe,lambda:shutil.disk_usage(Path.cwd()).free)
    serialized=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    print(serialized)
    if args.output:
        file=Path(args.output)
        if file.exists() or file.is_symlink():raise SystemExit('Refusing to overwrite')
        file.write_text(serialized,encoding='utf-8')
    return 0 if result['eligible_for_operator_review'] else 2
if __name__=='__main__':raise SystemExit(main())
