import unittest
from unittest.mock import patch
from coevo.learning_decisions import validate

class DecisionsTests(unittest.TestCase):
    def test_model_cannot_promote_source_scope_or_unverified_target(self):
        packet={'source_cluster_id':'L-source','context':{'operation':'csv'}}
        candidate={'candidate_id':'verified','source_cluster_id':'L-source'}
        proposal={'source_cluster_id':'L-source','memory_kind':'skill','body':'Check actual CSV fields',
            'conditions':{'operation':'csv'},'training_candidate_ids':['verified'],'reason':'actual correction'}
        with patch('coevo.learning_decisions.admit',side_effect=lambda x:x) as gate:
            self.assertEqual(validate(proposal,packet,[candidate])['selected'],[candidate])
            self.assertEqual(gate.call_count,1)
        for change in [{'source_cluster_id':'other'},{'memory_kind':'instruction'},
                {'conditions':{'operation':'bash'}},{'training_candidate_ids':['unverified']},
                {'training_candidate_ids':['verified']*5}]:
            with self.assertRaises(ValueError):validate({**proposal,**change},packet,[candidate])
        self.assertEqual(validate({**proposal,'memory_kind':'none','body':'','conditions':{},'training_candidate_ids':[]},packet,[candidate])['selected'],[])
