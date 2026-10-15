"""Canonical data contract. No solver or presentation dependencies."""
from dataclasses import asdict, dataclass, fields
from math import isfinite
from typing import Any
import logging

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Actionable scenario validation failure."""


@dataclass(frozen=True)
class Config:
    horizon_hours: float
    quantity_unit: str
    currency: str
    handling_hours: float = 0
    integer_quantities: bool = False
    label: str = 'Imported scenario'
    as_of: str = ''


@dataclass(frozen=True)
class Batch:
    batch_id: str
    commodity: str
    quantity: float
    shelf_life_hours: float
    handling_cost_per_unit: float = 0
    disposal_cost_per_unit: float = 0
    storage_cost_per_unit: float = 0


@dataclass(frozen=True)
class Demand:
    destination_id: str
    commodity: str
    quantity: float
    price_per_unit: float
    min_arrival_life_hours: float = 0


@dataclass(frozen=True)
class Route:
    route_id: str
    destination_id: str
    resource_id: str
    travel_hours: float
    capacity: float
    cost_per_unit: float
    fixed_cost: float = 0
    commodity: str = ''


@dataclass(frozen=True)
class Resource:
    resource_id: str
    capacity: float


def _record(cls, record: dict, context: str):
    if not isinstance(record, dict):
        raise ValidationError(f'{context}: expected an object/record')
    allowed = {f.name for f in fields(cls)}
    extra = set(record) - allowed
    if extra:
        raise ValidationError(f'{context}: unsupported columns {sorted(extra)}; map or remove explicitly')
    cleaned = {}
    for f in fields(cls):
        if f.name not in record:
            from dataclasses import MISSING
            if f.default is MISSING:
                raise ValidationError(f'{context}.{f.name}: required value is missing')
            continue
        value = record[f.name]
        label = f'{context}.{f.name}'
        if f.type is float:
            if isinstance(value, bool) or value is None:
                raise ValidationError(f'{label}: expected a finite nonnegative number')
            try:
                number = float(value)
            except (ValueError, TypeError, OverflowError):
                raise ValidationError(f'{label}: expected a finite nonnegative number') from None
            if not isfinite(number) or number < 0:
                raise ValidationError(f'{label}: expected a finite nonnegative number')
            cleaned[f.name] = number
        elif f.type is bool:
            if not isinstance(value, bool):
                raise ValidationError(f'{label}: expected JSON boolean true/false')
            cleaned[f.name] = value
        else:
            if not isinstance(value, str) or (not value.strip() and f.name not in ('commodity', 'as_of')):
                raise ValidationError(f'{label}: expected a nonempty string')
            cleaned[f.name] = value.strip().casefold() if f.name == 'commodity' else value.strip()
            if f.name == 'commodity' and cls is not Route and not cleaned[f.name]:
                raise ValidationError(f'{label}: commodity cannot be empty')
    return cls(**cleaned)


@dataclass(frozen=True)
class Scenario:
    config: Config
    inventory: tuple[Batch, ...]
    demand: tuple[Demand, ...]
    routes: tuple[Route, ...]
    resources: tuple[Resource, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Scenario':
        if not isinstance(data, dict):
            raise ValidationError('scenario: expected a JSON object')
        expected = {'config', 'inventory', 'demand', 'routes', 'resources'}
        if set(data) != expected:
            raise ValidationError(f'scenario: required sections {sorted(expected)}; missing {sorted(expected-set(data))}; unsupported {sorted(set(data)-expected)}')
        config = _record(Config, data['config'], 'config')
        if config.horizon_hours <= 0:
            raise ValidationError('config.horizon_hours: must be greater than zero')
        tables = {}
        keys = {'inventory': lambda b: b.batch_id, 'demand': lambda d: (d.destination_id, d.commodity),
                'routes': lambda r: r.route_id, 'resources': lambda r: r.resource_id}
        for name, record_type in [('inventory', Batch), ('demand', Demand), ('routes', Route), ('resources', Resource)]:
            if not isinstance(data[name], list):
                raise ValidationError(f'{name}: expected an array of records')
            values = [_record(record_type, row, f'{name}[{i}]') for i, row in enumerate(data[name])]
            seen = set()
            for row in values:
                key = keys[name](row)
                if key in seen:
                    raise ValidationError(f'{name}: duplicate key {key!r}; aggregate deliberately before import')
                seen.add(key)
            tables[name] = tuple(sorted(values, key=keys[name]))
        resource_ids = {r.resource_id for r in tables['resources']}
        destination_ids = {d.destination_id for d in tables['demand']}
        for r in tables['routes']:
            if r.resource_id not in resource_ids:
                raise ValidationError(f'routes.{r.route_id}.resource_id: unknown resource {r.resource_id!r}')
            if r.destination_id not in destination_ids:
                # Empty demand intentionally makes the entire scenario a valid no-sales input.
                if destination_ids:
                    raise ValidationError(f'routes.{r.route_id}.destination_id: unknown destination {r.destination_id!r}')
        scenario = cls(config=config, **tables)
        logger.info('Validated scenario: %d batches, %d demand rows, %d routes', len(scenario.inventory), len(scenario.demand), len(scenario.routes))
        return scenario

    def to_dict(self) -> dict[str, Any]:
        return {'config': asdict(self.config), **{name: [asdict(v) for v in getattr(self, name)] for name in ('inventory', 'demand', 'routes', 'resources')}}

    def residual_cost(self, batch: Batch) -> float:
        return batch.disposal_cost_per_unit if batch.shelf_life_hours <= self.config.horizon_hours else batch.storage_cost_per_unit
