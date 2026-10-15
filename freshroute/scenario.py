"""Pure transformations for an unexecuted planning sandbox."""
from math import isfinite
from freshroute.model import Scenario, ValidationError
from freshroute.engine import Plan, optimize
from freshroute.evaluation import evaluate
from freshroute.insights import shipment_rows


def change_scenario(s: Scenario, *, delay_hours: float = 0, capacity_factor: float = 1,
                    demand_factor: float = 1, price_factor: float = 1,
                    inventory_factor: float = 1, route_id: str | None = None) -> Scenario:
    values = dict(delay_hours=delay_hours, capacity_factor=capacity_factor, demand_factor=demand_factor,
                  price_factor=price_factor, inventory_factor=inventory_factor)
    for name,value in values.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value < 0:
            raise ValidationError(f'{name}: expected a finite nonnegative number')
    if route_id is not None and route_id not in {r.route_id for r in s.routes}:
        raise ValidationError(f'route_id: unknown route {route_id!r}')
    data = s.to_dict()
    for r in data['routes']:
        if route_id is None or r['route_id'] == route_id: r['travel_hours'] += delay_hours
        r['capacity'] *= capacity_factor
    for r in data['resources']: r['capacity'] *= capacity_factor
    for d in data['demand']:
        d['quantity'] *= demand_factor; d['price_per_unit'] *= price_factor
    for b in data['inventory']: b['quantity'] *= inventory_factor
    data['config']['label'] += ' / disruption'
    return Scenario.from_dict(data)


def replan(previous: Scenario, previous_plan: Plan, updated: Scenario, time_limit: float = 15) -> dict:
    previous_checks = evaluate(updated, previous_plan)
    plan = optimize(updated, time_limit)
    old = {(x.batch_id,x.route_id):x.quantity for x in previous_plan.shipments}
    new = {(x.batch_id,x.route_id):x.quantity for x in plan.shipments}
    changes = [{'batch_id':b,'route_id':r,'previous_quantity':old.get((b,r),0),'updated_quantity':new.get((b,r),0),
                'quantity_change':new.get((b,r),0)-old.get((b,r),0),
                'reason':'Reoptimized jointly under updated travel times, capacity, demand, prices and inventory; see current constraints and rejections.'}
               for b,r in sorted(set(old)|set(new)) if abs(new.get((b,r),0)-old.get((b,r),0))>1e-6]
    return {'plan':plan, 'previous_plan_feasible':not previous_checks['constraint_violations'],
            'previous_plan_violations':previous_checks['constraint_violations'],
            'previous_original_metrics':evaluate(previous,previous_plan),
            'previous_plan_on_updated_inputs': previous_checks if not previous_checks['constraint_violations'] else None,
            'updated_metrics':evaluate(updated,plan),'changes':changes}
