import copy
import itertools
import math
import random

import pytest

from freshroute.model import Scenario, ValidationError
from freshroute.engine import baseline, optimize, candidates, Plan, Shipment
from freshroute.evaluation import evaluate, compare
from freshroute.insights import discounts, explain
from freshroute.scenario import replan, change_scenario


def data():
    return {
        'config': {'horizon_hours': 24, 'quantity_unit': 'kg', 'currency': 'CU'},
        'inventory': [
            {'batch_id': 'old', 'commodity': 'tomato', 'quantity': 10, 'shelf_life_hours': 8},
            {'batch_id': 'new', 'commodity': 'tomato', 'quantity': 10, 'shelf_life_hours': 48}],
        'demand': [
            {'destination_id': 'near', 'commodity': 'tomato', 'quantity': 10, 'price_per_unit': 5},
            {'destination_id': 'far', 'commodity': 'tomato', 'quantity': 10, 'price_per_unit': 12}],
        'routes': [
            {'route_id': 'a', 'destination_id': 'near', 'resource_id': 'truck', 'travel_hours': 2, 'capacity': 20, 'cost_per_unit': 1},
            {'route_id': 'b', 'destination_id': 'far', 'resource_id': 'truck', 'travel_hours': 10, 'capacity': 20, 'cost_per_unit': 2}],
        'resources': [{'resource_id': 'truck', 'capacity': 15}]
    }


def scenario(d=None):
    return Scenario.from_dict(data() if d is None else d)


def test_baseline_and_known_optimum():
    s = scenario()
    b, p = baseline(s), optimize(s)
    assert evaluate(s, b)['net_revenue'] == pytest.approx(90)
    assert evaluate(s, p)['net_revenue'] == pytest.approx(120)
    assert p.status == 'optimal'
    assert evaluate(s, p)['constraint_violations'] == []
    assert evaluate(s, p)['spoiled_quantity'] == pytest.approx(5)
    assert evaluate(s, p)['viable_remaining_quantity'] == pytest.approx(0)
    assert compare(s, b, p)['net_revenue']['absolute_change'] == pytest.approx(30)


@pytest.mark.parametrize('field,value', [('quantity', -1), ('quantity', float('nan')), ('shelf_life_hours', -1), ('quantity', True)])
def test_reject_invalid_inventory(field, value):
    d = data(); d['inventory'][0][field] = value
    with pytest.raises(ValidationError, match=field): scenario(d)


def test_missing_and_duplicates_and_foreign_keys():
    for section, field in [('inventory', 'commodity'), ('demand', 'price_per_unit'), ('routes', 'travel_hours')]:
        d = data(); del d[section][0][field]
        with pytest.raises(ValidationError, match=field): scenario(d)
    d = data(); d['inventory'].append(d['inventory'][0].copy())
    with pytest.raises(ValidationError, match='duplicate'): scenario(d)
    d = data(); d['routes'][0]['resource_id'] = 'missing'
    with pytest.raises(ValidationError, match='resource'): scenario(d)


def test_expiry_horizon_handling_and_commodity():
    d = data(); d['routes'][0]['travel_hours'] = 8; d['routes'][1]['travel_hours'] = 48
    s = scenario(d)
    assert all(c.batch_id != 'old' for c in candidates(s)[0])
    p = optimize(s)
    assert evaluate(s, p)['spoiled_quantity'] == 10
    d['routes'][0]['travel_hours'] = 1
    d['config']['handling_hours'] = 7
    assert all(c.batch_id != 'old' for c in candidates(scenario(d))[0])
    d['inventory'][0]['commodity'] = 'banana'
    assert all(c.batch_id != 'old' for c in candidates(scenario(d))[0])
    d['config']['horizon_hours'] = 1
    assert optimize(scenario(d)).shipments == []


@pytest.mark.parametrize('section', ['inventory', 'demand', 'routes', 'resources'])
def test_empty_inputs(section):
    d = data(); d[section] = []
    if section == 'resources': d['routes'] = []
    s = scenario(d)
    p = optimize(s)
    assert evaluate(s, p)['constraint_violations'] == []


def test_fixed_cost_and_integer_model():
    d = data(); d['routes'][1]['fixed_cost'] = 200
    s = scenario(d); p = optimize(s)
    assert evaluate(s, p)['net_revenue'] == pytest.approx(40)
    assert all(x.route_id == 'a' for x in p.shipments)
    d = data(); d['config']['integer_quantities'] = True; d['resources'][0]['capacity'] = 1.7
    s = scenario(d); p = optimize(s)
    assert sum(x.quantity for x in p.shipments) == pytest.approx(1)
    assert evaluate(s, p)['net_revenue'] == pytest.approx(10)


