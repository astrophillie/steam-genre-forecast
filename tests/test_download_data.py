"""Offline regression checks for restoring the recorded source snapshot."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("download_data", ROOT / "src" / "download_data.py")
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "ROOT", tmp_path)
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    monkeypatch.setattr(downloader, "RAW", raw)
    payload = b"month,avg_players,steam_appid\nSep-25,100,10\n"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("steamcharts.csv", payload)
    archive_bytes = archive.getvalue()
    files = []
    for name, content in [("steam_monthly_players.zip", archive_bytes), ("steamcharts.csv", payload)]:
        files.append({"path": f"data/raw/monthly_players/{name}",
                      "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    manifest = {"sources": [{"download_url": "https://example.invalid/pinned-v2.zip", "files": files}]}
    manifest_path = raw / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    requests = []
    def fake_open(url, **kwargs):
        requests.append(url)
        assert url == manifest["sources"][0]["download_url"]
        return io.BytesIO(archive_bytes)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", fake_open)
    return tmp_path, manifest_path, payload, requests


def test_manifest_restores_missing_files_from_pinned_url(snapshot):
    root, manifest_path, payload, requests = snapshot
    original_manifest = manifest_path.read_bytes()
    downloader.main()
    assert (root / "data/raw/monthly_players/steamcharts.csv").read_bytes() == payload
    assert requests == ["https://example.invalid/pinned-v2.zip"]
    assert manifest_path.read_bytes() == original_manifest


def test_existing_snapshot_is_verified_and_reused(snapshot):
    root, _, payload, requests = snapshot
    downloader.main()
    requests.clear()
    downloader.main()
    assert requests == []
    assert (root / "data/raw/monthly_players/steamcharts.csv").read_bytes() == payload


def test_corrupt_existing_file_is_not_silently_accepted(snapshot):
    root, _, _, _ = snapshot
    target = root / "data/raw/monthly_players/steamcharts.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Checksum"):
        downloader.main()
    assert target.read_bytes() == b"corrupt"


def test_files_without_manifest_are_not_given_new_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "ROOT", tmp_path)
    raw = tmp_path / "data/raw"
    (raw / "fronkon_metadata").mkdir(parents=True)
    (raw / "fronkon_metadata/games.parquet").write_bytes(b"unknown snapshot")
    monkeypatch.setattr(downloader, "RAW", raw)
    monkeypatch.setattr(downloader, "read_json", lambda url: pytest.fail("Must not fetch a new revision"))
    with pytest.raises(ValueError, match="manifest"):
        downloader.main()
