import numpy as np
import pandas as pd
import pytest
from src.refresh_gate import validate_import,assess_refresh

def rows():
    return pd.DataFrame({"app_id":[1,1,1,2,2,2],"month":["2025-09-01","2025-10-01","2025-11-01"]*2,"avg_players":[10.,11.,12.,20.,21.,22.],"source_url":"https://example.org/history"})

@pytest.mark.parametrize("issue",["duplicate","partial","nan","negative","provenance","boolean","empty"])
def test_invalid_refresh_rejected(issue):
    frame=rows()
    if issue=="duplicate":frame=pd.concat([frame,frame.iloc[:1]])
    elif issue=="partial":frame["month"]="2026-10-01"
    elif issue=="nan":frame["avg_players"]=np.nan
    elif issue=="negative":frame["avg_players"]=-1.
    elif issue=="provenance":frame["source_url"]=""
    elif issue=="boolean":frame["app_id"]=True
    else:frame=frame.iloc[:0]
    with pytest.raises(ValueError):validate_import(frame,"2026-10-26")

def test_zero_activity_is_valid_and_missing_is_not_zero():
    frame=rows();frame["avg_players"]=0.
    assert validate_import(frame,"2026-10-26").avg_players.eq(0).all()

def test_refresh_gate_rejects_gaps_mismatches_and_outside_cohort():
    frame=validate_import(rows(),"2026-10-26")
    old=pd.DataFrame({"app_id":[1,2],"month":"2025-09-01","avg_players":[10.,20.]})
    games=pd.DataFrame({"app_id":[1,2,3],"eligible":[1,1,0]})
    labels=pd.DataFrame({"app_id":[1,2],"category":"Action"})
    summary,_,_,_=assess_refresh(frame,old,games,labels,"2025-11-01")
    assert summary["promotion_ready"]
    missing=frame.loc[~(frame.app_id.eq(2)&frame.month.eq("2025-10-01"))]
    summary,_,_,_=assess_refresh(missing,old,games,labels,"2025-11-01")
    assert not summary["promotion_ready"] and summary["missing_refresh_app_months"]==1
    frame.loc[0,"avg_players"]=99
    summary,_,_,_=assess_refresh(frame,old,games,labels,"2025-11-01")
    assert not summary["promotion_ready"] and summary["overlap_mismatches"]==1
    held=rows().iloc[:1].copy();held["app_id"]=3
    summary,_,_,_=assess_refresh(pd.concat([frame,held]),old,games,labels,"2025-11-01")
    assert summary["outside_cohort_rows"]==1
