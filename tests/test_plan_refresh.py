import pandas as pd
import pytest
from src.plan_refresh import make_queue

def test_queue_is_complete_deterministic_and_preserves_missing():
    data=pd.DataFrame({"app_id":[3,2,1,4],"refresh_scope":["Existing eligible cohort"]*3+["Held out under existing rule"],"baseline_latest_activity":[None,10.,10.,99.]})
    queue=make_queue(data,2)
    assert queue.app_id.tolist()==[1,2,3]
    assert queue.batch_id.tolist()==[1,1,2]
    assert pd.isna(queue.iloc[-1].baseline_latest_activity)
    assert queue.collection_state.eq("pending_access_method").all()

def test_invalid_batch_size():
    with pytest.raises(ValueError,match="positive"):
        make_queue(pd.DataFrame(),0)
