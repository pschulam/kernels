import numpy as np
from distributions.dbg.random import sample_discrete_log

def gibbs_hp(m, hparams):
    """
    hparams: dict mapping feature id to the following dict:
        {
            'hpdf' : <a function taking values of `hgrid' below and returning scores>,
            'hgrid': <a grid of hyperparameters to try>
        }
    """
    # XXX: this can be done in parallel
    for fi, hparam in hparams.iteritems():
        hpdf, hgrid = hparam['hpdf'], hparam['hgrid']
        scores = np.zeros(len(hgrid))
        for i, hp in enumerate(hgrid):
            m.set_feature_hp_raw(fi, hp)
            scores[i] = hpdf(hp) + m.score_data(fi)
        m.set_feature_hp_raw(fi, hgrid[sample_discrete_log(scores)])

###
# NOTE: while gibbs_assign(), gibbs_assign_nonconj(), and gibbs_assign_fixed()
# are all very similar and could be merged into one function with various input
# parameters governing the behavior, such an approach is confusing and error
# prone!
#
# Since the underlying gibbs kernel is quite concise, we trade off slight code
# duplication for increased clarity, less bugs, and slightly better performance
# (since extra runtime checks add up)
###

def gibbs_assign_fixed(m, it):
    for ei, yi in it:
        gid = m.remove_entity_from_group(ei, yi)
        idmap, scores = m.score_value(yi)
        gid = idmap[sample_discrete_log(scores)]
        m.add_entity_to_group(gid, ei, yi)

def gibbs_assign(m, it):
    empty_gids = list(m.empty_groups())
    if not len(empty_gids):
        empty_gid = m.create_group()
    else:
        empty_gid = empty_gids[0]
        for gid in empty_gids[1:]:
            m.delete_group(gid)
    assert len(m.empty_groups()) == 1
    for ei, yi in it:
        gid = m.remove_entity_from_group(ei, yi)
        if not m.nentities_in_group(gid):
            # we have already ensured exactly one empty group (before removing
            # the current entity).  now that we have two empty groups, we must
            # remove one of them
            m.delete_group(gid)
        idmap, scores = m.score_value(yi)
        gid = idmap[sample_discrete_log(scores)]
        m.add_entity_to_group(gid, ei, yi)
        if gid == empty_gid:
            # we used up our one empty group, so we must create another
            empty_gid = m.create_group()

def gibbs_assign_nonconj(m, it, nonempty):
    assert nonempty >= 1
    # we maintain the invariant that at the *beginning* of each iteration, there
    # are no empty groups
    empty_groups = list(m.empty_groups())
    for gid in empty_groups:
        m.delete_group(gid)
    for ei, yi in it:
        assert not len(m.empty_groups())
        gid = m.remove_entity_from_group(ei, yi)
        if not m.nentities_in_group(gid):
            m.delete_group(gid)
        empty_groups = [m.create_group() for _ in xrange(nonempty)]
        idmap, scores = m.score_value(yi)
        gid = idmap[sample_discrete_log(scores)]
        m.add_entity_to_group(gid, ei, yi)
        for egid in empty_groups:
            if egid == gid:
                continue
            m.delete_group(egid)
