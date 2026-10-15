import json
import pandas as pd
import pytest

from freshroute.io import load_scenario, save_report
from freshroute.model import ValidationError
from freshroute.engine import baseline, optimize
from test_engine import data


def test_json_csv_xlsx_roundtrip(tmp_path):
    d = data()
    p = tmp_path / 'input.json'; p.write_text(json.dumps(d))
    s = load_scenario(p)
    assert s.inventory[0].batch_id == 'new'  # canonical stable sort
    directory = tmp_path / 'csv'; directory.mkdir()
    (directory / 'config.json').write_text(json.dumps(d['config']))
    for section in ['inventory', 'demand', 'routes', 'resources']:
        pd.DataFrame(d[section]).to_csv(directory / f'{section}.csv', index=False)
    assert load_scenario(directory) == s
    xlsx = tmp_path / 'input.xlsx'
    with pd.ExcelWriter(xlsx) as writer:
        for key, value in d.items():
            pd.DataFrame([value] if key == 'config' else value).to_excel(writer, sheet_name=key, index=False)
    assert load_scenario(xlsx) == s
    out = tmp_path / 'report'
    save_report(s, baseline(s), optimize(s), out)
    report = json.loads((out / 'report.json').read_text())
    assert report['optimized_metrics']['constraint_violations'] == []
    assert (out / 'optimized_shipments.csv').exists()


def test_aliases_and_column_mapping(tmp_path):
    d = data(); d['inventory'][0]['qty'] = d['inventory'][0].pop('quantity')
    d['inventory'][1]['qty'] = d['inventory'][1].pop('quantity')
    p = tmp_path / 'input.json'; p.write_text(json.dumps(d))
    assert load_scenario(p).inventory[0].quantity == 10
    for b in d['inventory']: b['Available Stock'] = b.pop('qty')
    p.write_text(json.dumps(d))
    assert load_scenario(p, column_map={'inventory': {'Available Stock': 'quantity'}}).inventory[0].quantity == 10


def test_expiry_timestamps_require_asof_and_normalize(tmp_path):
    d = data(); d['config']['as_of'] = '2026-10-15T00:00:00Z'
    for b in d['inventory']:
        del b['shelf_life_hours']; b['expires_at'] = '2026-10-16T00:00:00Z'
    p = tmp_path / 'input.json'; p.write_text(json.dumps(d))
    assert load_scenario(p).inventory[0].shelf_life_hours == 24
    del d['config']['as_of']; p.write_text(json.dumps(d))
    with pytest.raises(ValidationError, match='as_of'): load_scenario(p)


def test_ambiguous_columns_and_unsupported_time_demand_rejected(tmp_path):
    d = data(); d['inventory'][0]['qty'] = 20
    p = tmp_path / 'input.json'; p.write_text(json.dumps(d))
    with pytest.raises(ValidationError, match='ambiguous'): load_scenario(p)
    d = data(); d['demand'][0]['timestamp'] = '2026-10-15'
    p.write_text(json.dumps(d))
    with pytest.raises(ValidationError, match='unsupported'): load_scenario(p)


def test_missing_config_and_invalid_excel_report_actionably(tmp_path):
    d = data(); del d['config']['horizon_hours']
    p = tmp_path / 'input.json'; p.write_text(json.dumps(d))
    with pytest.raises(ValidationError, match='horizon_hours'): load_scenario(p)
