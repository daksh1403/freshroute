"""Dependency-free column and timestamp normalization shared with WebAssembly."""
from datetime import datetime
import re
from freshroute.model import Scenario, ValidationError

TABLES = ('inventory','demand','routes','resources')
ALIASES = {
    'inventory': {'batch':'batch_id','id':'batch_id','product':'commodity','produce':'commodity', 'qty':'quantity', 'stock':'quantity',
                  'remaining_shelf_life_hours':'shelf_life_hours','remaining_life_hours':'shelf_life_hours'},
    'demand': {'destination':'destination_id','market':'destination_id','product':'commodity','qty':'quantity','demand':'quantity',
               'unit_price':'price_per_unit','selling_price_per_unit':'price_per_unit'},
    'routes': {'route':'route_id','destination':'destination_id','vehicle_id':'resource_id','transport_time_hours':'travel_hours',
               'transport_cost_per_unit':'cost_per_unit','shipment_cost':'fixed_cost'},
    'resources': {'vehicle_id':'resource_id','vehicle':'resource_id','vehicle_capacity':'capacity'},
    'config': {},
}


def _name(value: str) -> str:
    return re.sub(r'\s+', '_', str(value).strip().lower())


def normalize(data: dict, column_map: dict | None = None) -> Scenario:
    if not isinstance(data, dict): raise ValidationError('scenario: expected an object')
    normalized = {}
    for table,records in data.items():
        if table not in ALIASES:
            raise ValidationError(f'unsupported table {table!r}')
        if table == 'config':
            if not isinstance(records,dict): raise ValidationError('config: expected object')
            records = [records]
        if not isinstance(records,list): raise ValidationError(f'{table}: expected array')
        result = []
        for index,row in enumerate(records):
            if not isinstance(row,dict): raise ValidationError(f'{table}[{index}]: expected record')
            clean = {}
            for key,value in row.items():
                target = (column_map or {}).get(table,{}).get(key,key)
                target = ALIASES[table].get(_name(target),_name(target))
                if target in clean: raise ValidationError(f'{table}[{index}]: ambiguous columns both map to {target}')
                clean[target] = value
            result.append(clean)
        normalized[table] = result[0] if table == 'config' else result
    if 'inventory' in normalized:
        for i,b in enumerate(normalized['inventory']):
            if 'expires_at' not in b: continue
            if 'shelf_life_hours' in b:
                raise ValidationError(f'inventory[{i}]: ambiguous expires_at and shelf_life_hours; provide only one')
            config = normalized.get('config',{})
            try:
                as_of = datetime.fromisoformat(config['as_of'].replace('Z','+00:00'))
                expiry = datetime.fromisoformat(b.pop('expires_at').replace('Z','+00:00'))
                if as_of.tzinfo is None or expiry.tzinfo is None: raise ValueError('timezone required')
                b['shelf_life_hours'] = max(0,(expiry-as_of).total_seconds()/3600)
            except (KeyError,ValueError,AttributeError,TypeError) as exc:
                raise ValidationError(f'inventory[{i}].expires_at: requires timezone-aware ISO timestamps and config.as_of ({exc})') from None
    return Scenario.from_dict(normalized)


