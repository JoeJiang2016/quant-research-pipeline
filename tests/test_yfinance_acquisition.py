import copy
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backtest.reconciliation import load_config, validate_acquisition_config
from scripts import download_yfinance_dataset

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/data_sources/yfinance_daily.json"


class FakeFrame:
    def __init__(self, rows, fields):
        self.rows = rows
        self.fields = fields
        self.empty = False
        self.index = SimpleNamespace(name=None)

    def to_csv(self, path, lineterminator="\n", date_format=None):
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fields,
                                    lineterminator=lineterminator)
            writer.writeheader()
            writer.writerows(self.rows)


class FakeYFinance:
    __version__ = "1.7.0"

    def __init__(self):
        self.calls = []
        self.cache_path = None

    def set_tz_cache_location(self, path):
        self.cache_path = path

    def download(self, ticker, start, end, **parameters):
        self.calls.append({"ticker": ticker, "start": start, "end": end, **parameters})
        common = [
            {"Date": "2024-01-02", "Open": "100", "High": "102", "Low": "99",
             "Close": "101", "Adj Close": "91", "Volume": "1000",
             "Dividends": "0", "Stock Splits": "0"},
            {"Date": "2024-01-03", "Open": "101", "High": "103", "Low": "100",
             "Close": "102", "Adj Close": "92", "Volume": "1100",
             "Dividends": "0.24", "Stock Splits": "4"},
        ]
        if parameters["auto_adjust"]:
            common = [{**row, "Open": str(float(row["Open"]) - 10),
                       "High": str(float(row["High"]) - 10),
                       "Low": str(float(row["Low"]) - 10),
                       "Close": row["Adj Close"]} for row in common]
        return FakeFrame(common, list(common[0]))


def temp_config(tmp_path):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    return config


def test_contract_requires_every_critical_parameter():
    config = temp_config(None)
    for section, key in (("common_parameters", "repair"),
                         ("profiles.raw", "auto_adjust")):
        broken = copy.deepcopy(config)
        target = broken["common_parameters"] if section == "common_parameters" else broken["profiles"]["raw"]
        del target[key]
        with pytest.raises(ValueError):
            validate_acquisition_config(broken)


def test_mocked_acquisition_preserves_actions_and_links_provenance(tmp_path, monkeypatch):
    config = temp_config(tmp_path)
    monkeypatch.setattr(download_yfinance_dataset, "ROOT", tmp_path)
    fake = FakeYFinance()
    result = download_yfinance_dataset.acquire(config, yf=fake)

    assert len(fake.calls) == 2
    assert {call["auto_adjust"] for call in fake.calls} == {False, True}
    assert all(call["repair"] is False and call["actions"] is True for call in fake.calls)
    acquisition = result["acquisition_manifest"]
    assert acquisition["library_version"] == "1.7.0"
    assert acquisition["corporate_actions"]["event_counts"] == {
        "Dividends": 1, "Stock Splits": 1, "Capital Gains": 0}
    assert "Dividends" in (tmp_path / config["profiles"]["raw"]["artifact_path"]).read_text()

    raw = result["raw"]["manifest"]
    adjusted = result["auto_adjusted"]["manifest"]
    assert raw["dataset_id"] != adjusted["dataset_id"]
    assert raw["price_adjustment"] == "raw"
    assert adjusted["price_adjustment"] == "provider_adjusted"
    assert adjusted["adjustment_method"] == "yfinance_auto_adjust"
    assert raw["processed_file_sha256"] != adjusted["processed_file_sha256"]
    assert raw["raw_file_sha256"] != adjusted["raw_file_sha256"]
    assert adjusted["provenance"]["provider_acquisition_id"] == config["acquisition_id"]
    assert adjusted["provenance"]["provider_raw_sha256"] == acquisition["provider_artifacts"]["raw"]["sha256"]
    assert "legacy" not in json.dumps(acquisition).lower()


def test_immutable_acquisition_rejects_changed_provider_content(tmp_path, monkeypatch):
    config = temp_config(tmp_path)
    monkeypatch.setattr(download_yfinance_dataset, "ROOT", tmp_path)
    fake = FakeYFinance()
    download_yfinance_dataset.acquire(config, yf=fake)
    changed = FakeYFinance()
    original = changed.download

    def changed_download(*args, **kwargs):
        frame = original(*args, **kwargs)
        frame.rows[0]["Volume"] = "9999"
        return frame

    changed.download = changed_download
    with pytest.raises(FileExistsError, match="immutable provider artifact"):
        download_yfinance_dataset.acquire(config, yf=changed)
