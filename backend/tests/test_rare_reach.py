from app.models import Rule, TrialInfo
from app.rare_reach import build_rare_reach, find_hospitals


class Response:
    status_code = 404
    def raise_for_status(self): pass
    def json(self):
        return {"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States"}, {"facility": "Non-US Hospital", "city": "Toronto", "state": "ON", "country": "Canada"}]}}}, {"protocolSection": {"identificationModule": {"nctId": "NCT00000002"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States"}]}}}]}


class Client:
    def get(self, *_args, **_kwargs): return Response()


def trial(): return TrialInfo(nct_id="NCT01234567", title="Rare study", conditions=["Rare condition"], eligibility_text="Criteria")


def test_sites_count_public_trial_records_not_patients():
    sites = find_hospitals(trial(), Client())
    assert len(sites) == 1 and sites[0].historical_trial_count == 2
    assert sites[0].country == "United States"
    assert "not patient volume" in sites[0].explanation


def test_response_keeps_orphanet_and_nord_link_only():
    rule = Rule(id="R1", kind="inclusion", text="Age >= 18", variable="age", operator=">=", value=18, unit="years", simulatable=True)
    response = build_rare_reach("NCT01234567", [rule], trial=trial(), client=Client())
    assert response.orpha_status == "no_match"
    assert response.sources[1]["access"] == "live"
    assert response.strategies[0].outreach.startswith("Keep this criterion")
