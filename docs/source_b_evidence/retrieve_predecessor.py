"""Retrieve verified candidate-B predecessor SI; never use it as admitted model data.

Standard library only. ACS figshare metadata licenses the SI CC BY-NC 4.0.
Raw data are deliberately omitted from the distributed project; this script
reacquires identical bytes and verifies the recorded SHA256.
Usage: python docs/source_b_evidence/retrieve_predecessor.py --out work/source_b
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('work/source_b'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = json.loads((Path(__file__).parent / 'download_manifest.json').read_text())
    for record in records:
        dest = args.out / record['file']
        if not dest.exists():
            with urlopen(record['url'], timeout=60) as response:
                content = response.read()
            assert len(content) == record['bytes'], record['file']
            assert hashlib.sha256(content).hexdigest() == record['sha256'], record['file']
            dest.write_bytes(content)
        else:
            assert hashlib.sha256(dest.read_bytes()).hexdigest() == record['sha256'], record['file']
        print(record['file'], record['sha256'], 'verified; excluded from primary analysis')


if __name__ == '__main__':
    main()
