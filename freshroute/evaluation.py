"""Independent accounting and constraint validation, deliberately without solver imports."""
from collections import defaultdict
from math import isfinite
from typing import TYPE_CHECKING
from freshroute.model import Scenario

if TYPE_CHECKING:
    from freshroute.engine import Plan

TOL = 1e-6  # absolute quantity tolerance, also used for integer residuals


def evaluate(s: Scenario, plan: 'Plan') -> dict:
    batches = {b.batch_id: b for b in s.inventory}
    routes = {r.route_id: r for r in s.routes}
    demand = {(d.destination_id, d.commodity): d for d in s.demand}
    used_batch, used_route, used_resource, used_demand = (defaultdict(float) for _ in range(4))
    violations = []
    sales = transport = handling = 0.0
    for i, shipment in enumerate(plan.shipments):
        q = shipment.quantity
        if not isinstance(q, (int, float)) or not isfinite(q):
            violations.append(f'shipment[{i}]: nonfinite/invalid quantity'); continue
        if q < 0:
            violations.append(f'shipment[{i}]: negative quantity')
        if s.config.integer_quantities and abs(q - round(q)) > TOL:
            violations.append(f'shipment[{i}]: noninteger quantity')
        b, r = batches.get(shipment.batch_id), routes.get(shipment.route_id)
        if b is None or r is None:
            violations.append(f'shipment[{i}]: unknown batch or route'); continue
        key = (r.destination_id, b.commodity)
        d = demand.get(key)
        arrival = r.travel_hours + s.config.handling_hours
        if q > 0:
            if arrival >= b.shelf_life_hours:
                violations.append(f'{b.batch_id}/{r.route_id}: shelf life expires before or at arrival')
            if arrival > s.config.horizon_hours:
                violations.append(f'{b.batch_id}/{r.route_id}: arrival outside horizon')
            if d is None or (r.commodity and r.commodity != b.commodity):
                violations.append(f'{b.batch_id}/{r.route_id}: incompatible commodity/demand')
            elif b.shelf_life_hours - arrival < d.min_arrival_life_hours:
                violations.append(f'{b.batch_id}/{r.route_id}: minimum arrival shelf life not met')
        used_batch[b.batch_id] += q
        used_route[r.route_id] += q
        used_resource[r.resource_id] += q
        used_demand[key] += q
        sales += q * (d.price_per_unit if d else 0)
        transport += q * r.cost_per_unit
        handling += q * b.handling_cost_per_unit
    for b in s.inventory:
        if used_batch[b.batch_id] > b.quantity + TOL:
            violations.append(f'{b.batch_id}: inventory exceeded')
    for r in s.routes:
        if used_route[r.route_id] > r.capacity + TOL:
            violations.append(f'{r.route_id}: route capacity exceeded')
        if used_route[r.route_id] > 0:
            transport += r.fixed_cost
    for r in s.resources:
        if used_resource[r.resource_id] > r.capacity + TOL:
            violations.append(f'{r.resource_id}: shared resource capacity exceeded')
    for key, q in used_demand.items():
        if q > (demand[key].quantity if key in demand else 0) + TOL:
            violations.append(f'{key}: demand exceeded')
    inventory_quantity = sum(b.quantity for b in s.inventory)
    demand_quantity = sum(d.quantity for d in s.demand)
    shipped = sum(used_batch.values())
    unsold = inventory_quantity - shipped
    spoiled = viable = disposal = storage = 0.0
    for b in s.inventory:
        remaining = max(0.0, b.quantity - used_batch[b.batch_id])
        if b.shelf_life_hours <= s.config.horizon_hours:
            spoiled += remaining; disposal += remaining * b.disposal_cost_per_unit
        else:
            viable += remaining; storage += remaining * b.storage_cost_per_unit
    if abs(shipped + spoiled + viable - inventory_quantity) > TOL:
        violations.append('inventory balance not preserved')
    return {
        'net_revenue': sales - transport - handling - disposal - storage,
        'sales_revenue': sales, 'transport_expenditure': transport,
        'handling_cost': handling, 'disposal_cost': disposal, 'storage_cost': storage,
        'inventory_quantity': inventory_quantity, 'demand_quantity': demand_quantity,
        'shipped_quantity': shipped, 'unsold_quantity': unsold,
        'spoiled_quantity': spoiled, 'viable_remaining_quantity': viable,
        'demand_fulfillment_percent': (100 * shipped / demand_quantity) if demand_quantity else 0.0,
        'constraint_violations': violations, 'execution_seconds': plan.runtime_seconds,
    }


def compare(s: Scenario, baseline: 'Plan', optimized: 'Plan') -> dict:
    before, after = evaluate(s, baseline), evaluate(s, optimized)
    return {key: {'baseline': before[key], 'optimized': after[key],
                  'absolute_change': after[key] - before[key],
                  'percent_change': 100 * (after[key] - before[key]) / abs(before[key]) if before[key] != 0 else None}
            for key in before if key != 'constraint_violations'}


def utilization(s: Scenario, plan: 'Plan') -> list[dict]:
    route_used = defaultdict(float); resource_used = defaultdict(float); batch_used = defaultdict(float); demand_used = defaultdict(float)
    routes = {r.route_id: r for r in s.routes}; batches = {b.batch_id: b for b in s.inventory}
    for x in plan.shipments:
        r, b = routes[x.route_id], batches[x.batch_id]
        route_used[x.route_id] += x.quantity; resource_used[r.resource_id] += x.quantity
        batch_used[b.batch_id] += x.quantity; demand_used[(r.destination_id, b.commodity)] += x.quantity
    rows = []
    for kind, objects, used, key in [
        ('route', s.routes, route_used, lambda v: v.route_id),
        ('resource', s.resources, resource_used, lambda v: v.resource_id),
        ('inventory', s.inventory, batch_used, lambda v: v.batch_id),
        ('demand', s.demand, demand_used, lambda v: (v.destination_id, v.commodity))]:
        for v in objects:
            cap = v.capacity if kind in ('route', 'resource') else v.quantity
            amount = used[key(v)]
            rows.append({'constraint': kind, 'id': str(key(v)), 'used': amount, 'limit': cap,
                         'slack': cap - amount, 'binding': abs(cap - amount) <= TOL})
    return rows
