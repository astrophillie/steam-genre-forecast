import numpy as np
import pandas as pd
from src.forecast_uncertainty import error_radius

def test_calibration_excludes_unavailable_outcomes():
    frame=pd.DataFrame({"origin":pd.to_datetime(["2018-01-01"]*12+["2019-01-01"]),"month":pd.to_datetime(list(pd.date_range("2019-05-01",periods=12,freq="MS"))+["2021-01-01"]),"lead":list(range(16,28))+[24],"error":[2.]*12+[9999.]})
    radius,n=error_radius(frame,"2020-06-01")
    assert radius==2 and n==12
    frame.loc[12,"error"]=1e10
    assert error_radius(frame,"2020-06-01")== (radius,n)

def test_insufficient_calibration_is_unknown():
    frame=pd.DataFrame({"origin":pd.to_datetime(["2018-01-01"]),"month":pd.to_datetime(["2019-05-01"]),"lead":[16],"error":[2.]})
    radius,n=error_radius(frame,"2020-01-01")
    assert np.isnan(radius) and n==1
