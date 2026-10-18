from app.models import Rule, TrialInfo
from app.rare_reach import build_rare_reach, find_hospitals, lookup_orpha


class Response:
    status_code = 404
    def raise_for_status(self): pass
    def json(self):
        return {"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States"}, {"facility": "Non-US Hospital", "city": "Toronto", "state": "ON", "country": "Canada"}]}}}, {"protocolSection": {"identificationModule": {"nctId": "NCT00000002"}, "contactsLocationsModule": {"locations": [{"facility": "Example Hospital", "city": "Boston", "state": "MA", "country": "United States"}]}}}]}


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


def site_client(records):
    class SiteResponse:
        def raise_for_status(self): pass
        def json(self): return {'studies':records}
    class SiteClient:
        def get(self,*_args,**_kwargs): return SiteResponse()
    return SiteClient()


def study(n, name, city='Houston', state='Texas', country='United States'):
    return {'protocolSection':{'identificationModule':{'nctId':f'NCT{n:08d}'},
            'contactsLocationsModule':{'locations':[dict(facility=name,city=city,state=state,country=country)]}}}


def test_site_aliases_merge_before_ranking_and_keep_distinct_trial_evidence():
    records = [study(i, name) for name, ids in [
        ('M D Anderson',range(1,4)), ('MD Anderson',range(4,7)),
        ('University of Texas MD Anderson',range(7,9))] for i in ids]
    records += [study(i,'Dana-Farber','Boston','MA') for i in range(10,15)]
    records += [study(i,name,'Dallas','TX') for name, ids in [
        ('UT Southwestern',range(20,23)), ('University of Texas Southwestern Medical Center',range(23,25))] for i in ids]
    # An alias repeated for the same trial must count only once.
    records += [study(1,'MD Anderson',state='TX',country='USA')]
    sites=find_hospitals(trial(),site_client(records))
    assert sites[0].name=='University of Texas MD Anderson Cancer Center'
    assert [s.historical_trial_count for s in sites]==[8,5,5]
    assert sites[0].matching_nct_ids==[f'NCT{i:08d}' for i in range(1,9)]
    assert len(sites[0].source_urls)==8
    assert 'Name variants merged' in sites[0].explanation
    assert sites==find_hospitals(trial(),site_client(list(reversed(records))))


def test_normalization_preserves_different_cities_and_unrelated_institutions():
    records=[study(1,'MD Anderson'), study(2,'MD Anderson','Camden','NJ'),
             study(3,'MD Anderson Research Associates'),study(4,'M. D. Anderson',country='US')]
    sites=find_hospitals(trial(),site_client(records))
    assert len(sites)==3
    assert sites[0].historical_trial_count==2
    assert sorted(s.historical_trial_count for s in sites)==[1,1,2]


def located(n, name, lat, lon):
    record = study(n, name)
    record['protocolSection']['contactsLocationsModule']['locations'][0]['geoPoint'] = {'lat': lat, 'lon': lon}
    return record


def test_sites_carry_map_coordinates_independent_of_api_order():
    records = [located(1, 'MD Anderson', 29.7072, -95.3983), located(2, 'M D Anderson', 29.7604, -95.3698),
               study(3, 'Dana-Farber', 'Boston', 'MA')]
    sites = find_hospitals(trial(), site_client(records))
    assert (sites[0].latitude, sites[0].longitude) == (29.7072, -95.3983)
    assert (sites[1].latitude, sites[1].longitude) == (None, None)
    assert sites == find_hospitals(trial(), site_client(list(reversed(records))))
