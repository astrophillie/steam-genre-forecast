"""Collect and audit at most 20 SteamCharts app histories in a separate snapshot."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid
from urllib.robotparser import RobotFileParser

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "SteamGenreForecastResearch/0.1 (single-threaded portfolio validation)"
HEADERS = ["Month", "Avg. Players", "Gain", "% Gain", "Peak Players"]
MONTHS = {name: index for index, name in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}


class MonthlyTables(HTMLParser):
    """Read table cells without depending on optional HTML parsing packages."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table is not None:
                raise ValueError("Unexpected nested table")
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_monthly_html(html, app_id, as_of):
    """Extract published calendar-month rows; preserve zeros and absent months."""
    parser = MonthlyTables()
    parser.feed(html)
    matches = [table for table in parser.tables if table and table[0] == HEADERS]
    if len(matches) != 1:
        raise ValueError("Expected exactly one SteamCharts monthly table")
    cutoff = pd.Timestamp(as_of).tz_localize(None).to_period("M").to_timestamp()
    rows = []
    for cells in matches[0][1:]:
        if len(cells) != 5:
            raise ValueError("Malformed monthly table row")
        label = cells[0]
        if label == "Last 30 Days":
            continue
        match = re.fullmatch(r"([A-Za-z]+) ([0-9]{4})", label)
        if not match or match[1] not in MONTHS:
            raise ValueError(f"Unexpected month label: {label}")
        month = pd.Timestamp(year=int(match[2]), month=MONTHS[match[1]], day=1)
        if month > cutoff:
            raise ValueError("Unexpected future calendar month")
        if month == cutoff:
            continue
        try:
            average = float(cells[1].replace(",", ""))
            peak = float(cells[4].replace(",", ""))
        except ValueError as error:
            raise ValueError("Invalid numeric activity") from error
        if not np.isfinite([average, peak]).all() or average < 0 or peak < 0 or peak % 1:
            raise ValueError("Activity must be finite and nonnegative, with integer peaks")
        if average > peak + 1e-8:
            raise ValueError("Monthly average exceeds peak")
        rows.append({"app_id": int(app_id), "month": month.strftime("%Y-%m-01"),
                     "avg_players": average, "peak_players": int(peak)})
    result = pd.DataFrame(rows, columns=["app_id", "month", "avg_players", "peak_players"])
    if result.empty:
        raise ValueError("No completed calendar-month observations")
    if result["month"].duplicated().any():
        raise ValueError("Duplicate monthly records")
    return result.sort_values("month").reset_index(drop=True)


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_baseline():
    database = ROOT / "database/steam.sqlite"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        games = pd.read_sql_query("SELECT * FROM games ORDER BY app_id", connection)
        players = pd.read_sql_query("SELECT app_id,month,avg_players FROM monthly_players ORDER BY app_id,month", connection)
        labels = pd.read_sql_query("SELECT * FROM game_genres", connection)
    return games, players, labels


def select_cohort(games, players, labels, as_of, limit=20):
    """A deterministic diagnostic sample, not a representative market sample."""
    if not 1 <= limit <= 20:
        raise ValueError("Pilot limit must be between 1 and 20")
    latest_month = players["month"].max()
    latest = players.loc[players["month"].eq(latest_month)].merge(games, on="app_id", validate="one_to_one")
    selected = {}
    names = games.set_index("app_id")["name"].to_dict()

    def add(app_id, reason, name=None):
        app_id = int(app_id)
        if app_id not in selected and len(selected) < limit:
            selected[app_id] = {"app_id": app_id, "name": name or names.get(app_id, "Unmatched coverage probe"),
                                "selection_reason": reason}

    for app_id in [730, 252490, 289070]:
        add(app_id, "Previously verified overlap anchor")
    add(570, "Large-title coverage probe", "Dota 2")
    category_latest = latest.loc[latest["eligible"].eq(1)].merge(labels, on="app_id")
    for category in ["Action", "Indie", "Massively Multiplayer", "RPG", "Strategy"]:
        candidates = category_latest.loc[category_latest["genre"].eq(category)].sort_values(
            ["avg_players", "app_id"], ascending=[False, True])
        for app_id in candidates["app_id"].head(2):
            add(app_id, f"High-activity {category} coverage")
    for app_id in latest.loc[latest["review_group"].eq("Missing metadata")].sort_values(
            ["avg_players", "app_id"], ascending=[False, True])["app_id"].head(2):
        add(app_id, "Tracked app without matched metadata")
    add(431960, "Mixed-label software probe", "Wallpaper Engine")
    software = latest.loc[latest["review_group"].eq("Software/media labels only")].sort_values(
        ["avg_players", "app_id"], ascending=[False, True])
    for app_id in software["app_id"].head(1):
        add(app_id, "Software-only eligibility holdout")
    spans = players.assign(date=pd.to_datetime(players["month"])).groupby("app_id").agg(
        first=("date", "min"), last=("date", "max"), count=("date", "size"))
    spans["missing"] = ((spans["last"].dt.year - spans["first"].dt.year)*12
                        + spans["last"].dt.month - spans["first"].dt.month + 1 - spans["count"])
    eligible_ids = set(games.loc[games["eligible"].eq(1), "app_id"])
    for app_id in spans.loc[spans.index.isin(eligible_ids)].sort_values("missing", ascending=False).head(2).index:
        add(app_id, "History with many internal gaps")
    small = latest.loc[latest["eligible"].eq(1) & latest["avg_players"].between(1, 20)].sort_values("app_id")
    for app_id in small.sample(n=min(2, len(small)), random_state=42)["app_id"]:
        add(app_id, "Small-audience observed app")
    metadata = pd.read_parquet(ROOT / "data/raw/fronkon_metadata/games.parquet",
                              columns=["appID", "name", "release_date", "peak_ccu"])
    dates = pd.to_datetime(metadata["release_date"], format="mixed", errors="coerce")
    recent = metadata.loc[dates.dt.to_period("M").gt(pd.Timestamp(latest_month).to_period("M")) & dates.lt(
        pd.Timestamp(as_of).tz_localize(None).to_period("M").to_timestamp())].sort_values(
            ["peak_ccu", "appID"], ascending=[False, True])
    for row in recent.head(2).itertuples():
        add(row.appID, "Metadata release date after old player cutoff", row.name)
    # Fill remaining slots with reproducible low-audience records, keeping bounded scope.
    for row in small.itertuples():
        add(row.app_id, "Additional small-audience coverage")
    return list(selected.values())


