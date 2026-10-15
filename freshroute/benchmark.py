"""Seeded synthetic stress scenarios. Never claimed as real-world validation."""
from pathlib import Path
import json
import platform
import random
import statistics
import sys

import numpy
import pandas
import scipy

from freshroute.model import Scenario
from freshroute.io import load_scenario, csv_text
from freshroute.engine import baseline, optimize
from freshroute.evaluation import evaluate
from freshroute.scenario import change_scenario


def generated(seed: int = 2307, batches: int = 20, destinations: int = 5) -> Scenario:
    rng = random.Random(seed)
    commodities = ['tomato','banana','spinach']
    data = {'config':{'label':f'Synthetic random seed={seed}','horizon_hours':24,'quantity_unit':'kg','currency':'CU','handling_hours':0.5},
            'inventory':[], 'demand':[], 'routes':[], 'resources':[{'resource_id':'shared','capacity':batches*20}]}
    for i in range(batches):
        data['inventory'].append({'batch_id':f'B{i:05}', 'commodity':rng.choice(commodities), 'quantity':rng.randint(0,100),
                                  'shelf_life_hours':rng.choice([2,6,12,24,48,72]),'handling_cost_per_unit':0.2,'disposal_cost_per_unit':0.5})
    for j in range(destinations):
        for c in commodities:
            data['demand'].append({'destination_id':f'D{j:03}', 'commodity':c,'quantity':rng.randint(0,200),'price_per_unit':rng.randint(1,30)})
        data['routes'].append({'route_id':f'R{j:03}','destination_id':f'D{j:03}','resource_id':'shared',
                               'travel_hours':rng.uniform(1,14),'capacity':rng.randint(30,250),'cost_per_unit':rng.uniform(1,5),'fixed_cost':rng.choice([0,10,30])})
    return Scenario.from_dict(data)


def scenarios(demo: Scenario):
    yield 'normal',demo
    yield 'limited_capacity',change_scenario(demo,capacity_factor=0.2)
    yield 'transport_delay',change_scenario(demo,delay_hours=6)
    yield 'combined_disruption',change_scenario(demo,delay_hours=4,capacity_factor=0.6,demand_factor=0.8,price_factor=0.9,inventory_factor=0.85)
    d = demo.to_dict()
    for b in d['inventory']: b['shelf_life_hours'] = 3
    yield 'high_spoilage',Scenario.from_dict(d)
    d = demo.to_dict()
    for row in d['demand']: row['quantity'] *= 0.1 if row['destination_id']=='Koyambedu' else 3
    yield 'uneven_demand',Scenario.from_dict(d)
    yield 'uneconomic_markdowns',change_scenario(demo,price_factor=0.02)
    yield 'zero_inventory',change_scenario(demo,inventory_factor=0)
    yield 'zero_demand',change_scenario(demo,demand_factor=0)
    yield 'zero_capacity',change_scenario(demo,capacity_factor=0)
    yield 'excess_inventory',change_scenario(demo,inventory_factor=3)
    yield 'excess_demand',change_scenario(demo,demand_factor=3)
    for i in range(10): yield f'seeded_{i}',generated(2307+i)
    yield 'larger_sparse_model',generated(9071,200,25)


def run_benchmark(output: str | Path, inputs: list[str] | None = None, time_limit: float = 15) -> dict:
    output = Path(output); output.mkdir(parents=True,exist_ok=True)
    if inputs:
        cases = [(str(path),load_scenario(path)) for path in inputs]
        evidence = 'User-supplied scenarios; no official scoring metric configured'
    else:
        demo = load_scenario(Path(__file__).resolve().parent.parent/'examples/demo')
        cases = list(scenarios(demo))
        evidence = 'Synthetic validation only; not real-world predictive evidence'
    rows = []
    for name,s in cases:
        b,p = baseline(s), optimize(s,time_limit)
        mb,mp = evaluate(s,b),evaluate(s,p)
        rows.append({'scenario':name,'status':p.status,'mip_gap':p.mip_gap,'baseline_net':mb['net_revenue'],
                     'optimized_net':mp['net_revenue'],'net_change':mp['net_revenue']-mb['net_revenue'],
                     'net_change_percent':100*(mp['net_revenue']-mb['net_revenue'])/abs(mb['net_revenue']) if mb['net_revenue'] else None,
                     'baseline_spoiled':mb['spoiled_quantity'],'optimized_spoiled':mp['spoiled_quantity'],
                     'baseline_fulfillment_percent':mb['demand_fulfillment_percent'],
                     'optimized_fulfillment_percent':mp['demand_fulfillment_percent'],
                     'baseline_transport':mb['transport_expenditure'],'optimized_transport':mp['transport_expenditure'],
                     'baseline_unsold':mb['unsold_quantity'],'optimized_unsold':mp['unsold_quantity'],
                     'baseline_seconds':b.runtime_seconds,'optimized_seconds':p.runtime_seconds,
                     'baseline_violation_count':len(mb['constraint_violations']),
                     'optimized_violation_count':len(mp['constraint_violations']),
                     'diagnostics':mp['constraint_violations']+mb['constraint_violations']})
    summary = {'evidence':evidence,'scenario_count':len(rows),
               'total_net_change':sum(r['net_change'] for r in rows),
               'mean_net_change':statistics.mean(r['net_change'] for r in rows) if rows else 0,
               'revenue_regressions':sum(r['net_change'] < -1e-5 for r in rows),
               'constraint_violations':sum(r['baseline_violation_count']+r['optimized_violation_count'] for r in rows),
               'optimal_count':sum(r['status']=='optimal' for r in rows),
               'fallback_count':sum(r['status']=='fallback' for r in rows),
               'max_runtime_seconds':max((r['optimized_seconds'] for r in rows),default=0),
               'runtime':{'python':sys.version,'platform':platform.platform(),'numpy':numpy.__version__,'pandas':pandas.__version__,'scipy':scipy.__version__},
               'cases':rows}
    (output/'benchmark.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    (output/'benchmark.csv').write_text(csv_text(rows))
    return summary
