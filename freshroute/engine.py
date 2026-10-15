"""Sparse exact allocation model, credible FEFO baseline, validated fallbacks."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field
import logging
from math import floor, isfinite
from time import perf_counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix, vstack

from freshroute.model import Scenario, ValidationError
from freshroute.evaluation import evaluate, TOL

logger = logging.getLogger(__name__)
ECON_TOL = 1e-7


@dataclass(frozen=True)
class Shipment:
    batch_id: str
    route_id: str
    quantity: float


@dataclass
class Plan:
    shipments: list[Shipment]
    status: str
    runtime_seconds: float
    message: str = ''
    mip_gap: float | None = None
    primary_objective: float | None = None
    secondary_status: str = 'not_run'

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    batch_id: str
    route_id: str
    destination_id: str
    resource_id: str
    commodity: str
    unit_gain: float
    unit_margin: float
    shelf_life_hours: float
    arrival_hours: float


def candidates(s: Scenario) -> tuple[list[Candidate], list[dict]]:
    demands = {(d.destination_id, d.commodity): d for d in s.demand}
    resources = {r.resource_id: r for r in s.resources}
    # Only inspect routes for the commodity's destinations; retain explicit rejection evidence.
    arcs, rejected = [], []
    for b in s.inventory:
        for r in s.routes:
            d = demands.get((r.destination_id, b.commodity))
            arrival = r.travel_hours + s.config.handling_hours
            reason = None
            if d is None or (r.commodity and r.commodity != b.commodity): reason = 'No compatible commodity demand on route'
            elif b.quantity == 0: reason = 'Zero batch inventory'
            elif d.quantity == 0: reason = 'Zero destination demand'
            elif r.capacity == 0 or resources[r.resource_id].capacity == 0: reason = 'Zero transport capacity'
            elif arrival >= b.shelf_life_hours: reason = 'Shelf life expires before or at arrival'
            elif arrival > s.config.horizon_hours: reason = 'Arrival outside planning horizon'
            elif b.shelf_life_hours - arrival < d.min_arrival_life_hours: reason = 'Minimum arrival shelf life not met'
            if reason:
                rejected.append({'batch_id': b.batch_id, 'route_id': r.route_id, 'reason': reason})
                continue
            margin = d.price_per_unit - r.cost_per_unit - b.handling_cost_per_unit
            arcs.append(Candidate(b.batch_id, r.route_id, r.destination_id, r.resource_id, b.commodity,
                                  margin + s.residual_cost(b), margin, b.shelf_life_hours, arrival))
    return arcs, rejected


def _greedy(s: Scenario, strategy: str) -> Plan:
    start = perf_counter()
    arcs, _ = candidates(s)
    inventory = {b.batch_id: b.quantity for b in s.inventory}
    demand = {(d.destination_id, d.commodity): d.quantity for d in s.demand}
    route_cap = {r.route_id: r.capacity for r in s.routes}
    resource_cap = {r.resource_id: r.capacity for r in s.resources}
    fixed = {r.route_id: r.fixed_cost for r in s.routes}
    active = set(); shipments = []
    if strategy == 'fefo':
        arcs.sort(key=lambda c: (c.shelf_life_hours, c.batch_id, -c.unit_gain, c.arrival_hours, c.route_id))
    else:
        arcs.sort(key=lambda c: (-c.unit_gain, c.shelf_life_hours, c.batch_id, c.route_id))
    for c in arcs:
        key = (c.destination_id, c.commodity)
        q = min(inventory[c.batch_id], demand[key], route_cap[c.route_id], resource_cap[c.resource_id])
        if s.config.integer_quantities: q = floor(q)
        activation = fixed[c.route_id] if c.route_id not in active else 0
        if q <= 0 or q * c.unit_gain - activation <= 0: continue
        shipments.append(Shipment(c.batch_id, c.route_id, q)); active.add(c.route_id)
        inventory[c.batch_id] -= q; demand[key] -= q; route_cap[c.route_id] -= q; resource_cap[c.resource_id] -= q
    plan = Plan(shipments, strategy, perf_counter() - start, 'FEFO, best feasible contribution first' if strategy == 'fefo' else 'Margin greedy')
    violations = evaluate(s, plan)['constraint_violations']
    if violations: raise RuntimeError(f'Internal greedy feasibility error: {violations}')
    return plan


def baseline(s: Scenario) -> Plan:
    return _greedy(s, 'fefo')


def optimize(s: Scenario, time_limit: float = 15) -> Plan:
    if not isinstance(time_limit, (int, float)) or not isfinite(time_limit) or time_limit <= 0:
        raise ValidationError('time_limit: expected finite positive seconds')
    start = perf_counter()
    backups = [baseline(s), _greedy(s, 'margin'), Plan([], 'empty', 0)]
    backup = max(backups, key=lambda p: evaluate(s, p)['net_revenue'])
    arcs, _ = candidates(s)
    constant = -sum(b.quantity * s.residual_cost(b) for b in s.inventory)
    if not arcs:
        return Plan([], 'optimal', perf_counter() - start, 'No feasible sales arcs; empty dispatch is optimal', 0, constant, 'unnecessary')
    n = len(arcs)
    routes = {r.route_id: r for r in s.routes}
    fixed_routes = sorted({c.route_id for c in arcs if routes[c.route_id].fixed_cost > 0})
    activation_index = {key: n + i for i, key in enumerate(fixed_routes)}
    size = n + len(fixed_routes)
    gain = np.zeros(size)
    upper = np.ones(size)
    integers = np.zeros(size, dtype=np.uint8)
    stocks = {b.batch_id: b.quantity for b in s.inventory}
    demands = {(d.destination_id, d.commodity): d.quantity for d in s.demand}
    capacities = {r.resource_id: r.capacity for r in s.resources}
    row_ids, col_ids, values, limits = [], [], [], []
    rows = {}
    for kind, table in [('batch', stocks), ('demand', demands), ('route', {r.route_id:r.capacity for r in s.routes}), ('resource', capacities)]:
        for key, limit in table.items():
            rows[(kind, key)] = len(limits); limits.append(limit)
    for j, c in enumerate(arcs):
        key = (c.destination_id, c.commodity)
        upper[j] = min(stocks[c.batch_id], demands[key], routes[c.route_id].capacity, capacities[c.resource_id])
        gain[j] = c.unit_gain
        integers[j] = int(s.config.integer_quantities)
        for kind, k in [('batch', c.batch_id), ('demand', key), ('route', c.route_id), ('resource', c.resource_id)]:
            row_ids.append(rows[(kind, k)]); col_ids.append(j); values.append(1.0)
    for key, j in activation_index.items():
        gain[j] = -routes[key].fixed_cost; integers[j] = 1
        # Existing route capacity row becomes sum(x) - cap*y <= 0.
        row = rows[('route', key)]
        row_ids.append(row); col_ids.append(j); values.append(-routes[key].capacity); limits[row] = 0
    matrix = coo_matrix((values, (row_ids, col_ids)), shape=(len(limits), size)).tocsc()
    constraints = LinearConstraint(matrix, np.full(len(limits), -np.inf), np.asarray(limits))
    bounds = Bounds(np.zeros(size), upper)

    def extract(vector, status, message, gap=None):
        if vector is None or len(vector) != size or not np.isfinite(vector).all():
            raise RuntimeError('Solver provided no finite incumbent')
        shipments = []
        for c, q in zip(arcs, vector[:n]):
            if q < -TOL: raise RuntimeError('Solver returned negative quantity')
            if s.config.integer_quantities:
                if abs(q - round(q)) > TOL: raise RuntimeError('Solver returned noninteger quantity')
                q = float(round(q))
            if q > 1e-9: shipments.append(Shipment(c.batch_id, c.route_id, float(q)))
        plan = Plan(shipments, status, 0, message, gap)
        violations = evaluate(s, plan)['constraint_violations']
        if violations: raise RuntimeError(f'Solver incumbent failed independent checks: {violations}')
        return plan

    plan = None
    try:
        logger.info('Solving sparse model: %d arcs, %d binary activations, %d constraints', n, len(fixed_routes), len(limits))
        result = milp(-gain, integrality=integers, bounds=bounds, constraints=constraints,
                      options={'time_limit': float(time_limit), 'mip_rel_gap': 0.0, 'presolve': True})
        gap_value = getattr(result, 'mip_gap', None)
        gap = float(gap_value) if gap_value is not None and isfinite(gap_value) else None
        status = 'optimal' if result.status == 0 else 'feasible_limit'
        if result.status not in (0, 1): raise RuntimeError(f'Solver status {result.status}: {result.message}')
        plan = extract(result.x, status, str(result.message), gap)
        primary_gain = float(gain @ result.x)
        plan.primary_objective = primary_gain + constant
        remaining_time = time_limit - (perf_counter() - start)
        if result.status == 0 and remaining_time > 0.01:
            priority_batches = sorted(s.inventory, key=lambda b:(b.shelf_life_hours, b.batch_id))
            priority = {b.batch_id: (len(priority_batches)-i) for i,b in enumerate(priority_batches)}
            secondary = np.zeros(size)
            for j,c in enumerate(arcs):
                secondary[j] = -(priority[c.batch_id] + (n-j)/(n+1)**2)
            tied_matrix = vstack([matrix, csr_matrix(gain.reshape(1, -1))], format='csc')
            tied = LinearConstraint(tied_matrix, np.r_[np.full(len(limits), -np.inf), primary_gain], np.r_[limits, np.inf])
            try:
                second = milp(secondary, integrality=integers, bounds=bounds, constraints=tied,
                              options={'time_limit': float(remaining_time), 'mip_rel_gap': 0.0})
                if second.status == 0:
                    chosen = extract(second.x, 'optimal', str(result.message), gap)
                    if evaluate(s, chosen)['net_revenue'] >= evaluate(s, plan)['net_revenue'] - 1e-9:
                        chosen.primary_objective = plan.primary_objective
                        chosen.secondary_status = 'optimal'; plan = chosen
                    else: plan.secondary_status = 'rejected_economic_drift'
                else: plan.secondary_status = f'status_{second.status}; primary retained'
            except Exception as exc:
                plan.secondary_status = f'failed; primary retained: {exc}'
        backup_value = evaluate(s, backup)['net_revenue']
        if evaluate(s, plan)['net_revenue'] < backup_value - TOL:
            raise RuntimeError('Solver incumbent is economically worse than validated fallback')
        # Keep better fallback even on a timeout, without claiming an optimality certificate for it.
        if plan.status != 'optimal' and backup_value > evaluate(s, plan)['net_revenue']:
            raise RuntimeError('Time-limited incumbent improved by validated fallback')
    except Exception as exc:
        logger.warning('Optimization fallback: %s', exc)
        plan = Plan(list(backup.shipments), 'fallback', 0, str(exc))
    plan.runtime_seconds = perf_counter() - start
    logger.info('Plan status=%s net=%.6f runtime=%.4fs', plan.status, evaluate(s, plan)['net_revenue'], plan.runtime_seconds)
    return plan
