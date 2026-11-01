import pandas as pd
import pytest
from src.project_2027 import annual_summary

def test_annual_mean_and_rank_use_all_twelve_months():
    dates=pd.date_range("2027-01-01",periods=12,freq="MS").strftime("%Y-%m-%d")
    frame=pd.DataFrame({"policy":["Example"]*24,"category":["A"]*12+["B"]*12,"month":list(dates)*2,"prediction":[100]*12+[200]*12})
    result=annual_summary(frame).set_index("category")
    assert result.loc["B","rank"]==1 and result.loc["A","projected_mean_activity"]==100
    with pytest.raises(ValueError,match="12"):
        annual_summary(frame.iloc[1:])
    with pytest.raises(ValueError,match="Repeated"):
        annual_summary(pd.concat([frame,frame.iloc[:1]]))
