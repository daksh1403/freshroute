"""Deterministic explanations and explicitly unverified markdown scenarios."""
from collections import defaultdict
from freshroute.engine import Plan, candidates
from freshroute.evaluation import utilization
from freshroute.model import Scenario


def shipment_rows(s: Scenario, plan: Plan) -> list[dict]:
    batches = {b.batch_id:b for b in s.inventory}; routes = {r.route_id:r for r in s.routes}
    demand = {(d.destination_id,d.commodity):d for d in s.demand}
    route_quantity = defaultdict(float)
    for x in plan.shipments: route_quantity[x.route_id] += x.quantity
    rows = []
    # Expiry-first loading priority is explicit and does not imply multiple dispatch times.
    for order, x in enumerate(sorted(plan.shipments, key=lambda x:(batches[x.batch_id].shelf_life_hours, x.batch_id, x.route_id)), 1):
        b, r = batches[x.batch_id], routes[x.route_id]; d = demand[(r.destination_id,b.commodity)]
        fixed_share = r.fixed_cost * x.quantity / route_quantity[r.route_id]
        sales = x.quantity * d.price_per_unit
        cost = x.quantity * (r.cost_per_unit+b.handling_cost_per_unit) + fixed_share
        arrival = r.travel_hours+s.config.handling_hours
        rows.append({'dispatch_priority':order, 'batch_id':x.batch_id, 'commodity':b.commodity,
                     'destination_id':r.destination_id, 'route_id':r.route_id, 'resource_id':r.resource_id,
                     'quantity':x.quantity, 'arrival_hours':arrival, 'life_on_arrival_hours':b.shelf_life_hours-arrival,
                     'sales_revenue':sales, 'transport_cost':x.quantity*r.cost_per_unit+fixed_share,
                     'handling_cost':x.quantity*b.handling_cost_per_unit,
                     'sales_contribution':sales-cost,
                     'avoided_remaining_cost':x.quantity*s.residual_cost(b)})
    return rows


def explain(s: Scenario, plan: Plan) -> dict:
    arcs, rejected = candidates(s)
    rows = shipment_rows(s, plan)
    explanations = []
    for row in rows:
        explanations.append({**row, 'reason': (
            f"Batch {row['batch_id']} can reach {row['destination_id']} in {row['arrival_hours']:g} hours "
            f"with {row['life_on_arrival_hours']:g} hours of shelf life remaining. "
            f"This feasible allocation serves {row['quantity']:g} {s.config.quantity_unit} of commodity demand "
            f"and contributes {row['sales_contribution']:.2f} {s.config.currency} after transport and handling, "
            f"plus {row['avoided_remaining_cost']:.2f} in avoided remaining-stock costs. "
            f"{'Selected by the joint economic optimization.' if plan.status == 'optimal' else 'Selected by the reported feasible planning method.'}")})
    used = defaultdict(float)
    for x in plan.shipments: used[x.batch_id] += x.quantity
    not_shipped = []
    checks = utilization(s, plan)
    binding = [v for v in checks if v['binding']]
    for b in s.inventory:
        remaining = max(0,b.quantity-used[b.batch_id])
        if remaining <= 1e-6: continue
        available = [c for c in arcs if c.batch_id == b.batch_id]
        if not available:
            reason = 'No feasible delivery arc; inspect route rejection reasons.'
        else:
            route_ids = {c.route_id for c in available}; resources = {c.resource_id for c in available}
            bottlenecks = [f"{v['constraint']} {v['id']}" for v in binding if
                           (v['constraint']=='route' and v['id'] in route_ids) or
                           (v['constraint']=='resource' and v['id'] in resources) or
                           (v['constraint']=='demand' and any(v['id']==str((c.destination_id,c.commodity)) for c in available))]
            reason = ('Relevant limits are binding: '+', '.join(bottlenecks)+'. ') if bottlenecks else ''
            reason += 'Remaining allocations compete on net contribution, including route activation and remaining-stock costs.'
        not_shipped.append({'batch_id':b.batch_id,'quantity':remaining, 'expires_by_horizon':b.shelf_life_hours<=s.config.horizon_hours, 'reason':reason})
    return {'shipments':explanations, 'rejected_allocations':rejected, 'remaining_inventory':not_shipped,
            'constraint_utilization':checks, 'solver_status':plan.status, 'solver_message':plan.message}


def discounts(s: Scenario, plan: Plan) -> list[dict]:
    """No elasticity data => no demand uplift enters optimization or measured metrics."""
    used = defaultdict(float)
    for x in plan.shipments: used[x.batch_id] += x.quantity
    arcs, _ = candidates(s)
    routes = {r.route_id:r for r in s.routes}
    demand = {(d.destination_id,d.commodity):d for d in s.demand}
    result = []
    for b in s.inventory:
        remaining = max(0,b.quantity-used[b.batch_id])
        if remaining <= 1e-6 or b.shelf_life_hours > s.config.horizon_hours: continue
        choices = []
        for c in arcs:
            if c.batch_id != b.batch_id: continue
            r = routes[c.route_id]; d = demand[(c.destination_id,b.commodity)]
            # Illustrative separate markdown shipment: do not assume spare capacity or paid activation.
            sample_q = min(remaining,r.capacity,next(v.capacity for v in s.resources if v.resource_id==r.resource_id))
            if s.config.integer_quantities: sample_q = int(sample_q)
            if sample_q <= 0: continue
            unit_cost = r.cost_per_unit+b.handling_cost_per_unit+r.fixed_cost/sample_q
            for markdown in (0.05,0.10,0.15):
                price = d.price_per_unit*(1-markdown)
                margin = price-unit_cost
                if margin >= 0 and price > 0:
                    choices.append((markdown, margin, c.route_id, d.price_per_unit, unit_cost))
        common = {'batch_id':b.batch_id,'at_risk_quantity':remaining,'evidence':'scenario_only', 'additional_sales_assumed':0}
        if not choices:
            result.append({**common, 'suggested_discount_percent':None, 'route_id':None,
                           'discounted_price_per_unit':None, 'break_even_quantity_multiplier':None,
                           'reason':'No tested markdown preserves nonnegative contribution on a feasible route. Markdown demand response is unverified; fix logistics or margin first.'})
            continue
        pct, margin, route_id, original, cost = max(choices, key=lambda x:(x[0],x[1],x[2]))
        ratio = (original-cost)/margin if margin > 0 else None
        result.append({**common,'suggested_discount_percent':100*pct,'route_id':route_id,
                       'discounted_price_per_unit':original*(1-pct), 'break_even_quantity_multiplier':ratio,
                       'reason':f'{remaining:g} {s.config.quantity_unit} expires within {s.config.horizon_hours:g} hours. '
                                f'{pct:.0%} is the largest tested markdown among 5/10/15% with nonnegative illustrative contribution '
                                f'on route {route_id}, including a separate activation cost. Demand response is unverified; '
                                'confirm customers and spare transport capacity before acting. No extra sales enter plan metrics.'})
    return result
