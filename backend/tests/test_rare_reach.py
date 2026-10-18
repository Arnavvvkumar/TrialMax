from app.models import Rule, TrialInfo
from app.rare_reach import build_rare_reach, find_hospitals, lookup_orpha


class Response:
    status_code = 404
    def raise_for_status(self): pass
    def json(self):
        return {"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States", "geoPoint": {"lat": 42.3601, "lon": -71.0589}}, {"facility": "Non-US Hospital", "city": "Toronto", "state": "ON", "country": "Canada"}]}}}, {"protocolSection": {"identificationModule": {"nctId": "NCT00000002"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States"}]}}}]}


class Client:
    def get(self, *_args, **_kwargs): return Response()


class OrphadataResponse:
    status_code = 200
    def raise_for_status(self): pass
    def json(self):
        return {"data": {"__licence": {"name": "Creative Commons Attribution 4.0 International"}, "results": {"ORPHAcode": 181376, "Preferred term": "Rare diabetes mellitus type 2", "Synonym": ["Rare insulin-independent diabetes mellitus"]}}}


class OrphadataClient:
    def get(self, *_args, **_kwargs): return OrphadataResponse()


def trial(): return TrialInfo(nct_id="NCT01234567", title="Rare study", conditions=["Rare condition"], eligibility_text="Criteria")


def test_sites_count_public_trial_records_not_patients():
    sites = find_hospitals(trial(), Client())
    assert len(sites) == 1 and sites[0].historical_trial_count == 2
    assert sites[0].country == "United States"
    assert (sites[0].latitude, sites[0].longitude) == (42.3601, -71.0589)
    assert "not patient volume" in sites[0].explanation


def test_non_rare_condition_stops_before_site_or_outreach_research():
    rule = Rule(id="R1", kind="inclusion", text="Age >= 18", variable="age", operator=">=", value=18, unit="years", simulatable=True)
    response = build_rare_reach("NCT01234567", [rule], trial=trial(), client=Client())
    assert response.orpha_status == "no_match"
    assert response.is_rare_disease is False
    assert response.orpha_code is None
    assert response.hospitals == []
    assert response.strategies == []
    assert response.nord_url is None
    assert "Rare condition" in response.rare_disease_message
    assert response.sources[1]["access"] == "live"


def test_broad_condition_does_not_match_a_different_rare_subtype_or_licence_metadata():
    code, preferred, synonyms, status, reason = lookup_orpha("Type 2 Diabetes", OrphadataClient())
    assert (code, preferred, synonyms, status) == (None, None, [], "no_match")
    assert "Rare diabetes mellitus type 2" in reason
