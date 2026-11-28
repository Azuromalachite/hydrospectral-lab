import numpy as np
import pytest
from sklearn.model_selection import GroupKFold
from benchmark_kernel import *

def test_digest(tmp_path):
    p=tmp_path/'data';p.write_bytes(b'abc');sha=hashlib.sha256(b'abc').hexdigest()
    assert verify_file(p,sha,3)==sha
    with pytest.raises(ValueError): verify_file(p,'0'*64,3)
    with pytest.raises(ValueError): verify_file(p,sha,4)

def test_srf_support_and_tiny_tail():
    w=np.array([399.,400.,401.,500.,600.,799.,800.,801.])
    good=np.array([0.,0.,0.,1.,0.,0.,0.,0.]); tiny=good.copy();tiny[0]=1e-12
    edge=good.copy();edge[1]=.001
    accept,audit=srf_support_audit(w,{'good':good,'tiny':tiny,'edge':edge})
    assert set(accept)=={'good'} and len(audit)==3
    with pytest.raises(ValueError): srf_support_audit(w,{'bad':-good})

def test_group_weighting_and_sign():
    y=np.zeros(10);g=np.array(['big']*9+['small']);p=np.array([0.]*9+[2.])
    assert equal_group_rmse(y,p,g)==pytest.approx(np.sqrt(2))
    d=paired_delta(y,y,p,g);assert d['delta_candidate_minus_reference']<0 and d['ci_high']<=0
    assert mdsa_percent(np.zeros(3),np.ones(3)*np.log10(2))==pytest.approx(100)
    assert mdsa_percent(np.zeros(3),-np.ones(3)*np.log10(2))==pytest.approx(100)

def test_leakage():
    g=['a','a','b','b']
    with pytest.raises(ValueError): check_split([0,2],[1,3],g)
    with pytest.raises(ValueError): check_split([0,0],[2,3],g)
    with pytest.raises(ValueError): check_split([0,1],[1,2],g,False)
    check_split([0,1],[2,3],g)

def test_nested_and_planted_overlap():
    rng=np.random.default_rng(3);g=np.repeat([f'g{i}' for i in range(10)],6);X=rng.normal(size=(60,3));y=2*X[:,0]+.2*X[:,1]
    folds=list(GroupKFold(5).split(X,y,g))
    p,log=nested_group_predict(X,y,g,folds,inner_n=3,grid_override={'ridge__alpha':[.0001,1.]})
    assert equal_group_rmse(y,p,g)<.01 and len(log)==5
    with pytest.raises(ValueError): nested_group_predict(X,y,g,folds[:-1],inner_n=3,grid_override={'ridge__alpha':[.001]})
    tr,te=folds[0]; contaminated=tr.copy();contaminated[0]=te[0]
    with pytest.raises(ValueError): nested_group_predict(X,y,g,[(contaminated,te)],inner_n=3,grid_override={'ridge__alpha':[.001]})