def collect(run_id=None, offline=False, limit=20, delay=2.0):
    if delay < 2:
        raise ValueError("Pilot requests must be spaced by at least two seconds")
    if offline and not run_id:
        raise ValueError("Offline replay requires an existing run ID")
    if run_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid snapshot run ID")
    now = datetime.now(timezone.utc)
    run_id = run_id or now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
    folder = ROOT / "data/raw/steamcharts_pilot" / run_id
    manifest_path = folder / "manifest.json"
    baseline_hash = digest(ROOT / "database/steam.sqlite")
    games, players, labels = load_baseline()
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["baseline_database_sha256"] != baseline_hash:
            raise ValueError("Baseline changed; start a new pilot snapshot")
        if manifest["baseline_sources_sha256"] != digest(ROOT / "data/raw/sources.json"):
            raise ValueError("Baseline source manifest changed; start a new pilot snapshot")
    else:
        if offline:
            raise FileNotFoundError("Pilot snapshot is absent")
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "pages").mkdir()
        manifest = {"run_id": run_id, "created_at_utc": now.isoformat(),
                    "as_of": now.date().isoformat(), "source": "https://steamcharts.com",
                    "baseline_database_sha256": baseline_hash,
                    "baseline_sources_sha256": digest(ROOT / "data/raw/sources.json"),
                    "cohort": select_cohort(games, players, labels, now, limit),
                    "user_agent": USER_AGENT, "entries": {},
                    "scope": "Bounded pilot; no bulk-access or redistribution permission established"}
        save_json(manifest_path, manifest)
    if offline and ("robots" not in manifest or not (folder / "robots.txt").is_file()):
        raise FileNotFoundError("Offline replay requires cached robots evidence; no request attempted")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    robots = None
    if "robots" not in manifest:
        response = session.get("https://steamcharts.com/robots.txt", timeout=(10, 30))
        (folder / "robots.txt").write_bytes(response.content)
        manifest["robots"] = {"status": response.status_code,
                             "sha256": digest(folder / "robots.txt")}
        save_json(manifest_path, manifest)
    robot_status = manifest["robots"]["status"]
    robot_content = (folder / "robots.txt").read_text(encoding="utf-8", errors="replace")
    if digest(folder / "robots.txt") != manifest["robots"]["sha256"]:
        raise ValueError("Cached robots response checksum mismatch")
    if robot_status == 200:
        robots = RobotFileParser()
        robots.parse(robot_content.splitlines())
        delay = max(delay, robots.crawl_delay(USER_AGENT) or robots.crawl_delay("*") or 0)
    elif robot_status != 404:
        raise ValueError(f"Cannot establish pilot access after robots HTTP {robot_status}")
    blocked = False
    collected = []
    status_rows = []
    try:
        for item in manifest["cohort"]:
            app_id = item["app_id"]
            url = f"https://steamcharts.com/app/{app_id}"
            path = folder / "pages" / f"{app_id}.html"
            entry = manifest["entries"].get(str(app_id))
            record = dict(item, source_url=url)
            try:
                if blocked:
                    raise ValueError("Not attempted after an access/rate-limit response")
                if robots and not robots.can_fetch(USER_AGENT, url):
                    raise ValueError("robots.txt disallows this app path")
                if path.exists():
                    if not entry or digest(path) != entry["sha256"]:
                        raise ValueError("Cached app page checksum mismatch")
                elif offline:
                    raise ValueError("Page absent from offline snapshot")
                else:
                    time.sleep(delay)
                    response = session.get(url, timeout=(10, 30), allow_redirects=False)
                    path.write_bytes(response.content)
                    entry = {"http_status": response.status_code, "sha256": digest(path),
                             "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                             "source_url": url, "bytes": len(response.content)}
                    manifest["entries"][str(app_id)] = entry
                    save_json(manifest_path, manifest)
                status = entry["http_status"]
                if status in {401, 403, 429}:
                    blocked = True
                if status != 200:
                    raise ValueError(f"HTTP {status}; no history inferred")
                frame = parse_monthly_html(path.read_text(encoding="utf-8"), app_id, manifest["as_of"])
                frame["source_url"] = url
                frame["page_sha256"] = entry["sha256"]
                frame["snapshot_run_id"] = run_id
                collected.append(frame)
                record.update(status="ok", rows=len(frame), first_month=frame["month"].min(),
                              last_month=frame["month"].max(), error="")
            except (requests.RequestException, ValueError, UnicodeError) as error:
                record.update(status="failed", rows=0, first_month=None, last_month=None, error=str(error))
            status_rows.append(record)
            print(f"{app_id}: {record['status']} ({record['rows']} months)", flush=True)
    finally:
        session.close()
    manifest["pilot_status"] = "completed_with_failures" if any(r["status"] != "ok" for r in status_rows) else "completed"
    manifest["last_replayed_at_utc"] = datetime.now(timezone.utc).isoformat()
    save_json(manifest_path, manifest)
    fresh = pd.concat(collected, ignore_index=True) if collected else pd.DataFrame(
        columns=["app_id", "month", "avg_players", "peak_players", "source_url", "page_sha256", "snapshot_run_id"])
    status_table = pd.DataFrame(status_rows)
    overlap = players.merge(fresh[["app_id", "month", "avg_players"]], on=["app_id", "month"],
                            how="inner", validate="one_to_one", suffixes=("_old", "_pilot"))
    overlap["absolute_difference"] = (overlap["avg_players_old"] - overlap["avg_players_pilot"]).abs()
    overlap["within_rounding_tolerance"] = overlap["absolute_difference"].le(.011)
    old_max = players["month"].max()
    complete_cutoff = (pd.Timestamp(manifest["as_of"]).to_period("M") - 1).to_timestamp().strftime("%Y-%m-01")
    audits = []
    for item in status_rows:
        history = fresh.loc[fresh["app_id"].eq(item["app_id"])]
        matches = overlap.loc[overlap["app_id"].eq(item["app_id"])]
        new = history.loc[history["month"].gt(old_max)]
        if history.empty:
            gaps = None
        else:
            gaps = len(pd.date_range(history["month"].min(), history["month"].max(), freq="MS")) - len(history)
        audits.append(dict(item, overlap_months=len(matches),
            overlap_mismatches=int((~matches["within_rounding_tolerance"]).sum()),
            new_months=len(new), has_latest_complete_month=bool(history["month"].eq(complete_cutoff).any()),
            internal_missing_months=gaps))
    output = ROOT / "reports/steamcharts_pilot" / run_id
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "source_manifest.json", manifest)
    fresh.to_csv(output / "monthly_players.csv", index=False)
    pd.DataFrame(audits).to_csv(output / "app_audit.csv", index=False)
    overlap.to_csv(output / "overlap_comparison.csv", index=False)
    save_json(output / "summary.json", {
        "run_id": run_id, "as_of": manifest["as_of"], "baseline_cutoff": old_max,
        "latest_complete_calendar_month": complete_cutoff,
        "selected_apps": len(status_rows), "successful_apps": int(status_table["status"].eq("ok").sum()),
        "failed_apps": int(status_table["status"].ne("ok").sum()),
        "completed_month_rows": len(fresh), "overlap_rows": len(overlap),
        "overlap_mismatches": int((~overlap["within_rounding_tolerance"]).sum()),
        "new_month_rows": int(fresh["month"].gt(old_max).sum()),
        "scope": "Pilot only; original raw files, prepared database, and model inputs unchanged",
        "raw_manifest": manifest_path.relative_to(ROOT).as_posix(),
    })
    print(f"Pilot reports: {output.relative_to(ROOT)}", flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    collect(args.run_id, args.offline, args.limit)
