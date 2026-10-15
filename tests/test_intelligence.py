import json
import pytest
from freshroute.intelligence import review_extraction, apply_extraction, apply_operations, evidence
from freshroute.model import ValidationError
from freshroute.webbridge import run
from test_engine import data,scenario


def extraction():
    return {'source_id':'note-1','records':[{'kind':'inventory','commodity':'tomato','quantity':120,'quantity_unit':'kg','remaining_life':2,'life_unit':'days','source_refs':{},'ambiguities':[]}],'issues':[],'unresolved':[]}


def test_review_converts_explicit_units_and_requires_confirmation():
    s=scenario();review=review_extraction(s,extraction())
    assert review['draft']['inventory'][0]['shelf_life_hours']==48
    with pytest.raises(ValidationError,match='confirm'):apply_extraction(s,review['draft'],False,'replace')
    updated=apply_extraction(s,review['draft'],True,'replace')
    assert updated.inventory[0].quantity==120
    assert s.inventory[0].quantity==10


def test_missing_quantity_and_ambiguous_units_cannot_be_committed():
    for field,value in [('quantity',None),('quantity_unit','boxes'),('remaining_life',None),('commodity','cement')]:
        raw=extraction();raw['records'][0][field]=value
        review=review_extraction(scenario(),raw)
        assert review['issues']
        with pytest.raises(ValidationError):apply_extraction(scenario(),review['draft'],True,'replace')


def test_duplicate_ids_and_invalid_changes_are_rejected():
    review=review_extraction(scenario(),extraction());draft=review['draft'];draft['inventory'].append(draft['inventory'][0].copy())
    with pytest.raises(ValidationError):apply_extraction(scenario(),draft,True,'replace')
    with pytest.raises(ValidationError):apply_operations(scenario(),[{'op':'delete_everything'}],True)
    with pytest.raises(ValidationError):apply_operations(scenario(),[{'op':'delay_route','route_id':'absent','hours':3}],True)
    with pytest.raises(ValidationError):apply_operations(scenario(),[{'op':'scale_capacity','resource_id':None,'factor':-1}],True)


def test_targeted_whatif_is_safe_and_preserves_original():
    s=scenario()
    with pytest.raises(ValidationError,match='confirm'):apply_operations(s,[{'op':'delay_route','route_id':'a','hours':3}],False)
    updated=apply_operations(s,[{'op':'delay_route','route_id':'a','hours':3},{'op':'scale_demand','commodity':'tomato','destination_id':'near','factor':1.2}],True)
    assert updated.routes[0].travel_hours==5
    assert next(d for d in updated.demand if d.destination_id=='near').quantity==12
    assert s.routes[0].travel_hours==2


def test_evidence_recomputes_metrics_instead_of_trusting_supplied_numbers():
    report=json.loads(run(json.dumps(data())));report['optimized_metrics']['net_revenue']=999999
    facts=evidence(report)
    assert any(f['id']=='metrics.net_revenue' and '120' in f['text'] for f in facts)
    assert all('999999' not in f['text'] for f in facts)


def test_demand_import_preserves_existing_delivery_constraints():
    raw=data();raw['demand'][0]['min_arrival_life_hours']=12
    s=scenario(raw)
    draft={'inventory':[],'demand':[{'destination_id':'near','commodity':'tomato','quantity':8,'price_per_unit':6}],'price_updates':[]}
    updated=apply_extraction(s,draft,True,'append')
    demand=next(d for d in updated.demand if d.destination_id=='near')
    assert demand.min_arrival_life_hours==12
    assert demand.quantity==8 and demand.price_per_unit==6


def test_duplicate_price_updates_require_manual_resolution():
    price={'destination_id':'near','commodity':'tomato','price_per_unit':6}
    draft={'inventory':[],'demand':[],'price_updates':[price,{**price,'price_per_unit':7}]}
    with pytest.raises(ValidationError,match='Duplicate.*price'):
        apply_extraction(scenario(),draft,True,'append')
