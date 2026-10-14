import importlib.util
from types import SimpleNamespace
import unittest

@unittest.skipUnless(importlib.util.find_spec('torch'),'Optional tensor contract; no GPU or download')
class SelectedLossTests(unittest.TestCase):
    def test_selected_projection_matches_dense_shifted_loss_and_gradients(self):
        import torch
        from torch.nn import functional as F
        from coevo.loss import selected_causal_loss
        torch.manual_seed(17)
        logits=torch.randn(1,9,13,requires_grad=True)
        labels=torch.tensor([[-100,-100,3,8,-100,2,-100,-100,7]])
        dense=F.cross_entropy(logits[:,:-1].reshape(-1,13),labels[:,1:].reshape(-1),ignore_index=-100)
        gradient=torch.autograd.grad(dense,logits)[0]
        class Model:
            def __call__(self,**kwargs):return SimpleNamespace(logits=logits[:,kwargs['logits_to_keep'],:])
        sparse=selected_causal_loss(Model(),torch.zeros_like(labels),labels)
        sparse_gradient=torch.autograd.grad(sparse,logits)[0]
        torch.testing.assert_close(sparse,dense)
        torch.testing.assert_close(sparse_gradient,gradient)
