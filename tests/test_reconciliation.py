import copy, csv, json
from pathlib import Path
import pytest
from backtest.reconciliation import (compare_csv_files, load_config,
                                     validate_acquisition_config)

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"config/data_sources/yfinance_daily.json"


def write(path, rows):
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=["Date","Open","High","Low","Close","Volume"],lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def test_download_contract_requires_explicit_parameters_and_version():
    config=load_config(CONFIG)
    assert config["library_version"]=="1.7.0"
    validate_acquisition_config(config,installed_yfinance_version="1.7.0")
    broken=copy.deepcopy(config); del broken["common_parameters"]["repair"]
    with pytest.raises(ValueError,match="explicit"): validate_acquisition_config(broken)
    broken=copy.deepcopy(config); del broken["profiles"]["raw"]["auto_adjust"]
    with pytest.raises(ValueError,match="profile missing"): validate_acquisition_config(broken)
    with pytest.raises(ValueError,match="version"): validate_acquisition_config(config,installed_yfinance_version="other")


def test_comparison_aligns_by_session_date_and_reports_mismatches(tmp_path):
    left=tmp_path/"left.csv"; right=tmp_path/"right.csv"
    write(left,[{"Date":"2024-01-01","Open":"10","High":"11","Low":"9","Close":"10","Volume":"100"},
                {"Date":"2024-01-02","Open":"11","High":"12","Low":"10","Close":"11","Volume":"200"}])
    write(right,[{"Date":"2024-01-02","Open":"11","High":"12","Low":"10","Close":"11.5","Volume":"200"},
                 {"Date":"2024-01-03","Open":"12","High":"13","Low":"11","Close":"12","Volume":"300"}])
    result=compare_csv_files(left,right,fields=["Open","High","Low","Close","Volume"],absolute_tolerance="1e-10",relative_tolerance="1e-12")
    assert result["overlap_row_count"]==1
    assert result["left_only_dates"]==["2024-01-01"] and result["right_only_dates"]==["2024-01-03"]
    assert result["fields"]["Close"]["mismatch_count"]==1
    assert result["total_field_mismatches"]==1 and result["mismatch_examples"]


def test_comparison_is_deterministic_and_does_not_modify_legacy(tmp_path):
    legacy=tmp_path/"legacy.csv"; candidate=tmp_path/"candidate.csv"
    rows=[{"Date":"2024-01-01","Open":"10","High":"11","Low":"9","Close":"10","Volume":"100"}]
    write(legacy,rows); write(candidate,rows); before=legacy.read_bytes()
    kwargs=dict(fields=["Open","High","Low","Close","Volume"],absolute_tolerance="1e-10",relative_tolerance="1e-12")
    first=compare_csv_files(legacy,candidate,**kwargs); second=compare_csv_files(legacy,candidate,**kwargs)
    assert json.dumps(first,sort_keys=True)==json.dumps(second,sort_keys=True)
    assert legacy.read_bytes()==before
