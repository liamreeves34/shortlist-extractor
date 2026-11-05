import time

import httpx

from service.connectors import greenhouse, lever
from service.schemas import SourcePosting

ADAPTERS = {"greenhouse": greenhouse.fetch, "lever": lever.fetch}

def fetch(provider: str, token: str, *, user_agent: str) -> list[SourcePosting]:
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError
    
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=10,) as client:
        for i in range(3):
                try:
                    return adapter(token, http=client)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code < 500 or i == 2:
                        raise
                except httpx.TransportError:
                    if i == 2:
                        raise
                time.sleep(i+1)
