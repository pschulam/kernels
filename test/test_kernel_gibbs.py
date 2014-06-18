from distributions.dbg.models import bb

from microscopes.models.mixture.dp import DPMM
from microscopes.common.dataset import numpy_dataset
from microscopes.kernels.gibbs import gibbs

import itertools as it
import math
import numpy as np
import scipy as sp
import scipy.misc

def canonical(assignments):
    assignments = np.copy(assignments)
    lowest = 0
    for i in xrange(assignments.shape[0]):
        if assignments[i] < lowest:
            continue
        if assignments[i] == lowest:
            lowest += 1
            continue
        temp = assignments[i]
        idxs = assignments == temp
        assignments[assignments == lowest] = temp
        assignments[idxs] = lowest
        lowest += 1
    return assignments

def permutation_iter(n):
    seen = set()
    for C in it.product(range(n), repeat=n):
        C = tuple(canonical(np.array(C)))
        if C in seen:
            continue
        seen.add(C)
        yield C

def cluster(Y, assignments):
    labels = {}
    for assign in assignments:
        if assign not in labels:
            labels[assign] = len(labels)
    clusters = [[] for _ in xrange(len(labels))]
    for ci, yi in zip(assignments, Y):
        clusters[labels[ci]].append(yi)
    return tuple(np.array(c) for c in clusters)

def kl(a, b):
    return np.sum([p*np.log(p/q) for p, q in zip(a, b)])

def test_simple():
    N = 4
    D = 5
    dpmm = DPMM(N, {'alpha':2.0}, [bb]*D, [{'alpha':1.0, 'beta':1.0}]*D)
    actual_dpmm = DPMM(N, {'alpha':2.0}, [bb]*D, [{'alpha':1.0, 'beta':1.0}]*D)
    Y_clustered = dpmm.sample(N)
    Y = np.vstack(Y_clustered)
    actual_dpmm.fill(Y_clustered)

    idmap = { C : i for i, C in enumerate(permutation_iter(N)) }

    # brute force the posterior of the actual model
    def posterior(assignments):
        actual_dpmm.reset()
        actual_dpmm.fill(cluster(Y, assignments))
        return actual_dpmm.score_joint()
    actual_scores = np.array(map(posterior, permutation_iter(N)))
    actual_scores -= sp.misc.logsumexp(actual_scores)
    actual_scores = np.exp(actual_scores)

    dataset = numpy_dataset(Y)
    dpmm.bootstrap(dataset.data(shuffle=False))

    # burnin
    gibbs(dpmm, dataset, 10000)

    # now grab 1000 samples, every 10 iters
    smoothing = 1e-5
    gibbs_scores = np.zeros(len(actual_scores)) + smoothing
    for _ in xrange(1000):
        gibbs(dpmm, dataset, 10)
        gibbs_scores[idmap[tuple(canonical(dpmm.assignments()))]] += 1
    gibbs_scores /= gibbs_scores.sum()

    assert kl(actual_scores, gibbs_scores) <= 0.1