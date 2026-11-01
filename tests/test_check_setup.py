"""Invalid source values must not produce a successful setup report."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_setup", ROOT / "src/check_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.mark.parametrize("column,value", [
    ("steam_appid", "invalid"),
    ("steam_appid", None),
    ("avg_players", "invalid"),
    ("avg_players", None),
    ("avg_players", float("inf")),
    ("avg_players", -1),
])
def test_invalid_input_cannot_be_reported_as_passed(tmp_path, monkeypatch, column, value):
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    (raw / "sources.json").write_text(json.dumps({"sources": []}), encoding="utf-8")
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: None)
    games = pd.DataFrame({"appID": [10], "name": ["Example"], "genres": [["Action"]]})
    players = pd.DataFrame({"steam_appid": [10], "month": ["Sep-25"], "avg_players": [100]})
    players[column] = pd.Series([value])
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: games)
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: players)
    monkeypatch.setattr(pq, "ParquetFile", lambda *args: SimpleNamespace(metadata=SimpleNamespace(num_rows=1)))
    with pytest.raises(ValueError):
        setup.main()
    assert not (tmp_path / "reports/setup_check.json").exists()
