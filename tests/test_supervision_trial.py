import json
import tempfile
import unittest
from pathlib import Path
from coevo.supervision_trial import freeze
from coevo.workflows import cases


class TrialTests(unittest.TestCase):
    def test_frozen_shared_panel_preserves_legacy_inputs_and_does_not_overlap_L(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);matrix=root/'matrix';matrix.mkdir()
            config=root/'config.json';config.write_text('{}')
            for arm in ('output-only','full','full-replay'):
                (matrix/(arm+'.jsonl')).write_text('{}\n')
                for design in ('same-exposure','token-matched'):
                    (matrix/(arm+'-'+design+'.json')).write_text('{}')
            freeze(matrix,root/'trial',config)
            manifest=json.loads((root/'trial/manifest.json').read_text())
            panel=json.loads((root/'trial/panel.json').read_text())
            self.assertEqual(len(manifest['arms']),6)
            self.assertTrue(all(Path(a['dataset']).is_file() for a in manifest['arms']))
            self.assertEqual(len(panel),19)
            learning={(f,json.dumps(s['inputs'],sort_keys=True)) for f,i,s in cases(3,17)}
            development={(r['name'].split('-')[1],json.dumps(r['inputs'],sort_keys=True)) for r in panel if r['split']=='D'}
            self.assertFalse(learning&development)
            self.assertTrue(all(r['train_authorized'] is False for r in panel))
            old=[r for r in panel if r['split']=='G']
            self.assertEqual([json.loads(r['expected']['output.json']) for r in old],
                             [{'result':[-3,0,2,7]},{'result':7},{'result':[-1,2,5]}])
            with self.assertRaises(FileExistsError):freeze(matrix,root/'trial',config)
