from microscopes.kernels.slice import slice_hp
from common import make_one_feature_bb_mm, bb_hyperprior_pdf

import numpy as np
from nose.plugins.attrib import attr

@attr('slow')
def test_kernel_slice_hp():
    # XXX: this test is a bit flaky
    Nk = 1000
    K = 100
    dpmm = make_one_feature_bb_mm(Nk, K, 1.0, 1.0)
    dpmm.set_feature_hp_raw(0, {'alpha':1.5,'beta':1.5}) # don't start w/ the right answer

    hparams = {0:{'hpdf':bb_hyperprior_pdf,'hw':{'alpha':1.,'beta':1.}}}
    def posterior(niters):
        for _ in xrange(niters):
            slice_hp(dpmm, hparams)
            hp = dpmm.get_feature_hp_raw(0)
            yield np.array([hp['alpha'], hp['beta']])
    values = list(posterior(10000))[10:]
    avg = sum(values) / len(values)

    print avg
    #print values
    assert np.linalg.norm( np.array([1., 1.]) - avg ) <= 0.15