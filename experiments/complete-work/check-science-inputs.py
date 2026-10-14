"""Independent input facts for reviewers; not a reference analysis solution."""
import csv
import json
from collections import Counter
from pathlib import Path


def facts(root):
    result = {}
    for filename in ['penguins.csv', 'penguins_raw.csv']:
        with (Path(root) / filename).open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        result[filename] = {'rows': len(rows), 'columns': list(rows[0]),
                            'missing': {k: sum(row[k] in ('', 'NA') for row in rows) for k in rows[0]}}
        keys = ['species', 'island', 'sex', 'year'] if filename == 'penguins.csv' else ['Species', 'Island', 'Sex', 'studyName']
        result[filename]['groups'] = {key: dict(sorted(Counter(row[key] for row in rows).items())) for key in keys}
        species, island = keys[:2]
        result[filename]['species_island'] = dict(sorted(Counter(f'{row[species]} | {row[island]}' for row in rows).items()))
        if filename == 'penguins_raw.csv':
            ids = Counter(row['Individual ID'] for row in rows)
            result[filename]['repeated_individual_ids'] = {key: count for key, count in ids.items() if count > 1}
            composite = Counter((row['studyName'], row['Species'], row['Island'], row['Individual ID']) for row in rows)
            result[filename]['duplicate_composite_keys'] = sum(count - 1 for count in composite.values())
    return result


if __name__ == '__main__':
    import sys
    print(json.dumps(facts(sys.argv[1]), indent=2))
