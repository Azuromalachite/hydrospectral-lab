"""Candidate benchmark kernel; synthetic tests only, not a confirmatory runner.
All choices in proposed protocol clarification require approval before real runs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
from sklearn.base import clone
from sklearn.model_selection import GroupKFold, ParameterGrid
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor

SEED = 2026
GLORIA_SHA = 'f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14'
GLORIA_BYTES = 58956647
GRID = np.arange(400., 801.)

def verify_file(path, sha, size=None):
    p = Path(path)
    if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Expected a pinned lowercase SHA-256')
    if size is not None and p.stat().st_size != size:
        raise ValueError(f'Size mismatch: {p}')
    with p.open('rb') as f:
        got = hashlib.file_digest(f, 'sha256').hexdigest()
    if got != sha:
        raise ValueError(f'Digest mismatch: {p}')
    return got

def srf_support_audit(wavelengths, responses, lo=400., hi=800.):
    """Literal sampled support; conservative rejection at nonzero table endpoints.
    No clipping/renormalizing tails. All exclusions are returned with reasons.
    A sampled curve does not prove the physical response outside the file is zero.
    """
    w = np.asarray(wavelengths, float)
    if w.ndim != 1 or len(w)<2 or not np.isfinite(w).all() or not (np.diff(w)>0).all():
        raise ValueError('Invalid wavelength grid')
    accepted, audit = {}, []
    for name, value in responses.items():
        r = np.asarray(value, float)
        if r.shape != w.shape or not np.isfinite(r).all() or (r<0).any() or not (r>0).any():
            raise ValueError(f'Invalid SRF: {name}')
        support = w[r>0]
        # For piecewise linear interpolation include neighboring zero endpoints.
        idx = np.flatnonzero(r>0)
        left = w[max(0, idx[0]-1)]; right = w[min(len(w)-1, idx[-1]+1)]
        reason = 'eligible'
        if r[0]>0 or r[-1]>0:
            reason = 'unbounded_table_endpoint'
        elif left<lo or right>hi:
            reason = 'outside_window'
        else:
            accepted[name] = r
        audit.append(dict(band=name, sampled_min_nm=float(support.min()),sampled_max_nm=float(support.max()), interpolation_min_nm=float(left),interpolation_max_nm=float(right),status=reason))
    if not accepted:
        raise ValueError('No eligible bands; inspect source and support policy')
    return accepted, audit

def _groups(g):
    g=np.asarray(g,object)
    if g.ndim!=1 or any(x is None or not isinstance(x,str) or not x.strip() for x in g):
        raise ValueError('Missing or invalid group labels')
    return g

def group_mse(y,p,g):
    y,p=np.asarray(y,float),np.asarray(p,float); g=_groups(g)
    if y.ndim!=1 or y.shape!=p.shape or y.shape!=g.shape or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError('Unpaired or nonfinite scores')
    return np.array([np.mean((y[g==k]-p[g==k])**2) for k in sorted(set(g))])

def equal_group_rmse(y,p,g):
    return float(np.sqrt(group_mse(y,p,g).mean()))

def paired_delta(y,candidate,reference,g,n_bootstrap=2000,seed=SEED):
    """Candidate minus reference: negative favors candidate. Resample whole groups."""
    a,b=group_mse(y,candidate,g),group_mse(y,reference,g)
    if len(a)<2: raise ValueError('Need >=2 groups')
    ix=np.random.default_rng(seed).integers(0,len(a),size=(n_bootstrap,len(a)))
    d=np.sqrt(a[ix].mean(1))-np.sqrt(b[ix].mean(1))
    return {'delta_candidate_minus_reference':float(np.sqrt(a.mean())-np.sqrt(b.mean())), 'ci_low':float(np.quantile(d,.025)), 'ci_high':float(np.quantile(d,.975)), 'n_groups':len(a)}

def mdsa_percent(y_log,p_log):
    """Median symmetric accuracy = 100*(exp(median(abs(log ratio)))-1)."""
    y,p=np.asarray(y_log,float),np.asarray(p_log,float)
    if y.shape!=p.shape or y.ndim!=1 or not np.isfinite(y).all() or not np.isfinite(p).all(): raise ValueError('Invalid paired log scores')
    return float(100*np.expm1(np.log(10)*np.median(np.abs(y-p))))

def check_split(tr,te,g,require_disjoint=True):
    tr,te=np.asarray(tr),np.asarray(te); g=_groups(g)
    if tr.ndim!=1 or te.ndim!=1 or not len(tr) or not len(te) or tr.dtype.kind not in 'iu' or te.dtype.kind not in 'iu': raise ValueError('Invalid indices')
    if min(tr.min(),te.min())<0 or max(tr.max(),te.max())>=len(g): raise ValueError('Index outside cohort')
    if len(set(tr))!=len(tr) or len(set(te))!=len(te) or np.intersect1d(tr,te).size: raise ValueError('Row overlap or duplicate')
    if require_disjoint and set(g[tr])&set(g[te]): raise ValueError('Group leakage')

def model_spec(family):
    if family=='ridge': return make_pipeline(StandardScaler(),Ridge()), {'ridge__alpha':np.logspace(-4,4,17)}
    if family=='hgb': return HistGradientBoostingRegressor(max_iter=300,random_state=SEED,early_stopping=False), {'max_depth':[3,6],'learning_rate':[.03,.1],'min_samples_leaf':[10,30],'l2_regularization':[0.,1.]}
    raise ValueError('Unknown family')

def nested_group_predict(X,y,groups,outer_splits,family='ridge',inner_n=5,grid_override=None):
    """Only for group-disjoint outer CV; temporal/random need separately frozen rules.
    Candidate tie-break is ParameterGrid order. Scaling lives in fitted pipeline.
    Equal-group RMSE over inner OOF predictions selects parameters, not held-out results.
    grid_override is for synthetic tests only, not a scientific run.
    """
    X,y=np.asarray(X,float),np.asarray(y,float); groups=_groups(groups)
    if X.ndim!=2 or y.ndim!=1 or len(X)!=len(y) or len(y)!=len(groups) or not np.isfinite(X).all() or not np.isfinite(y).all(): raise ValueError('Invalid features or labels')
    base,grid=model_spec(family); grid=grid if grid_override is None else grid_override
    oof=np.full(len(y),np.nan); folds=[]; seen=np.zeros(len(y),int)
    for fold,(tr,te) in enumerate(outer_splits):
        tr,te=np.asarray(tr),np.asarray(te); check_split(tr,te,groups)
        if np.any(seen[te]): raise ValueError('Repeated held-out row')
        seen[te]+=1
        local=groups[tr]; inner=list(GroupKFold(inner_n).split(X[tr],y[tr],local))
        best=None
        for params in ParameterGrid(grid):
            inner_pred=np.full(len(tr),np.nan)
            for a,b in inner:
                check_split(a,b,local)
                model=clone(base).set_params(**params).fit(X[tr[a]],y[tr[a]])
                inner_pred[b]=model.predict(X[tr[b]])
            score=equal_group_rmse(y[tr],inner_pred,local)
            if best is None or score<best[0]: best=(score,params)
        model=clone(base).set_params(**best[1]).fit(X[tr],y[tr])
        oof[te]=model.predict(X[te]); folds.append({'fold':fold,'params':best[1],'inner_rmse':best[0],'train_n':len(tr),'test_n':len(te)})
    if not np.all(seen==1) or not np.isfinite(oof).all(): raise ValueError('Incomplete OOF predictions')
    return oof,folds
