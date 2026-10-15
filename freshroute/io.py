"""Source adapters and portable reports. Source naming does not leak into the model."""
from dataclasses import asdict
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import re
import zipfile

import pandas as pd

from freshroute.model import Scenario, ValidationError
from freshroute.engine import Plan
from freshroute.evaluation import evaluate, compare
from freshroute.insights import discounts, explain, shipment_rows

from freshroute.adapters import TABLES, normalize


def load_scenario(source: str | Path | bytes, *, format: str | None = None, column_map: dict | None = None) -> Scenario:
    try:
        if isinstance(source,bytes):
            if format == 'xlsx':
                data = _workbook(BytesIO(source))
            else: data = json.loads(source)
        else:
            path = Path(source)
            if path.is_dir():
                data = {'config':json.loads((path/'config.json').read_text())}
                for table in TABLES:
                    data[table] = pd.read_csv(path/f'{table}.csv', keep_default_na=False).to_dict('records')
            elif path.suffix.lower() in ('.xlsx','.xlsm'):
                data = _workbook(path)
            elif path.suffix.lower() == '.json': data = json.loads(path.read_text())
            else: raise ValidationError('input: provide a JSON file, XLSX workbook, or CSV directory with config.json')
        return normalize(data,column_map)
    except ValidationError: raise
    except (OSError,ValueError,TypeError,KeyError,zipfile.BadZipFile,ImportError) as exc:
        raise ValidationError(f'Cannot load scenario: {exc}') from None


def _workbook(source) -> dict:
    frames = pd.read_excel(source, sheet_name=None, keep_default_na=False)
    if 'config' not in frames or len(frames['config']) != 1:
        raise ValidationError('workbook config: supply exactly one row on a config sheet')
    return {key:frame.to_dict('records')[0] if key=='config' else frame.to_dict('records') for key,frame in frames.items()}


def report(s: Scenario, baseline: Plan, optimized: Plan) -> dict:
    return {'schema_version':1, 'scenario':s.to_dict(), 'baseline_plan':baseline.to_dict(),
            'optimized_plan':optimized.to_dict(), 'baseline_metrics':evaluate(s,baseline),
            'optimized_metrics':evaluate(s,optimized), 'comparison':compare(s,baseline,optimized),
            'explanations':explain(s,optimized), 'discount_scenarios':discounts(s,optimized),
            'assumptions':['Single unexecuted dispatch wave; immediate sale on arrival up to demand.',
                           'All units and currency as configured; no inferred demand uplift.',
                           'Unshipped stock spoils only if shelf life <= planning horizon.',
                           'Absent optional costs equal zero; see normalized input.']}


def csv_text(rows: list[dict], columns: list[str] | None = None) -> str:
    # Prevent spreadsheet formula execution in exported user-supplied identifier fields.
    frame = pd.DataFrame(rows,columns=columns)
    for col in frame.columns:
        frame[col] = frame[col].map(lambda v: "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
    return frame.to_csv(index=False)


def report_files(s: Scenario, baseline: Plan, optimized: Plan) -> dict[str,str]:
    shipment_columns = ['dispatch_priority','batch_id','commodity','destination_id','route_id','resource_id','quantity',
                        'arrival_hours','life_on_arrival_hours','sales_revenue','transport_cost','handling_cost','sales_contribution','avoided_remaining_cost']
    result = report(s,baseline,optimized)
    return {'report.json':json.dumps(result,indent=2,allow_nan=False),
            'scenario.json':json.dumps(s.to_dict(),indent=2,allow_nan=False),
            'optimized_shipments.csv':csv_text(shipment_rows(s,optimized),shipment_columns),
            'baseline_shipments.csv':csv_text(shipment_rows(s,baseline),shipment_columns),
            'comparison.csv':csv_text([{'metric':key,**value} for key,value in result['comparison'].items()]),
            'discount_scenarios.csv':csv_text(result['discount_scenarios'])}


def report_zip(s: Scenario, baseline: Plan, optimized: Plan) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as bundle:
        for name,content in report_files(s,baseline,optimized).items(): bundle.writestr(name,content)
    return output.getvalue()


def save_report(s: Scenario, baseline: Plan, optimized: Plan, output: str | Path):
    output = Path(output); output.mkdir(parents=True,exist_ok=True)
    for name,content in report_files(s,baseline,optimized).items(): (output/name).write_text(content)
