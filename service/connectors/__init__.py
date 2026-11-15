import time
from urllib.parse import unquote, urlparse

import httpx

from service.connectors import ashby, greenhouse, lever
from service.schemas import SourcePosting

ADAPTERS = {"greenhouse": greenhouse.fetch, "lever": lever.fetch, "ashby": ashby.fetch}


def fetch(provider: str, token: str, *, user_agent: str) -> list[SourcePosting]:
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError

    with httpx.Client(
        headers={"User-Agent": user_agent},
        timeout=10,
    ) as client:
        for i in range(3):
            try:
                return adapter(token, http=client)
            except httpx.HTTPStatusError as error:
                if error.response.status_code < 500 or i == 2:
                    raise
            except httpx.TransportError:
                if i == 2:
                    raise
            time.sleep(i + 1)


def parse_job_url(url: str) -> tuple[str, str, str] | None:
    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        return None

    parts = [unquote(p).lower() for p in parsed.path.split("/") if p]  # replaces lines 39–41

    if (
        host in ["boards.greenhouse.io", "job-boards.greenhouse.io"]
        and len(parts) == 3
        and parts[1] == "jobs"
    ):
        return ("greenhouse", parts[0], parts[2])  # returns -> provider, token, jobid

    if host == "jobs.lever.co" and (len(parts) == 2 or (len(parts) == 3 and parts[2] == "apply")):
        return ("lever", parts[0], parts[1])

    if host == "jobs.ashbyhq.com" and (
        len(parts) == 2 or (len(parts) == 3 and parts[2] == "application")
    ):
        return ("ashby", parts[0], parts[1])
    return None
