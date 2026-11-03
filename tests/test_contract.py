"""The fixtures match the customer API document the backend publishes.

openapi_subset.json is copied from the monorepo's customer.json by
tools/homeassistant-publish/sync_contract.py; CI fails when it drifts. So a
backend change to these routes fails here until the fixtures (and the
integration) are updated with it.
"""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from .conftest import FIXTURES, load

SUBSET = json.loads((FIXTURES / "openapi_subset.json").read_text())


def _validator(path: str) -> Draft202012Validator:
    schema = SUBSET["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return Draft202012Validator({**schema, "components": SUBSET["components"]})


@pytest.mark.parametrize("path, fixture", [
    ("/api/dashboard/meta", "meta"),
    ("/api/sites/{site_uuid}/sensors", "sensors"),
    ("/api/sites/{site_uuid}/readings", "readings"),
])
def test_fixture_matches_the_published_schema(path, fixture):
    errors = sorted(_validator(path).iter_errors(load(fixture)), key=str)
    assert not errors, [e.message for e in errors]


def test_fixtures_use_every_field_the_integration_reads():
    point = SUBSET["components"]["schemas"]["SitePoint"]["properties"]
    for field in ("point_uuid", "name", "entity_class", "unit", "cumulative", "value_type"):
        assert field in point, f"SitePoint lost {field}; the integration reads it"
    equipment = SUBSET["components"]["schemas"]["SiteEquipment"]["properties"]
    for field in ("equipment_uuid", "name", "entity_class", "template", "dev_eui", "space_name",
                  "level_name", "building_name", "points"):
        assert field in equipment, f"SiteEquipment lost {field}; the integration reads it"
    reading = SUBSET["components"]["schemas"]["SiteReading"]["properties"]
    for field in ("point_uuid", "value", "updated_at"):
        assert field in reading
