import json

import jsonschema

from scripts.export_schema import CONTRACT_DIR, build_schemas


def test_committed_contract_matches_the_code():
    for name, schema in build_schemas().items():
        committed = json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))
        assert committed == schema, (
            f"contract/{name} is stale: run uv run python -m scripts.export_schema"
        )


def test_stub_responses_satisfy_the_contract(api):
    schemas = build_schemas()
    extract = api.post("/v1/extract", json={"text": "x"}).json()
    jsonschema.validate(extract, schemas["extract_response.schema.json"])
    fetch = api.post("/v1/sources/fetch", json={"provider": "lever", "token": "x"}).json()
    jsonschema.validate(fetch, schemas["fetch_response.schema.json"])
