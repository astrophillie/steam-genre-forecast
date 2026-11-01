import numpy as np
import pandas as pd
import pytest
from src.gradient_boosting import feature_row,training_features,recursive_predict,evaluate

def test_training_features_exclude_the_target_and_align_lags():
    series=pd.Series(np.arange(1.,49.),index=pd.date_range("2019-01-01",periods=48,freq="MS"))
    X,y=training_features(series)
    assert X.iloc[0].lag_1==12 and X.iloc[0].lag_12==1 and y[0]==13
    assert X.iloc[0].rolling_mean_3==11
    assert X.iloc[0].rolling_mean_12==6.5

def test_recursion_appends_predictions_instead_of_actuals():
    class Spy:
        def __init__(self):self.seen=[]
        def predict(self,X):
            self.seen.append(X.iloc[0].lag_1)
            return [X.iloc[0].lag_1+1]
    model=Spy()
    predicted,count=recursive_predict(model,np.arange(1.,13.),"2020-01-01",3)
    assert predicted.tolist()==[13,14,15] and model.seen==[12,13,14] and count==0

def test_future_actuals_cannot_change_any_model_predictions():
    dates=pd.date_range("2018-01-01",periods=60,freq="MS")
    data=pd.DataFrame({"category":"Example","month":dates,"avg_players":100+np.arange(60)+4*np.sin(np.arange(60))})
    before,_,_=evaluate(data,[dates[35]],12)
    data.loc[data.month.gt(dates[35]),"avg_players"]*=3
    after,_,_=evaluate(data,[dates[35]],12)
    np.testing.assert_allclose(before.prediction,after.prediction)
    assert before.groupby("model").size().eq(12).all()
    assert len(before.model.unique())==6

def test_nonfinite_predictions_rejected():
    class Bad:
        def predict(self,X):return [np.inf]
    with pytest.raises(ValueError,match="Nonfinite"):
        recursive_predict(Bad(),np.ones(12),"2020-01-01",1)
