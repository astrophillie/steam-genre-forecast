r"""Download the two public starter datasets and preserve source provenance.

Run with: .venv\Scripts\python.exe src\download_data.py
Existing downloads are retained. No credentials or account are required.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def read_json(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def download(url, destination):
    if destination.exists():
        print(f"Already stored: {destination.relative_to(ROOT)}", flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading: {destination.relative_to(ROOT)}", flush=True)
    with urllib.request.urlopen(url, timeout=180) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(destination)


def record_file(path):
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def extract_players(archive, destination, expected_hash=None):
    """Extract only the known CSV member, then publish the complete file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.namelist().count("steamcharts.csv") != 1:
            raise ValueError("Expected exactly one steamcharts.csv archive member")
        with bundle.open("steamcharts.csv") as source, partial.open("wb") as output:
            shutil.copyfileobj(source, output)
    if expected_hash and record_file(partial)["sha256"] != expected_hash:
        raise ValueError(f"Checksum mismatch: {destination}")
    partial.replace(destination)


def restore_snapshot(manifest):
    """Restore recorded files using pinned URLs; never relabel existing bytes."""
    for source in manifest["sources"]:
        entries = source["files"]
        paths = {entry["path"]: (ROOT / entry["path"]).resolve() for entry in entries}
        for path in paths.values():
            if not path.is_relative_to(RAW.resolve()):
                raise ValueError("Manifest file path must stay inside data/raw")
        # Check every existing file before downloading or replacing anything.
        for entry in entries:
            path = paths[entry["path"]]
            if path.exists() and record_file(path)["sha256"] != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {path}")
        for entry in entries:
            path = paths[entry["path"]]
            if path.exists():
                continue
            if path.suffix == ".csv":
                archives = [paths[item["path"]] for item in entries if item["path"].endswith(".zip")]
                if len(archives) != 1:
                    raise ValueError("CSV restoration requires one recorded archive")
                archive = archives[0]
                archive_entry = next(item for item in entries if paths[item["path"]] == archive)
                if not archive.exists():
                    download(source["download_url"], archive)
                if record_file(archive)["sha256"] != archive_entry["sha256"]:
                    raise ValueError(f"Checksum mismatch: {archive}")
                extract_players(archive, path, entry["sha256"])
            else:
                download(source["download_url"], path)
            if record_file(path)["sha256"] != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {path}")



def main():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "sources.json"
    if manifest_path.exists():
        restore_snapshot(json.loads(manifest_path.read_text(encoding="utf-8")))
        print("Recorded source snapshot verified; missing files restored.")
        return
    existing_data = list(RAW.rglob("*.parquet")) + list(RAW.rglob("*.zip")) + list(RAW.rglob("*.csv"))
    if existing_data:
        raise ValueError("Existing data has no source manifest; restore its manifest before downloading.")


    hf = read_json("https://huggingface.co/api/datasets/FronkonGames/steam-games-dataset")
    kaggle = read_json("https://www.kaggle.com/api/v1/datasets/view/lunthu/steam-monthly-average-players")
    hf_dir = RAW / "fronkon_metadata"
    player_dir = RAW / "monthly_players"
    hf_dir.mkdir(exist_ok=True)
    player_dir.mkdir(exist_ok=True)
    (hf_dir / "dataset_info.json").write_text(json.dumps(hf, indent=2), encoding="utf-8")
    (player_dir / "dataset_info.json").write_text(json.dumps(kaggle, indent=2), encoding="utf-8")

    revision = hf["sha"]
    parquet = hf_dir / "games.parquet"
    metadata_url = f"https://huggingface.co/datasets/FronkonGames/steam-games-dataset/resolve/{revision}/data/train-00000-of-00001.parquet?download=true"
    download(metadata_url, parquet)
    download(f"https://huggingface.co/datasets/FronkonGames/steam-games-dataset/resolve/{revision}/README.md", hf_dir / "SOURCE_README.md")

    version = kaggle["currentVersionNumber"]
    archive = player_dir / "steam_monthly_players.zip"
    players_url = f"https://www.kaggle.com/api/v1/datasets/download/lunthu/steam-monthly-average-players?datasetVersionNumber={version}"
    download(players_url, archive)
    csv_path = player_dir / "steamcharts.csv"
    if not csv_path.exists():
        extract_players(archive, csv_path)


    manifest = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "name": "FronkonGames Steam metadata", "revision": revision,
                "source": "https://huggingface.co/datasets/FronkonGames/steam-games-dataset",
                "download_url": metadata_url, "license_as_reported": hf.get("cardData", {}).get("license"),
                "source_updated_at": hf.get("lastModified"), "files": [record_file(parquet)],
                "limitations": "Metadata snapshot; release dates do not provide historical player counts.",
            },
            {
                "name": "Steam Monthly Average Players", "version": version,
                "source": "https://www.kaggle.com/datasets/lunthu/steam-monthly-average-players",
                "download_url": players_url, "license_as_reported": kaggle.get("licenseName"),
                "source_updated_at": kaggle.get("lastUpdated"),
                "files": [record_file(archive), record_file(csv_path)],
                "limitations": "Historical sample, updated in 2025; misses low-audience and some major games. Not approved for final 2027 forecasting without a freshness/coverage audit.",
            },
        ],
        "reviews": "Deferred until the first two sources are understood, as agreed in the project guide.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Downloads and SHA-256 source manifest saved.", flush=True)


if __name__ == "__main__":
    main()
