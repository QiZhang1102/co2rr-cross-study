#!/usr/bin/env python3
"""Retrieve the public pinned workbook, verify content, never overwrite changes."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
COMMIT='b9c7f420fed238cca9e1e3ac3e4010b09bd68ce9'
FILENAME='CO2RRMolecularModification-HXR-20230323.xlsx'
EXPECTED_SHA256='6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793'
URL=f'https://raw.githubusercontent.com/Wang-Group/Cu-CO2RR_modifiers/{COMMIT}/{FILENAME}'

def download(root=ROOT):
    path=Path(root)/'data/raw'/FILENAME
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        data=path.read_bytes()
        status='verified_existing_cache'
    else:
        request=urllib.request.Request(URL,headers={'User-Agent':'CO2RR-cross-study-reproducibility/1.0'})
        with urllib.request.urlopen(request,timeout=60) as response:
            data=response.read()
        status='downloaded'
    sha=hashlib.sha256(data).hexdigest()
    if sha != EXPECTED_SHA256:
        raise ValueError(f'Raw workbook hash mismatch: {sha}; no changed file will be overwritten')
    if not path.exists():
        path.write_bytes(data)
    evidence={'url':URL,'repository_commit':COMMIT,'sha256':sha,'bytes':len(data),
              'status':status,'license_declaration':'Apache-2.0 repository license; underlying measurement rights not independently determined',
              'original_acquisition_date_utc':'2026-11-09','workbook':'Sheet1'}
    (Path(root)/'data/raw/source_manifest.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();download(args.root)
