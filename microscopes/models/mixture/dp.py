import numpy as np

from microscopes.common.groups import FixedNGroupManager
from distributions.dbg.random import sample_discrete_log, sample_discrete

class DPMM(object):

    def __init__(self, n, clusterhp, featuretypes, featurehps):
        self._groups = FixedNGroupManager(n)
        self._alpha = clusterhp['alpha'] # CRP alpha
        self._featuretypes = featuretypes
        def init_and_load_shared(arg):
            typ, hp = arg
            shared = typ.Shared()
            shared.load(hp)
            return shared
        self._featureshares = map(init_and_load_shared, zip(self._featuretypes, featurehps))

    def set_cluster_hp(self, clusterhp):
        self._alpha = clusterhp['alpha']

    def set_feature_hp(self, fi, featurehp):
        self._featureshares[fi].load(featurehp)

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

    def create_group(self):
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

    def delete_group(self, gid):
        self._groups.delete_group(gid)

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
        scores = np.zeros(self._groups.ngroups(), dtype=np.float)
        idmap = [0]*self._groups.ngroups()
        n = self._groups.nentities()
        for idx, (gid, (cnt, gdata)) in enumerate(self._groups.groupiter()):
            lg_term1 = np.log((self._alpha if not cnt else cnt)/(n-1-self._alpha)) # CRP
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

    def bootstrap(self, it):
        """
        bootstraps assignments
        """
        assert not self.ngroups()
        assert self._groups.no_entities_assigned()

        ei0, y0 = next(it)
        gid0 = self.create_group()
        self.add_entity_to_group(gid0, ei0, y0)
        empty_gid = self.create_group()
        for ei, yi in it:
            idmap, scores = self.score_value(yi)
            gid = idmap[sample_discrete_log(scores)]
            self.add_entity_to_group(gid, ei, yi)
            if gid == empty_gid:
                empty_gid = self.create_group()

        assert self._groups.all_entities_assigned()

    def sample(self, n):
        """
        generate n iid samples from the underlying generative process described by this DPMM.

        does not affect the state of the DPMM, and only depends on the prior parameters of the
        DPMM

        returns a k-length tuple of observations, where k is the # of sampled
        clusters from the CRP
        """
        cluster_counts = np.array([1], dtype=np.int)
        def init_sampler(arg):
            typ, s = arg
            samp = typ.Sampler()
            samp.init(s)
            return samp
        def new_cluster_params():
            return map(init_sampler, zip(self._featuretypes, self._featureshares))
        def new_sample(params):
            return [samp.eval(s) for samp, s in zip(cluster_params[0], self._featureshares)]
        cluster_params = [new_cluster_params()]
        samples = [[new_sample(cluster_params[-1])]]
        for _ in xrange(1, n):
            dist = np.append(cluster_counts, self._alpha).astype(np.float, copy=False)
            choice = sample_discrete(dist)
            if choice == len(cluster_counts):
                cluster_counts = np.append(cluster_counts, 1)
                cluster_params.append(new_cluster_params())
                samples.append([new_sample(cluster_params[-1])])
            else:
                cluster_counts[choice] += 1
                params = cluster_params[choice]
                samples[choice].append(new_sample(params))
        return tuple(np.array(ys) for ys in samples)
