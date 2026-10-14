"""Checks that complete-work evidence cannot be replaced by student assertions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coevo.complete_work import verify, SOURCES
from coevo.project import hashes
from coevo.runtime import write_json


class CompleteWorkChecks(unittest.TestCase):
    def test_successful_science_process_leaves_scientific_review_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / 'run'
            ws = out / 'workspace'
            (ws / 'data').mkdir(parents=True)
            for name in ('penguins.csv', 'penguins_raw.csv'):
                (ws / 'data' / name).write_text('a\n1\n')
            initial = hashes(ws)
            (ws / 'analysis.py').write_text('print("claimed success")\n')
            write_json(out / 'task.json', dict(case='science', source_cluster='palmerpenguins', source_revision=SOURCES['science'][1], initial_files=initial))
            def execute(*args, **kwargs):
                # A process which creates an output is still not a scientific verdict.
                if args[2] == ['python', 'analysis.py']:
                    (args[0] / 'results').mkdir()
                    (args[0] / 'results' / 'table.csv').write_text('claim\n42\n')
                return {'exit_code': 0}
            with patch('coevo.complete_work.subprocess.check_output', side_effect=[SOURCES['science'][1], '']), patch('coevo.complete_work.execute', side_effect=execute):
                result = verify(out, root / 'sources', root / 'environment')
            self.assertTrue(result['reproduction_passed'])
            self.assertFalse(result['report_present'])
            self.assertIsNone(result['task_success'])
            self.assertTrue(result['review_pending'])
            self.assertFalse((ws / 'results').exists())

    def test_modified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / 'task.json', dict(case='software', source_revision=SOURCES['software'][1]))
            with patch('coevo.complete_work.subprocess.check_output', side_effect=[SOURCES['software'][1], ' M frontmatter/__init__.py']):
                with self.assertRaisesRegex(ValueError, 'clean'):
                    verify(root, root, root)
            self.assertFalse((root / 'review').exists())


if __name__ == '__main__':
    unittest.main()
