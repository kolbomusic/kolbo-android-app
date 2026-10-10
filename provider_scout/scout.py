"""Bounded, documented Hugging Face Space discovery and schema introspection.

Never runs model code or uploads user data. Public metadata is untrusted.
"""
from __future__ import annotations
import datetime as dt
import re
from itertools import islice
from urllib.parse import urlparse
from dataclasses import asdict
import requests
from .adapter import recognize

SPACE_ID=re.compile(r'^[A-Za-z0-9][\w.-]{0,63}/[A-Za-z0-9][\w.-]{0,95}$')
SUBDOMAIN=re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,125}[a-z0-9])?$')
TERMS=('image to video','video generation','LTX video')
PILOT_IDS=('chopperblu/ltx-2-5-demo',)
ALLOWED_LICENSES=frozenset({'apache-2.0','mit','bsd-3-clause','cc-by-4.0'})
MAX_INFO_BYTES=256_000


def safe_space_id(raw):
    return isinstance(raw,str) and bool(SPACE_ID.fullmatch(raw)) and '..' not in raw


def safe_space_host(subdomain):
    if (not isinstance(subdomain,str) or not SUBDOMAIN.fullmatch(subdomain)
            or '--' in subdomain or '-' not in subdomain):
        raise ValueError('BAD_SPACE_SUBDOMAIN')
    return 'https://'+subdomain+'.hf.space'


def _get_limited_json(session, url):
    # No redirects; only a Space host of the constrained form is supplied by scout().
    r=session.get(url,timeout=(5,11),allow_redirects=False,stream=True,headers={'Accept':'application/json'})
    try:
        if r.status_code!=200:raise ValueError('REMOTE_METADATA_HTTP_'+str(r.status_code))
        content=bytearray()
        for chunk in r.iter_content(chunk_size=16_384):
            content.extend(chunk)
            if len(content)>MAX_INFO_BYTES:raise ValueError('REMOTE_METADATA_TOO_BIG')
        return __import__('json').loads(content)
    finally:r.close()


def _space_license(info):
    metadata=getattr(info,'card_data',None) or {}
    if isinstance(metadata,dict):return str(metadata.get('license') or '').lower()
    return str(getattr(metadata,'license',None) or '').lower()


def scan(max_candidates=9, terms=TERMS, client=None, session=None):
    from huggingface_hub import HfApi
    api=client or HfApi(token=False)
    web=session or requests.Session()
    seen=set(); candidates=[]; now=dt.datetime.now(dt.timezone.utc).isoformat()
    ids=[]
    # Prioritize previously validated public model demos before broad search results.
    for seed in PILOT_IDS:
        if safe_space_id(seed) and seed not in seen and len(ids)<max_candidates:
            ids.append(seed);seen.add(seed)
    for term in terms:
        try:
            for item in islice(api.search_spaces(term,sdk='gradio',include_non_running=False,token=False),max_candidates):
                repo_id=getattr(item,'id',None)
                if repo_id and any(word in repo_id.lower() for word in ('uncensored','eros','nsfw','porn')):
                    continue
                if safe_space_id(repo_id) and repo_id not in seen:
                    ids.append(repo_id);seen.add(repo_id)
                if len(ids)>=max_candidates:break
        except Exception:pass
        if len(ids)>=max_candidates:break
    for repo_id in ids:
        record={'id':repo_id,'discovered_at':now,'source':'huggingface_spaces_official',
                'status':'discovered','capabilities':[],'probe':'not_run','pricing_verified':False,
                'terms_verified':False,'production_eligible':False}
        try:
            info=api.space_info(repo_id,token=False)
            if getattr(info,'private',False) or getattr(info,'disabled',False):raise ValueError('PRIVATE_OR_DISABLED')
            license_id=_space_license(info)
            record['license_declared']=license_id or None
            record['automated_public_demo_probe_candidate']=license_id in ALLOWED_LICENSES
            # HF authoritative Space subdomain, never free-form URL from a remote model.
            domain=getattr(info,'subdomain',None)
            if not domain:raise ValueError('SUBDOMAIN_NOT_PUBLISHED')
            base=safe_space_host(str(domain).lower())
            record['space_url']='https://huggingface.co/spaces/'+repo_id
            record['api_host']=base
            metadata=_get_limited_json(web,base+'/gradio_api/info')
            plans=recognize(metadata)
            record['status']='schema_matched' if plans else 'schema_not_compatible'
            record['capabilities']=[p.public() for p in plans[:3]]
        except Exception as e:
            record['status']='introspection_unavailable'
            record['reason']=type(e).__name__+':'+str(e)[:90]
        candidates.append(record)
    return {'version':'3.2.0','discovered_at':now,'verification_level':'metadata_only',
            'never_claims_generation_from_metadata':True,
            'candidates':candidates}