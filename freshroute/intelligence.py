"""Deterministic boundary between untrusted AI proposals and the existing optimizer."""
from collections import defaultdict
from math import isfinite
import re

from freshroute.model import Scenario, ValidationError
from freshroute.engine import Plan, Shipment
from freshroute.evaluation import evaluate, compare
from freshroute.insights import explain

UNIT_KG={'kg':1,'kilogram':1,'kilograms':1,'g':0.001,'gram':0.001,'grams':0.001,'tonne':1000,'tonnes':1000,'t':1000}


def _factor(source, target):
    if not isinstance(source,str): raise ValidationError('Missing quantity unit; no unit is inferred')
    source,target=source.lower().strip(),target.lower().strip()
    if source==target:return 1
    if source in UNIT_KG and target in UNIT_KG:return UNIT_KG[source]/UNIT_KG[target]
    raise ValidationError(f'Cannot convert {source!r} to {target!r}; boxes/crates need a documented conversion')


def _number(value,name,max_value=1e9):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not 0<=value<=max_value:
        raise ValidationError(f'{name}: expected finite nonnegative number')
    return float(value)


def review_extraction(s:Scenario, proposal:dict)->dict:
    draft={'inventory':[],'demand':[],'price_updates':[]}
    issues=list(proposal.get('issues',[]))+list(proposal.get('unresolved',[]));provenance=[]
    known={b.commodity for b in s.inventory}|{d.commodity for d in s.demand}
    destinations={d.destination_id for d in s.demand}
    source_id=re.sub(r'[^A-Za-z0-9_-]','',proposal.get('source_id','source'))[:40] or 'source'
    for index,r in enumerate(proposal.get('records',[])):
        item=f'record {index+1}';issues.extend(f'{item}: {v}' for v in r.get('ambiguities',[]))
        commodity=r.get('commodity');quantity=life=price=None
        if commodity not in known:issues.append(f'{item}: commodity must match existing commodity demand')
        try:quantity=_number(r.get('quantity'),'quantity')*_factor(r.get('quantity_unit'),s.config.quantity_unit)
        except ValidationError as exc:
            if r.get('kind')!='price':issues.append(f'{item}: {exc}')
        if r.get('kind')=='inventory':
            try:
                unit=r.get('life_unit');multiplier={'hour':1,'hours':1,'day':24,'days':24}.get(unit)
                if multiplier is None:raise ValidationError('Missing/unsupported shelf-life unit; use hours or days')
                life=_number(r.get('remaining_life'),'remaining_life')*multiplier
            except ValidationError as exc:issues.append(f'{item}: {exc}')
            draft['inventory'].append({'batch_id':f'AI-{source_id}-{index+1}','commodity':commodity,'quantity':quantity,'shelf_life_hours':life})
        elif r.get('kind') in ('demand','price'):
            destination=r.get('destination_id')
            if destination not in destinations:issues.append(f'{item}: unknown/missing destination')
            try:
                if r.get('currency')!=s.config.currency:raise ValidationError('Currency missing or does not match scenario')
                price=_number(r.get('price_per_unit'),'price_per_unit')/_factor(r.get('price_quantity_unit'),s.config.quantity_unit)
            except ValidationError as exc:issues.append(f'{item}: {exc}')
            if r['kind']=='demand':draft['demand'].append({'destination_id':destination,'commodity':commodity,'quantity':quantity,'price_per_unit':price})
            else:draft['price_updates'].append({'destination_id':destination,'commodity':commodity,'price_per_unit':price})
        else:raise ValidationError(f'{item}: unsupported extraction kind')
        provenance.append({'record':index+1,'source_id':source_id,'source_refs':r.get('source_refs',{}),'ambiguities':r.get('ambiguities',[])})
    if not proposal.get('records'):issues.append('No operational records extracted; nothing can be committed')
    return {'draft':draft,'issues':issues,'provenance':provenance,'generated_ids':'AI-prefixed batch IDs are system labels, not extracted facts. Correct them when needed.'}


def apply_extraction(s:Scenario,draft:dict,confirmed:bool,mode:str)->Scenario:
    if confirmed is not True:raise ValidationError('Human confirmation is required before applying extracted data')
    if mode not in ('append','replace'):raise ValidationError('Choose append or replace inventory explicitly')
    if not isinstance(draft,dict) or set(draft)!= {'inventory','demand','price_updates'}:raise ValidationError('Draft requires inventory, demand, price_updates arrays only')
    if any(not isinstance(v,list) for v in draft.values()) or not any(draft.values()):raise ValidationError('No reviewed records to apply')
    data=s.to_dict();known={b.commodity for b in s.inventory}|{d.commodity for d in s.demand};destinations={d.destination_id for d in s.demand}
    for table,rows in draft.items():
        for r in rows:
            if not isinstance(r,dict):raise ValidationError(f'{table}: expected records')
            if r.get('commodity') not in known:raise ValidationError('Unknown commodity; add its demand explicitly in the input scenario first')
            if table!='inventory' and r.get('destination_id') not in destinations:raise ValidationError('Unknown destination')
    data['inventory']= ([] if mode=='replace' else data['inventory'])+draft['inventory']
    by_key={(d['destination_id'],d['commodity']):d for d in data['demand']};seen=set()
    for row in draft['demand']:
        key=(row.get('destination_id'),row.get('commodity'))
        if key in seen:raise ValidationError('Duplicate extracted demand records')
        seen.add(key);by_key[key]={**by_key.get(key,{}),**row}
    seen_prices=set()
    for row in draft['price_updates']:
        if set(row)!= {'destination_id','commodity','price_per_unit'}:raise ValidationError('Price update has unsupported fields')
        key=(row['destination_id'],row['commodity'])
        if key in seen_prices:raise ValidationError('Duplicate extracted price updates; resolve conflicting records')
        seen_prices.add(key)
        if key not in by_key:raise ValidationError('Price update has no existing destination/commodity demand')
        by_key[key]={**by_key[key],'price_per_unit':row['price_per_unit']}
    data['demand']=list(by_key.values());data['config']['label']='Human-verified AI import / '+s.config.label
    return Scenario.from_dict(data)