def test_penalties_and_no_forced_loss_sales():
    d = data(); d['demand'][0]['price_per_unit'] = 0; d['demand'][1]['price_per_unit'] = 0
    s = scenario(d)
    assert optimize(s).shipments == []
    d['inventory'][0]['disposal_cost_per_unit'] = 3
    s = scenario(d); p = optimize(s)
    assert evaluate(s, p)['net_revenue'] == pytest.approx(-10)
    assert evaluate(s, p)['disposal_cost'] == pytest.approx(0)
    assert sum(x.quantity for x in p.shipments) == pytest.approx(10)


def test_independent_validator_detects_bad_plans():
    s = scenario()
    p = Plan([Shipment('old', 'b', 30), Shipment('new', 'a', -1)], 'test', 0)
    violations = evaluate(s, p)['constraint_violations']
    assert len(violations) >= 4
    assert any('shelf' in x for x in violations)
    assert any('inventory' in x for x in violations)
    assert any('capacity' in x for x in violations)
    assert any('negative' in x for x in violations)


def test_bruteforce_small_integer_cases():
    rng = random.Random(421)
    for _ in range(16):
        d = data(); d['config']['integer_quantities'] = True
        for b in d['inventory']: b['quantity'] = rng.randint(0, 2)
        for r in d['routes']: r['fixed_cost'] = rng.randint(0, 5)
        d['resources'][0]['capacity'] = rng.randint(0, 3)
        s = scenario(d)
        best = -math.inf
        arcs, _ = candidates(s)
        for quantities in itertools.product(range(3), repeat=len(arcs)):
            p = Plan([Shipment(c.batch_id, c.route_id, q) for c, q in zip(arcs, quantities) if q], 'enumerated', 0)
            m = evaluate(s, p)
            if not m['constraint_violations']: best = max(best, m['net_revenue'])
        assert evaluate(s, optimize(s))['net_revenue'] == pytest.approx(best, abs=1e-5)


def test_randomized_feasibility_and_baseline_dominance():
    rng = random.Random(812)
    for _ in range(35):
        d = data()
        for b in d['inventory']:
            b['quantity'] = rng.uniform(0, 100); b['shelf_life_hours'] = rng.uniform(0, 50)
        for row in d['demand']:
            row['quantity'] = rng.uniform(0, 100); row['price_per_unit'] = rng.uniform(0, 20)
        for r in d['routes']:
            r['capacity'] = rng.uniform(0, 100); r['fixed_cost'] = rng.uniform(0, 20)
        d['resources'][0]['capacity'] = rng.uniform(0, 100)
        s = scenario(d); b, p = baseline(s), optimize(s)
        mb, mp = evaluate(s, b), evaluate(s, p)
        assert not mb['constraint_violations'] and not mp['constraint_violations']
        assert mp['net_revenue'] >= mb['net_revenue'] - 1e-5
        assert mp['shipped_quantity'] + mp['unsold_quantity'] == pytest.approx(mp['inventory_quantity'])


def test_solver_failure_fallback(monkeypatch):
    import freshroute.engine as engine
    def fail(*args, **kwargs): raise RuntimeError('test failure')
    monkeypatch.setattr(engine, 'milp', fail)
    s = scenario(); p = optimize(s)
    assert p.status == 'fallback'
    assert 'test failure' in p.message
    assert not evaluate(s, p)['constraint_violations']


def test_replan_does_not_mutate_inputs_and_checks_previous_plan():
    s = scenario(); old = optimize(s)
    changed = change_scenario(s, delay_hours=12, capacity_factor=0.5, demand_factor=0.8, price_factor=0.9, inventory_factor=0.9)
    result = replan(s, old, changed)
    assert s.routes[0].travel_hours == 2
    assert result['previous_plan_feasible'] is False
    assert result['changes']
    assert not evaluate(changed, result['plan'])['constraint_violations']
    with pytest.raises(ValidationError): change_scenario(s, capacity_factor=-1)


def test_discounts_are_explicit_scenarios_not_automatic_sales():
    s = scenario(); p = optimize(s)
    rows = discounts(s, p)
    assert rows and rows[0]['batch_id'] == 'old'
    assert rows[0]['evidence'] == 'scenario_only'
    assert rows[0]['additional_sales_assumed'] == 0
    assert 'unverified' in rows[0]['reason'].lower()
    assert explain(s, p)['shipments']


def test_zero_baseline_percent_is_none():
    d = data(); d['inventory'] = []
    s = scenario(d)
    assert compare(s, baseline(s), optimize(s))['net_revenue']['percent_change'] is None
