import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.chalk_trials import ChalkTrialError, ChalkTrialNotFound, fetch_chalk_trial, fetch_snapshot_trial, snapshot_info
from app.models import TrialInfo


def completed(payload):
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


def test_chalk_sql_trial_maps_existing_dataset_columns(monkeypatch):
    monkeypatch.setattr("app.chalk_trials.shutil.which", lambda _: "/usr/local/bin/chalk")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return completed({"rows": [{
            "nct_id": "NCT01234567", "brief_title": "Lung study",
            "criteria": "Inclusion Criteria:\\n* Adults", "gender": "ALL",
            "minimum_age": "18 Years", "maximum_age": "75 Years", "phase": "PHASE3",
            "overall_status": "RECRUITING", "enrollment": 250.0,
        }]})

    trial = fetch_chalk_trial("nct01234567", runner=runner, environment="chalk-env")

    command, kwargs = calls[0]
    assert command[:2] == ["chalk", "sql"] and "chalk.datasets.\"nsclc-trials\"" in command[2]
    assert "NCT01234567" in command[2] and command[-3:] == ["--environment", "chalk-env", "--json"]
    assert kwargs["check"] is False
    assert trial.title == "Lung study" and trial.phases == ["PHASE3"]
    assert trial.enrollment == 250 and trial.data_source == "chalk"


def test_chalk_sql_trial_without_a_row_is_not_found(monkeypatch):
    monkeypatch.setattr("app.chalk_trials.shutil.which", lambda _: "/usr/local/bin/chalk")
    with pytest.raises(ChalkTrialNotFound):
        fetch_chalk_trial(
            "NCT01234567", environment="chalk-env",
            runner=lambda *_args, **_kwargs: completed({"rows": []}),
        )


def test_api_trial_lookup_can_require_the_chalk_source(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "fetch_chalk_trial", lambda *_args, **_kwargs: TrialInfo(
        nct_id="NCT01234567", eligibility_text="Adults", data_source="chalk"
    ))
    result = main._get_trial("NCT01234567", "chalk")
    assert result.data_source == "chalk"


def no_cli(*_args, **_kwargs):
    raise ChalkTrialError("Chalk CLI is not installed or not on PATH.")


def test_without_the_cli_trials_come_from_the_bundled_chalk_snapshot(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "fetch_chalk_trial", no_cli)
    monkeypatch.setattr(main, "fetch_trial", lambda *_a, **_k: pytest.fail("must not reach ClinicalTrials.gov"))
    trial = main._get_trial("nct05429463", "auto")
    assert trial.data_source == "chalk-snapshot" and trial.nct_id == "NCT05429463" and trial.eligibility_text


def test_snapshot_miss_falls_back_to_ctgov_unless_chalk_is_required(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "fetch_chalk_trial", no_cli)
    monkeypatch.setattr(main, "fetch_trial", lambda nct_id: TrialInfo(nct_id=nct_id, eligibility_text="Adults"))
    assert main._get_trial("NCT05738694", "auto").data_source == "ctgov"   # kidney trial: not in the NSCLC dataset
    with pytest.raises(HTTPException) as missing:
        main._get_trial("NCT05738694", "chalk")
    assert missing.value.status_code == 404


def test_snapshot_records_its_chalk_provenance():
    info = snapshot_info()
    assert info["source"] == 'chalk.datasets."nsclc-trials"' and info["row_count"] > 3000
    with pytest.raises(ChalkTrialNotFound):
        fetch_snapshot_trial("NCT00000000")
