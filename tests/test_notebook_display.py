"""Presentation checks protect the meanings shown in notebook tables."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from notebook_display import report_table


def test_table_preserves_row_labels_and_does_not_modify_data():
    frame = pd.DataFrame({"apps": [174, 3703], "activity_share_pct": [.23, 99.77]},
                         index=pd.Index(["Unmatched", "Matched"], name="Metadata"))
    before = frame.copy(deep=True)
    html = report_table(frame, "Coverage").data
    pd.testing.assert_frame_equal(frame, before)
    assert "Unmatched" in html and "Matched" in html
    assert "99.77%" in html and "0.23%" in html


def test_percent_units_ids_and_missing_counts_stay_distinct():
    frame = pd.DataFrame({"app_id": [1476970, 730], "coverage_rate": [.7706, 1.0],
                          "internal_missing_months": [105., float("nan")]})
    html = report_table(frame, "History").data
    assert "1476970" in html and "1,476,970" not in html
    assert "77.06%" in html and "100.00%" in html
    assert ">105<" in html and "Unavailable" in html


def test_caption_and_values_are_escaped():
    html = report_table(pd.DataFrame({"name": ["<script>"]}), "<caption>").data
    assert "&lt;script&gt;" in html and "&lt;caption&gt;" in html
    assert "<script>" not in html

def test_vertical_audit_summary_retains_metric_units():
    frame = pd.Series({"coverage_rate": .7706, "observed_apps": 1990,
                       "category": "Indie"}).to_frame("Lowest coverage")
    html = report_table(frame, "Coverage detail").data
    assert "77.06%" in html and "1,990" in html
    assert "Internal coverage" in html and "Indie" in html

def test_calendar_month_cells_cannot_split_across_lines():
    html = report_table(pd.DataFrame({"month": ["2025-09-01"]}), "Month").data
    assert '<td class="date-cell">' in html
    assert "Sep" in html and "2025" in html
    assert "white-space:nowrap;overflow-wrap:normal" in html
