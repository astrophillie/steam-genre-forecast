import pandas as pd
import pytest
from src.refresh_readiness import build_catalog

def inputs():
    games=pd.DataFrame({"app_id":[1,2],"name":["Game","Held"],"eligible":[1,0]})
    players=pd.DataFrame({"app_id":[1,2],"month":["2025-09-01"]*2,"avg_players":[10.,0.]})
    audit=pd.DataFrame({"app_id":[1,3],"name":["Game","Probe"],"status":["ok","http_error"],"last_month":["2026-09-01",None],"has_latest_complete_month":[True,False],"overlap_months":[1,0],"overlap_mismatches":[0,0]})
    return games,players,audit

def test_scope_and_missing_values_remain_separate():
    catalog=build_catalog(*inputs()).set_index("app_id")
    assert catalog.loc[1,"refresh_scope"] == "Existing eligible cohort"
    assert catalog.loc[2,"status"] == "not_requested"
    assert catalog.loc[2,"baseline_latest_activity"] == 0
    assert catalog.loc[3,"refresh_scope"] == "Catalog expansion probe"
    assert pd.isna(catalog.loc[3,"baseline_latest_activity"])
    assert pd.isna(catalog.loc[3,"eligible"])

def test_duplicate_pilot_ids_rejected():
    games,players,audit=inputs()
    with pytest.raises(ValueError,match="Duplicate app identifiers"):
        build_catalog(games,players,pd.concat([audit,audit]))

def test_duplicate_months_rejected():
    games,players,audit=inputs()
    with pytest.raises(ValueError,match="Duplicate app/month"):
        build_catalog(games,pd.concat([players,players]),audit)
