import json
from freshroute.benchmark import run_benchmark
from test_engine import data


def test_mixed_currencies_are_never_added_together(tmp_path):
    inputs=[]
    for currency in ['INR','USD']:
        raw=data();raw['config']['currency']=currency
        path=tmp_path/f'{currency}.json';path.write_text(json.dumps(raw));inputs.append(str(path))
    result=run_benchmark(tmp_path/'out',inputs)
    assert result['total_net_change'] is None
    assert result['mean_net_change'] is None
    assert result['by_currency']['INR']['total_net_change']==30
    assert result['by_currency']['USD']['total_net_change']==30
    assert result['constraint_violations']==0
