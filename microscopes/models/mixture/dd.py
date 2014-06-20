import numpy as np

from microscopes.common.groups import FixedNGroupManager
from distributions.dbg.random import sample_discrete_log, sample_discrete
from distributions.dbg.special import gammaln

class DirichletFixed(object):

    def __init__(self, n, k, clusterhp, featuretypes, featurehps):
        self._groups = FixedNGroupManager(n)
        self._alpha = clusterhp['alpha'] # dirichlet distribution alpha
        self._featuretypes = featuretypes
        def init_and_load_shared(arg):
            typ, hp = arg
            shared = typ.Shared()
            shared.load(hp)
            return shared
        self._featureshares = map(init_and_load_shared, zip(self._featuretypes, featurehps))
        for i in xrange(k):
            gid = self._create_group()
            assert gid == i
        assert self.ngroups() == k

    def get_cluster_hp_raw(self):
        return {'alpha':self._alpha}

    def set_cluster_hp_raw(self, raw):
        self._alpha = clusterhp['alpha']

    def get_feature_hp_raw(self, fi):
        return self._featureshares[fi].dump()

    def set_feature_hp_raw(self, fi, raw):
        self._featureshares[fi].load(raw)

    def get_feature_hp_shared(self, fi):
        return self._featureshares[fi]

    def get_suff_stats(self, fi):
        return [(gid, gdata[fi]) for gid, (_, gdata) in self._groups.groupiter()]

    def assignments(self):
        return self._groups.assignments()

    def empty_groups(self):
        return self._groups.empty_groups()

    def ngroups(self):
        return self._groups.ngroups()

    def nentities(self):
        return self._groups.nentities()

    def nentities_in_group(self, gid):
        return self._groups.nentities_in_group(gid)

    def is_group_empty(self, gid):
        return not self._groups.nentities_in_group(gid)

    def groups(self):
        return range(self.ngroups())

    def _create_group(self):
        """
        returns gid
        """
        def init_group(arg):
            typ, shared = arg
            g = typ.Group()
            g.init(shared)
            return g
        gdata = map(init_group, zip(self._featuretypes, self._featureshares))
        return self._groups.create_group(gdata)

    def add_entity_to_group(self, gid, eid, y):
        gdata = self._groups.add_entity_to_group(gid, eid)
        for (g, s), yi in zip(zip(gdata, self._featureshares), y):
            g.add_value(s, yi)

    def remove_entity_from_group(self, eid, y):
        """
        returns gid
        """
        gid, gdata = self._groups.remove_entity_from_group(eid)
        for (g, s), yi in zip(zip(gdata, self._featureshares), y):
            g.remove_value(s, yi)
        return gid

    def score_value(self, y):
        """
        returns idmap, scores
        """
        k = self.ngroups()
        scores = np.zeros(k, dtype=np.float)
        idmap = np.arange(k)
        n = self.nentities()
        for idx, (gid, (cnt, gdata)) in enumerate(self._groups.groupiter()):
            lg_term1 = np.log((cnt + self._alpha/k)/(n-1-self._alpha)) # CRP
            lg_term2 = sum(g.score_value(s, yi) for (g, s), yi in zip(zip(gdata, self._featureshares), y))
            scores[idx] = lg_term1 + lg_term2
            idmap[idx] = gid
        return idmap, scores

    def score_data(self, fi=None):
        """
        computes log p(Y_{fi} | C) = \sum{k=1}^{K} log p(Y_{fi}^{k}),
        where Y_{fi}^{k} is the slice of data along the fi-th feature belonging to the
        k-th cluster

        if fi is None, scores the data along every feature
        """
        score = 0.0
        for _, (_, gdata) in self._groups.groupiter():
            if fi is not None:
                score += gdata[fi].score_data(self._featureshares[fi])
            else:
                score += sum(g.score_data(s) for g, s in zip(gdata, self._featureshares))
        return score

    def score_assignment(self):
        """
        computes log p(C)
        Eq. 8 of http://homepage.tudelft.nl/19j49/Publications_files/TR_1.pdf
        """
        n = self.nentities()
        k = self.ngroups()
        alpha_over_K = self._alpha/k
        acc = 0.0
        for _, (cnt, _) in self._groups.groupiter():
            acc += gammaln(cnt + alpha_over_K)
        return gammaln(self._alpha) - gammaln(n + self._alpha) + acc - k*gammaln(alpha_over_K)

    def score_joint(self):
        """
        computes log p(C, Y) = log p(C) + log p(Y|C)
        """
        return self.score_assignment() + self.score_data(fi=None)

    def reset(self):
        """
        reset to the same condition as upon construction
        """
        k = self.ngroups()
        self._groups = FixedNGroupManager(self._groups.nentities())
        for i in xrange(k):
            gid = self._create_group()
            assert gid == i

    def bootstrap(self, it):
        """
        bootstraps assignments
        """
        assert self._groups.no_entities_assigned()
        for ei, yi in it:
            idmap, scores = self.score_value(yi)
            gid = idmap[sample_discrete_log(scores)]
            self.add_entity_to_group(gid, ei, yi)
        assert self._groups.all_entities_assigned()

    def fill(self, clusters):
        """
        form a cluster assignment and sufficient statistics out of an given
        clustering of N points.

        useful to bootstrap a model as the ground truth model
        """
        assert self._groups.no_entities_assigned()
        assert len(clusters) <= self.ngroups(), 'given more clusters than model can support'
        counts = [c.shape[0] for c in clusters]
        cumcounts = np.cumsum(counts)
        for cid, data in enumerate(clusters):
            off = cumcounts[cid-1] if cid else 0
            for ei, yi in enumerate(data):
                self.add_entity_to_group(cid, off + ei, yi)
        assert self._groups.all_entities_assigned()

    def sample(self, n):
        """
        generate n iid samples from the underlying generative process described
        by this DirichletFixed model.

        does not affect the state of the model, and only depends on the prior
        parameters

        returns a tuple of
            (
                k-length tuple of observations, one for each cluster,
                k-length tuple of cluster samplers
            )
        """
        def mk_dtype_desc(typ, shared):
            if hasattr(shared, 'dimension') and shared.dimension() > 1:
                return ('', typ.Value, (shared.dimension(),))
            return ('', typ.Value)
        ydtype = [mk_dtype_desc(typ, shared) for typ, shared in zip(self._featuretypes, self._featureshares)]
        def init_sampler(arg):
            typ, s = arg
            samp = typ.Sampler()
            samp.init(s)
            return samp
        def new_cluster_params():
            return tuple(map(init_sampler, zip(self._featuretypes, self._featureshares)))
        def new_sample(params):
            data = tuple(samp.eval(s) for samp, s in zip(params, self._featureshares))
            return data
        k = self.ngroups()
        cluster_params = [new_cluster_params() for _ in xrange(k)]
        pis = np.random.dirichlet(self._alpha/k*np.ones(k))
        samples = [[] for _ in xrange(k)]
        for _ in xrange(n):
            choice = sample_discrete(pis)
            params = cluster_params[choice]
            samples[choice].append(new_sample(params))
        return tuple(np.array(ys, dtype=ydtype) for ys in samples), tuple(cluster_params)
