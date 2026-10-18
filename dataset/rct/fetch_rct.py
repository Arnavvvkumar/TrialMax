"""Download only the three fixed public R survival snapshots; never downloads at import time."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.responder_truth import TRIALS


def fetch(directory=Path(__file__).resolve().parent):
    directory.mkdir(parents=True,exist_ok=True)
    with httpx.Client(timeout=30,follow_redirects=True) as client:
        for key,trial in TRIALS.items():
            url = f'https://vincentarelbundock.github.io/Rdatasets/csv/survival/{key}.csv'
            response = client.get(url); response.raise_for_status()
            data = response.content
            rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
            print(key,'schema:',list(rows[0]),'rows:',len(rows))
            (directory/f'{key}.csv').write_bytes(data)
            (directory/f'{key}.provenance.json').write_text(json.dumps(dict(url=url,
              downloaded_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(data).hexdigest(),
              citation=trial['citation'],publication_url=trial['publication_url'],credit='R survival package; Rdatasets mirror',
              documentation_url=f'https://vincentarelbundock.github.io/Rdatasets/doc/survival/{key}.html'),indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__': fetch()
