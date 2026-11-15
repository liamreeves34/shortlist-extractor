from datetime import datetime
from typing import Literal

import httpx

from service.connectors.filter import is_internship
from service.connectors.greenhouse import UnknownBoard
from service.normalize import content_hash
from service.schemas import Pay, SourcePosting, Structured

API = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
PERIODS: dict[str, Literal["HOUR", "YEAR"]] = {"1 HOUR": "HOUR", "1 YEAR": "YEAR"}


def fetch(
    board_token: str,
    *,
    http: httpx.Client,
) -> list[SourcePosting]:
    return_list = []
    response = http.get(API.format(token=board_token))

    if response.status_code == 404:
        raise UnknownBoard(board_token)
    response.raise_for_status()

    for job in response.json()["jobs"]:
        if not is_internship(job["title"], job.get("employmentType")):
            continue

        text: str = job["descriptionPlain"]
        hashed = content_hash(text)

        compensation = job.get("compensation")
        components = compensation.get("summaryComponents") if compensation else None
        pay = None

        if components is not None:
            for component in components:
                comptype = component.get("compensationType")
                if comptype == "Salary":
                    pay = Pay(
                        min=component.get("minValue"),
                        max=component.get("maxValue"),
                        period=PERIODS.get(component.get("interval") or "", "UNKNOWN"),
                        currency=component.get("currencyCode"),
                    )

        work_place = job.get("workplaceType")
        work_mode = work_place.upper() if work_place else None

        structured = Structured(
            work_mode=work_mode, pay=pay, commitment=job.get("employmentType"), deadline=None
        )

        posting = SourcePosting(
            external_id=job["id"],
            title=job["title"],
            organization=board_token,
            location_raw=job.get("location"),
            url=job["jobUrl"],
            updated_at=datetime.fromisoformat(job["publishedAt"]),
            text=text,
            content_hash=hashed,
            structured=structured,
        )

        return_list.append(posting)
    return return_list
