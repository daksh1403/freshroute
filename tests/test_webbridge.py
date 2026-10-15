import json
from freshroute.webbridge import run, preview, disrupt
from test_engine import data


def test_browser_bridge_matches_known_optimum_and_replans():
    raw = json.dumps(data())
    result = json.loads(run(raw,15))
    assert result['optimized_metrics']['net_revenue'] == 120
    assert result['baseline_metrics']['net_revenue'] == 90
    assert result['optimized_metrics']['constraint_violations'] == []
    assert result['shipments']
    assert json.loads(preview(raw))['inventory_quantity'] == 20
    updated = json.loads(disrupt(raw,json.dumps(result['optimized_plan']),json.dumps({'delay_hours':12,'capacity_factor':0.5}),15))
    assert not updated['replanning']['previous_plan_feasible']
    assert updated['optimized_metrics']['constraint_violations'] == []


def test_browser_workbook_roundtrip_blank_optional_fields():
    from io import BytesIO
    import pandas as pd
    from freshroute.model import Scenario
    from freshroute.webbridge import workbook
    raw=Scenario.from_dict(data()).to_dict()
    stream=BytesIO()
    with pd.ExcelWriter(stream) as writer:
        for key,value in raw.items():
            pd.DataFrame([value] if key=='config' else value).to_excel(writer,sheet_name=key,index=False)
    assert json.loads(workbook(stream.getvalue()))==raw
