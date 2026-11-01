"""Shared notebook presentation; source DataFrames remain unchanged."""
from html import escape
from numbers import Integral, Real
import re

import pandas as pd
from IPython.display import HTML


LABELS = {
    "app_id": "App ID", "appID": "App ID", "steam_appid": "App ID",
    "avg_players": "Average concurrent activity",
    "average_concurrent_players": "Summed concurrent activity",
    "latest_month_average_players": "Latest-month activity",
    "coverage_rate": "Internal coverage",
    "internal_missing_apps": "Apps with internal gaps",
    "activity_share_pct": "Activity share",
    "year_over_year_pct": "Year-over-year change",
    "leader_share_pct": "Leading app share",
    "metadata_available": "Metadata matched",
    "mae": "MAE", "rmse": "RMSE", "wape_pct": "WAPE",
    "mean_absolute_target_average_error": "Mean absolute target-average error",
    "source_url": "Source URL", "has_latest_complete_month": "Latest complete month available",
}
CSS = """
<style>
.steam-report {font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
 color:#514b65;background:#fffaf6;border:2px solid #c9b4e6;
 box-shadow:4px 4px 0 #cce4d7;margin:16px 4px 26px 0;padding:14px;box-sizing:border-box}
.steam-report .table-scroll {overflow-x:auto;max-width:100%}
.steam-report table {border-collapse:collapse;min-width:65%;font-size:13px}
.steam-report caption {text-align:left;font-weight:600;font-size:14px;padding:0 0 12px;color:#635277}
.steam-report th {text-align:left!important;background:#e9def5;color:#514365;
 border-bottom:2px solid #bda4da;padding:10px 14px;white-space:normal;max-width:230px}
.steam-report td {padding:9px 14px;border-bottom:1px solid #eadff0;color:#514b65;
 text-align:left;vertical-align:top;max-width:360px;overflow-wrap:anywhere;white-space:normal}
.steam-report td.numeric-cell {text-align:right;white-space:nowrap}
.steam-report td.date-cell {white-space:nowrap;overflow-wrap:normal}
.steam-report tbody tr:nth-child(even) {background:#f4edf8}
.steam-report tbody tr:hover {background:#e7f3ec}
.steam-report .table-note {font-size:12px;margin-top:10px;color:#756981}
</style>
"""


def configure_notebook():
    """Use a consistent, readable style for saved Matplotlib figures."""
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.titlesize": 13, "axes.titleweight": "bold",
        "axes.titlepad": 12, "axes.labelsize": 11,
        "axes.labelcolor": "#514b65", "axes.edgecolor": "#e4daec",
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "#fffaf6", "axes.facecolor": "#fffaf6",
        "text.color": "#514b65", "xtick.color": "#70647e",
        "ytick.color": "#70647e", "grid.color": "#e4daec",
        "lines.linewidth": 1.8, "legend.fontsize": 10,
        "savefig.facecolor": "#fffaf6",
    })


def report_table(frame, caption):
    """Render a copy, retaining meaningful row keys and explicit missing values."""
    view = frame.copy()
    if "error" in view.columns:
        view["error"] = view["error"].fillna("None recorded")
    meaningful_index = not isinstance(view.index, pd.RangeIndex)
    if meaningful_index and view.index.name is None:
        view.index.name = "Metric" if len(view.columns) == 1 else "Group"
    formatters = {}
    for column in view.columns:
        key = str(column).lower()
        def format_value(value, key=key):
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, pd.Timestamp):
                return value.strftime("%b %Y")
            if isinstance(value, Integral):
                return str(value) if key in {"app_id", "appid", "steam_appid", "lead"} else f"{value:,}"
            if isinstance(value, Real):
                if key == "coverage_rate" or key in {"top1_share", "top5_share"}:
                    return f"{value:.2%}"
                if key.endswith("_pct") or "percent" in key:
                    return f"{value:,.2f}%"
                if key.endswith(("_months", "_apps", "_predictions")) or key in {"rows", "origins", "count"}:
                    return f"{value:,.0f}"
                return f"{value:,.2f}"
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-01", value):
                return pd.Timestamp(value).strftime("%b %Y")
            return str(value)
        formatters[column] = format_value
    if meaningful_index and len(view.columns) == 1:
        column = view.columns[0]
        view[column] = view[column].astype(object)
        for row in view.index:
            value = view.at[row, column]
            if pd.notna(value):
                # Vertical audit summaries name each metric in the row index.
                key = str(row).lower()
                if key == "coverage_rate":
                    value = f"{value:.2%}"
                elif isinstance(value, Integral):
                    value = f"{value:,}"
                elif isinstance(value, Real):
                    value = f"{value:,.0f}" if key.endswith(("_apps", "_months")) else f"{value:,.2f}"
                view.at[row, column] = value
        view.index = [LABELS.get(str(row), str(row).replace("_", " ").capitalize()
                                if "_" in str(row) else row) for row in view.index]
    table = view.to_html(index=meaningful_index, border=0, na_rep="Unavailable",
                         escape=True, formatters=formatters, classes="steam-data")
    cell_classes = []
    for column in frame.columns:
        values = frame[column].dropna()
        numeric = (pd.api.types.is_numeric_dtype(values)
                   and not pd.api.types.is_bool_dtype(values))
        dates = pd.api.types.is_datetime64_any_dtype(values) or (
            len(values) > 0 and all(isinstance(value, str) and
            re.fullmatch(r"\d{4}-\d{2}-01", value) for value in values))
        cell_classes.append("numeric-cell" if numeric else "date-cell" if dates else "text-cell")
    def align_row(match):
        positions = iter(cell_classes)
        return re.sub(r"<td>", lambda _: '<td class="' + next(positions) + '">',
                      match.group(0))
    table = re.sub(r"<tr[^>]*>.*?</tr>", align_row, table, flags=re.S)
    # Rename only rendered headers, preserving raw field names in calculations.
    for column in view.columns:
        label = LABELS.get(str(column), str(column).replace("_", " ").capitalize())
        table = table.replace("<th>" + escape(str(column)) + "</th>",
                              "<th>" + escape(label) + "</th>", 1)
    table = table.replace("<thead>", "<caption>" + escape(caption) + "</caption><thead>", 1)
    note = ('<div class="table-note">Unavailable = no recorded value.</div>'
            if frame.isna().to_numpy().any() else "")
    return HTML(CSS + '<div class="steam-report"><div class="table-scroll">' +
                table + "</div>" + note + "</div>")


def present(value, caption):
    """Style table results while leaving figures and other results untouched."""
    if isinstance(value, pd.Series):
        value = value.to_frame()
    return report_table(value, caption) if isinstance(value, pd.DataFrame) else value