def apply_operations(s:Scenario,operations:list[dict],confirmed:bool)->Scenario:
    if confirmed is not True:raise ValidationError('Human confirmation is required before scenario changes')
    if not isinstance(operations,list) or not 1<=len(operations)<=8:raise ValidationError('Provide 1–8 supported operations')
    data=s.to_dict()
    definitions={'delay_route':{'route_id','hours'},'scale_capacity':{'resource_id','factor'},'scale_demand':{'destination_id','commodity','factor'},'scale_price':{'destination_id','commodity','factor'},'scale_inventory':{'batch_id','commodity','factor'}}
    lookups={'route_id':{r.route_id for r in s.routes},'resource_id':{r.resource_id for r in s.resources},'destination_id':{d.destination_id for d in s.demand},'commodity':{d.commodity for d in s.demand}|{b.commodity for b in s.inventory},'batch_id':{b.batch_id for b in s.inventory}}
    for op in operations:
        kind=op.get('op') if isinstance(op,dict) else None
        if kind not in definitions or set(op)!=definitions[kind]|{'op'}:raise ValidationError('Unsupported operation or parameters')
        for field,allowed in lookups.items():
            if field in op and op[field] is not None and op[field] not in allowed:raise ValidationError(f'Unknown {field}: {op[field]}')
        if kind=='delay_route':
            hours=_number(op['hours'],'delay hours',168)
            for r in data['routes']:
                if op['route_id'] is None or r['route_id']==op['route_id']:r['travel_hours']+=hours
        elif kind=='scale_capacity':
            factor=_number(op['factor'],'capacity factor',3)
            for r in data['resources']:
                if op['resource_id'] is None or r['resource_id']==op['resource_id']:r['capacity']*=factor
            for r in data['routes']:
                if op['resource_id'] is None or r['resource_id']==op['resource_id']:r['capacity']*=factor
        else:
            factor=_number(op['factor'],'factor',3);table='inventory' if kind=='scale_inventory' else 'demand';field='price_per_unit' if kind=='scale_price' else 'quantity'
            for r in data[table]:
                if all(op.get(k) is None or r.get(k)==op[k] for k in ('destination_id','commodity','batch_id')):r[field]*=factor
    data['config']['label']+=' / confirmed AI what-if'
    return Scenario.from_dict(data)


def evidence(report:dict)->list[dict]:
    s=Scenario.from_dict(report['scenario'])
    def plan(value):
        return Plan([Shipment(**r) for r in value['shipments']],value['status'],value['runtime_seconds'])
    p,b=plan(report['optimized_plan']),plan(report['baseline_plan']);metrics=evaluate(s,p)
    if metrics['constraint_violations']:raise ValidationError('Cannot ground AI in an invalid dispatch plan')
    facts=[]
    for name,value in metrics.items():
        if isinstance(value,(int,float)) and name!='execution_seconds':facts.append({'id':'metrics.'+name,'kind':'optimization_output','text':f'{name}: {value:.6f}. Currency {s.config.currency}; quantity unit {s.config.quantity_unit}.'})
    for name,row in compare(s,b,p).items():
        if name in ('net_revenue','spoiled_quantity','demand_fulfillment_percent'):
            percentage=round(row["percent_change"],2) if row["percent_change"] is not None else "undefined"
            facts.append({'id':'comparison.'+name,'kind':'optimization_output','text':f'{name}: baseline {row["baseline"]:.6f}, optimized {row["optimized"]:.6f}, absolute change {row["absolute_change"]:.6f}; percent change {percentage}.'})
    for i,row in enumerate(explain(s,p)['shipments'][:12]):facts.append({'id':f'shipment.{i}','kind':'optimization_output','text':row['reason']})
    for i,row in enumerate(explain(s,p)['remaining_inventory'][:8]):facts.append({'id':f'remaining.{i}','kind':'optimization_output','text':str(row)})
    for i,row in enumerate(explain(s,p)['rejected_allocations'][:12]):facts.append({'id':f'rejection.{i}','kind':'optimization_output','text':str(row)})
    for i,row in enumerate([r for r in explain(s,p)['constraint_utilization'] if r['binding']][:10]):facts.append({'id':f'constraint.{i}','kind':'optimization_output','text':str(row)})
    for i,batch in enumerate(s.inventory[:12]):facts.append({'id':f'input.batch.{i}','kind':'verified_input','text':str(batch)})
    facts.append({'id':'assumptions','kind':'explicit_assumption','text':f'Planning horizon {s.config.horizon_hours:g} hours. Immediate sale on arrival, up to demand. Unshipped inventory only spoils if shelf life is within this horizon. Discounts create no assumed customers. No stochastic forecast or committed shipments are modeled.'})
    return facts
