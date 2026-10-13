"""Student-written tests cannot substitute for independently checked task behavior."""
import tempfile
import unittest
import shutil
from pathlib import Path

from coevo.project import prepare, verify
from test_project_tools import ENVIRONMENT

SOURCE = Path('/mnt/e/CoEvo/upstream/task-candidates/frostming--marko')


@unittest.skipUnless(SOURCE.exists() and (ENVIRONMENT / 'bin/python').exists(), 'Fixed task source and environment required')
class ProjectCheckerTests(unittest.TestCase):
    def test_symlinked_package_is_rejected_before_host_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            prepare(out, SOURCE, ENVIRONMENT)
            package = out / 'workspace/marko'
            shutil.rmtree(package)
            package.symlink_to('/etc', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                verify(out, SOURCE, ENVIRONMENT)
            self.assertFalse((out / 'verification-workspace').exists())
    def test_passing_submitted_test_does_not_make_missing_feature_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            prepare(out, SOURCE, ENVIRONMENT)
            (out / 'workspace/tests/test_submitted.py').write_text('def test_claim():\n    assert True\n')
            result = verify(out, SOURCE, ENVIRONMENT)
            self.assertEqual(result['upstream_regression']['exit_code'], 0)
            self.assertEqual(result['submitted_tests']['exit_code'], 0)
            self.assertNotEqual(result['requested_behavior']['exit_code'], 0)
            self.assertFalse(result['passed'])
