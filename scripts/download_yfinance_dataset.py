"""Acquire the two explicit Yahoo views, then delegate canonical import/validation."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
dependency_path = os.environ.get("DATA_ACQUISITION_DEPENDENCY_PATH")
if dependency_path:
    sys.path.insert(0, dependency_path)

from backtest.datasets import checksum
from backtest.reconciliation import load_config, validate_acquisition_config
from backtest.yfinance_acquisition import finalize_acquisition


def _write_immutable_frame(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.index.name = "Date"
    frame.to_csv(temporary, lineterminator="\n", date_format="%Y-%m-%d")
    if path.exists():
        if checksum(path) != checksum(temporary):
            temporary.unlink()
            raise FileExistsError(f"immutable provider artifact differs: {path}")
        temporary.unlink()
    else:
        temporary.replace(path)


def acquire(config, *, yf):
    validate_acquisition_config(config, installed_yfinance_version=yf.__version__)
    cache_path = ROOT / config["cache_path"]
    cache_path.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_path))
    for name, profile in config["profiles"].items():
        parameters = dict(config["common_parameters"])
        parameters["auto_adjust"] = profile["auto_adjust"]
        parameters["period"] = config["download_semantics"]["period"]
        frame = yf.download(
            config["symbol"], start=config["start"], end=config["end_exclusive"],
            **parameters,
        )
        if frame.empty:
            raise RuntimeError(f"empty Yahoo download: {name}")
        _write_immutable_frame(frame, ROOT / profile["artifact_path"])
    return finalize_acquisition(config, root=ROOT)


def main(config_path):
    import yfinance as yf

    config = load_config(config_path)
    result = acquire(config, yf=yf)
    for name in ("raw", "auto_adjusted"):
        manifest = result[name]["manifest"]
        print(f"{name}: {manifest['dataset_id']}_v{manifest['version']} "
              f"{manifest['processed_file_sha256']}")
    print(f"acquisition_manifest: {result['acquisition_manifest_path']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path,
                        default=ROOT / "config/data_sources/yfinance_daily.json")
    main(parser.parse_args().config)
