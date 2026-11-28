"""Stage authoritative binary sources outside Git. Unreviewed sensor hashes are candidates only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen, Request
from benchmark_kernel import verify_file, GLORIA_SHA, GLORIA_BYTES
SOURCES = {
 'gloria': ('GLORIA-2022.zip','https://download.pangaea.de/dataset/948492/files/GLORIA-2022.zip'),
 's2': ('sentinel-2-spectral-response-functions-v5.xlsx','https://sentiwiki.copernicus.eu/__attachments/a_ad595cc9fa0018a4e9eb28e1e234124a751149b5933b0b8b1f6b80612eaab586/sentinel-2-spectral-response-functions-v5.xlsx?cb=0735bcc384fde7424ba8d58a19c4a9dd'),
 's3': ('S3A_OL_SRF_20160713_mean_rsr.nc4','https://sentiwiki.copernicus.eu/__attachments/a_1376b0c7651794dd4dc96b9372d6cd9142231ae04d8578f9bfc884eba902cbc3/S3A_OL_SRF_20160713_mean_rsr.nc4?cb=fe25bf278fcd53f15c2be812ba223de4'),
}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--download',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    records={}; missing=[]
    for key,(name,url) in SOURCES.items():
        f=a.out/name
        if not f.exists() and a.download:
            tmp=f.with_suffix(f.suffix+'.partial')
            with urlopen(Request(url,headers={'User-Agent':'hydrospectral-lab research staging'}),timeout=90) as r,tmp.open('wb') as w:
                while chunk:=r.read(1024*1024):w.write(chunk)
            tmp.replace(f)
        if not f.exists():missing.append(key);continue
        with f.open('rb') as s:
            head=s.read(8);s.seek(0);sha=hashlib.file_digest(s,'sha256').hexdigest()
        if key in ('gloria','s2') and head[:2]!=b'PK':raise ValueError(f'Expected ZIP/XLSX magic: {f}')
        if key=='s3' and not (head.startswith(b'\x89HDF\r\n\x1a\n') or head.startswith(b'CDF')):raise ValueError('Expected NetCDF signature')
        if key=='gloria':verify_file(f,GLORIA_SHA,GLORIA_BYTES)
        records[key]={'filename':name,'source_url':url,'bytes':f.stat().st_size,'sha256':sha,'status':'matched_frozen_digest' if key=='gloria' else 'candidate_digest_needs_review'}
    (a.out/'candidate_input_inventory.json').write_text(json.dumps({'records':records,'missing':missing},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'records':records,'missing':missing},indent=2))
    return 2 if missing else 0
if __name__=='__main__':raise SystemExit(main())
