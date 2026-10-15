"""JSON-only interface for the same engine in Pyodide. No network or UI dependencies."""
from dataclasses import asdict
import json

from freshroute.adapters import normalize
from freshroute.engine import Plan, Shipment, baseline, optimize
from freshroute.evaluation import evaluate, compare
from freshroute.insights import discounts, explain, shipment_rows
from freshroute.scenario import change_scenario, replan


def _result(s, b, p):
    return {'schema_version':1,'scenario':s.to_dict(),'baseline_plan':b.to_dict(),'optimized_plan':p.to_dict(),
            'baseline_metrics':evaluate(s,b),'optimized_metrics':evaluate(s,p),'comparison':compare(s,b,p),
            'shipments':shipment_rows(s,p),'baseline_shipments':shipment_rows(s,b),
            'explanations':explain(s,p),'discount_scenarios':discounts(s,p)}


def run(raw: str, time_limit: float = 15) -> str:
    s=normalize(json.loads(raw))
    return json.dumps(_result(s,baseline(s),optimize(s,time_limit)),allow_nan=False)


def preview(raw: str) -> str:
    s=normalize(json.loads(raw))
    return json.dumps({'scenario':s.to_dict(),'inventory_quantity':sum(b.quantity for b in s.inventory),
                       'demand_quantity':sum(d.quantity for d in s.demand),
                       'at_risk_quantity':sum(b.quantity for b in s.inventory if b.shelf_life_hours<=s.config.horizon_hours)},allow_nan=False)


def disrupt(raw: str, prior: str, modifications: str, time_limit: float = 15) -> str:
    s=normalize(json.loads(raw)); previous=json.loads(prior)
    previous['shipments']=[Shipment(**row) for row in previous['shipments']]
    old=Plan(**previous)
    updated=change_scenario(s,**json.loads(modifications))
    result=replan(s,old,updated,time_limit)
    p=result.pop('plan')
    report=_result(updated,baseline(updated),p)
    report['replanning']=result
    return json.dumps(report,allow_nan=False)


def workbook(raw_bytes: bytes) -> str:
    """Optional browser XLSX import. openpyxl is loaded only on demand."""
    from io import BytesIO
    from openpyxl import load_workbook
    book=load_workbook(BytesIO(raw_bytes),read_only=True,data_only=True)
    tables={}
    for sheet in book:
        rows=iter(sheet.values)
        header=next(rows,())
        if len(set(header))!=len(header): raise ValueError(f'{sheet.title}: duplicate column headers')
        records=[{key: (value if value is not None else '') for key,value in zip(header,row)}
                 for row in rows if any(v is not None for v in row)]
        if sheet.title=='config':
            if len(records)!=1: raise ValueError('config sheet must have exactly one row')
            tables[sheet.title]=records[0]
        else: tables[sheet.title]=records
    book.close()
    return json.dumps(normalize(tables).to_dict(),allow_nan=False)


def ai_review(raw:str,proposal:str)->str:
    from freshroute.intelligence import review_extraction
    return json.dumps(review_extraction(normalize(json.loads(raw)),json.loads(proposal)),allow_nan=False)


def ai_apply(raw:str,draft:str,confirmed:bool,mode:str)->str:
    from freshroute.intelligence import apply_extraction
    return json.dumps(apply_extraction(normalize(json.loads(raw)),json.loads(draft),confirmed,mode).to_dict(),allow_nan=False)


def ai_facts(raw_report:str)->str:
    from freshroute.intelligence import evidence
    return json.dumps(evidence(json.loads(raw_report)),allow_nan=False)


def ai_whatif(raw_report:str,operations:str,confirmed:bool,time_limit:float=15)->str:
    from freshroute.intelligence import apply_operations
    previous=json.loads(raw_report);s=normalize(previous['scenario']);p=previous['optimized_plan']
    old=Plan([Shipment(**x) for x in p.pop('shipments')],**p)
    updated=apply_operations(s,json.loads(operations),confirmed)
    changes=replan(s,old,updated,time_limit);plan=changes.pop('plan')
    result=_result(updated,baseline(updated),plan);result['replanning']=changes
    return json.dumps(result,allow_nan=False)
