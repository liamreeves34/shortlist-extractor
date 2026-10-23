import json
from pathlib import Path

from service.schemas import ExtractRequest, ExtractResponse, FetchRequest, FetchResponse

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"


def build_schemas() -> dict[str, dict]:
    return {
        "extract_request.schema.json": ExtractRequest.model_json_schema(),
        "extract_response.schema.json": ExtractResponse.model_json_schema(),
        "fetch_request.schema.json": FetchRequest.model_json_schema(),
        "fetch_response.schema.json": FetchResponse.model_json_schema(),
    }


def main() -> None:
    CONTRACT_DIR.mkdir(exist_ok=True)
    for name, schema in build_schemas().items():
        (CONTRACT_DIR / name).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote contract/{name}")


if __name__ == "__main__":
    main()
