import json
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from httpx import HTTPError

from service import connectors
from service.connectors.greenhouse import UnknownBoard
from service.settings import Settings

# class SourcePosting(BaseModel):
#     external_id: str
#     title: str
#     organization: str
#     location_raw: str | None = None
#     url: str
#     updated_at: datetime | None = None
#     text: str
#     content_hash: str
#     structured: Structured = Structured()


settings = Settings()
PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)  # __file__ points to the file itself, resolve makes it the absolute path
# parent is . and another parent is the project root

DATA_PATH = PROJECT_ROOT / "data" / "raw"
MANIFEST = PROJECT_ROOT / "data" / "manifests" / "collected.jsonl"

source_path = PROJECT_ROOT / "sources.yaml"


def write_raw():
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    with open(source_path, encoding="utf-8") as sources:
        source_list = yaml.safe_load(sources)["sources"]

    new = 0
    with open(MANIFEST, "a", encoding="utf-8") as manifest:
        for dic in source_list:
            provider, token = dic["provider"], dic["token"]
            try:
                postings = connectors.fetch(
                    provider, token, user_agent=settings.CONNECTOR_USER_AGENT
                )
            except (UnknownBoard, HTTPError) as error:
                print(f"skip  {provider}/{token}: {error!r}")
                continue

            for posting in postings:
                save = DATA_PATH / f"{posting.content_hash.removeprefix('sha256:')}.json"
                if save.exists():
                    continue

                fetched_at = datetime.now(UTC).isoformat()
                record = {
                    "provider": provider,
                    "token": token,
                    "fetched_at": fetched_at,
                    **posting.model_dump(mode="json"),
                }

                save.write_text(json.dumps(record, indent=2), encoding="utf-8")

                manifest.write(
                    json.dumps(
                        {
                            "hash": posting.content_hash,
                            "provider": provider,
                            "token": token,
                            "organization": posting.organization,
                            "external_id": posting.external_id,
                            "fetched_at": fetched_at,
                        }
                    )
                    + "\n"
                )
                new += 1
            time.sleep(1)
    print(f"{new} new postings")


if __name__ == "__main__":
    write_raw()
# print(data)
