import numpy as np
import pandas as pd
import pytest
from src.incorporate_enrichment import calendar_features,validate_history

def test_calendar_future_coverage_and_leap_year():
    frame=calendar_features()
    assert not frame.month.duplicated().any()
    assert frame.month.iloc[-1]=="2027-12-01"
    assert frame.set_index("month").loc["2024-02-01","days_in_month"]==29
    assert np.allclose(frame.month_sin**2+frame.month_cos**2,1)

def test_supplemental_duplicates_and_invalid_activity():
    row=pd.DataFrame({"app_id":[1],"month":["2026-09-01"],"avg_players":[5.],"peak_players":[10.]})
    validate_history(row)
    with pytest.raises(ValueError,match="duplicate"):
        validate_history(pd.concat([row,row]))
    row.loc[0,"avg_players"]=11
    with pytest.raises(ValueError,match="Invalid"):
        validate_history(row)
