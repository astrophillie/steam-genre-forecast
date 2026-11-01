import numpy as np
import pandas as pd
import pytest
from src.tune_candidates import inner_origins,select_parameters,GRID

def test_inner_validation_finishes_before_outer_cutoff():
    train=pd.Series(100+np.arange(96,dtype=float),index=pd.date_range("2012-07-01",periods=96,freq="MS"))
    origins=inner_origins(train)
    assert len(origins)==2
    for origin in origins:
        assert len(train.loc[:origin])>=36
        assert origin+pd.DateOffset(months=27)<=train.index[-1]

def test_parameter_choice_minimises_only_inner_scores():
    train=pd.Series(100+np.arange(96,dtype=float)+np.sin(np.arange(96)),index=pd.date_range("2012-07-01",periods=96,freq="MS"))
    params,search,chosen=select_parameters(train,"Reference")
    assert len(search)==8
    assert params==GRID[chosen]
    assert chosen==search.groupby("candidate").mae.mean().idxmin()
    assert search.last_target_month.le(train.index[-1]).all()

def test_insufficient_nested_history_rejected():
    train=pd.Series(np.ones(40),index=pd.date_range("2018-01-01",periods=40,freq="MS"))
    with pytest.raises(ValueError,match="Insufficient"):
        inner_origins(train)
