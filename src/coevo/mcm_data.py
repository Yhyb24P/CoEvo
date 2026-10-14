"""Prepare official MCM inputs and conservative retrospective development views."""
import argparse
import csv
import hashlib
import io
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .runtime import write_json


FILES = ('data_dictionary.csv', 'summerOly_athletes.csv', 'summerOly_hosts.csv',
         'summerOly_medal_counts.csv', 'summerOly_programs.csv')
BASE_URL = 'https://www.contest.comap.org/undergraduate/contests/mcm/contests/2025/problems/'


def decode_csv(data):
    try:
        return data.decode('utf-8-sig'), 'utf-8-sig'
    except UnicodeDecodeError:
        return data.decode('cp1252'), 'cp1252'


def before_year(rows, target):
    """Outcome records from the target edition and later are never exposed."""
    return [r for r in rows if int(r['Year']) < target]


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare(official, out, targets=(2016, 2020, 2024)):
    official, out = Path(official).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Use a new output directory; preserve prior evidence')
    archive = official / '2025_Problem_C_Data.zip'
    pdf = official / '2025_MCM_Problem_C.pdf'
    if not pdf.read_bytes().startswith(b'%PDF-'):
        raise ValueError('Official problem is not a PDF')
    tables, inventory = {}, []
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC validation failed')
        for name in FILES:
            matches = [n for n in z.namelist() if Path(n).name == name]
            if len(matches) != 1:
                raise ValueError(f'Expected exactly one {name}')
            data = z.read(matches[0])
            text, encoding = decode_csv(data)
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            tables[name] = (reader.fieldnames, rows)
            inventory.append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                              'encoding': encoding, 'data_rows': len(rows), 'columns': reader.fieldnames,
                              'year_range': ([min(int(r['Year']) for r in rows), max(int(r['Year']) for r in rows)]
                                             if 'Year' in reader.fieldnames else None)})
            dest = out / 'full-task' / 'data' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    shutil.copy2(pdf, out / 'full-task' / pdf.name)
    views = {}
    for target in targets:
        counts = {}
        for name in ('summerOly_medal_counts.csv', 'summerOly_athletes.csv', 'summerOly_hosts.csv'):
            fields, rows = tables[name]
            visible = before_year(rows, target)
            write_csv(out / 'retrospective' / str(target) / 'input' / name, fields, visible)
            counts[name] = len(visible)
        fields, rows = tables['summerOly_medal_counts.csv']
        truth = [r for r in rows if int(r['Year']) == target]
        if not truth:
            raise ValueError(f'No target outcomes for {target}')
        write_csv(out / 'evaluation-only' / str(target) / 'medal_counts.csv', fields, truth)
        views[str(target)] = {'visible_rows': counts, 'truth_medal_rows': len(truth),
                              'edition_year': target, 'actual_event_year': 2021 if target == 2020 else target}
    result = {'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_cluster_id': 'comap-2025-mcm-c', 'split': 'D', 'H': False,
              'training_executed': False, 'model_executed': False,
              'sources': [{'url': BASE_URL + p.name, 'bytes': p.stat().st_size,
                           'local_download_completed_at_utc': datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                           'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (pdf, archive)],
              'files': inventory, 'retrospective_views': views,
              'visibility_policy': 'Year < target for outcome records and historical hosts; no target/future covariates, PDF, dictionary, or programs in retrospective inputs',
              'limitations': ['Public task and outcomes may be in pretraining; not blind H',
                             'Official files are retrospective exports, not timestamped historical vintages; country names and athlete metadata may be revised',
                             'Programs use current taxonomy/governing names with no historical publication dates; omitted from conservative retrospective inputs',
                             'Evaluation-only directory must not be mounted in an Agent workspace; directory separation alone is not an access sandbox',
                             'Medal table contains medal-winning teams only; zero-medal cohort and country mapping still require explicit evaluation design']}
    write_json(out / 'manifest.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--official', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    prepare(args.official, args.out)


if __name__ == '__main__':
    main()
