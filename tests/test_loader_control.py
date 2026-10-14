import json
import tempfile
import unittest
from pathlib import Path
from coevo.loader_control import zero_delta
try:
    import torch
    from safetensors.torch import save_file,load_file
except ImportError:
    torch=None


@unittest.skipUnless(torch is not None,'Optional tensor control; no GPU or download')
class LoaderControlTests(unittest.TestCase):
    def test_zero_delta_preserves_source_A_and_base_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            (source/'adapter_config.json').write_text(json.dumps({'peft_type':'LORA','bias':'none'}))
            A=torch.tensor([[1.,2.],[3.,4.]]);B=torch.tensor([[.5,.3],[.4,.8]])
            save_file({'layer.lora_A.weight':A,'layer.lora_B.weight':B},source/'adapter_model.safetensors')
            original=(source/'adapter_model.safetensors').read_bytes();zero_delta(source,root/'control')
            state=load_file(root/'control/adapter_model.safetensors')
            self.assertTrue(torch.equal(state['layer.lora_A.weight'],A))
            self.assertTrue(torch.equal(state['layer.lora_B.weight']@A,torch.zeros_like(B)))
            x=torch.tensor([[5.,6.]]);base=x@torch.eye(2)
            self.assertTrue(torch.equal(base+x@state['layer.lora_A.weight'].T@state['layer.lora_B.weight'].T,base))
            self.assertEqual((source/'adapter_model.safetensors').read_bytes(),original)
            self.assertEqual(json.loads((root/'control/zero-delta.json').read_text())['optimizer_steps'],0)

    def test_extra_saved_parameters_do_not_claim_zero_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            (source/'adapter_config.json').write_text(json.dumps({'peft_type':'LORA','bias':'none'}))
            save_file({'layer.lora_A.weight':torch.ones(2,2),'layer.lora_B.weight':torch.ones(2,2),
                'other.weight':torch.ones(2,2)},source/'adapter_model.safetensors')
            with self.assertRaises(ValueError):zero_delta(source,root/'control')
