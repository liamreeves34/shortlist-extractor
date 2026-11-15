import httpx
import yaml

from service import connectors
from service.connectors.greenhouse import UnknownBoard
from service.settings import settings

SIMPLE = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json"


def download_urls() -> list[str]:
    response = httpx.get(SIMPLE, headers={"User-Agent": settings.CONNECTOR_USER_AGENT}, timeout=30)
    response.raise_for_status()
    return [listing["url"] for listing in response.json() if listing.get("url")]


def find_tokens(urls: list[str]) -> dict[str, list[str]]:
    found = {"greenhouse": set(), "lever": set(), "ashby": set()}
    for url in urls:
        parsed = connectors.parse_job_url(url)
        if parsed:
            provider, token, _job_id = parsed
            found[provider].add(token.lower())
    return {provider: sorted(tokens) for provider, tokens in found.items()}


def check(provider: str, token: str) -> dict | None:
    try:
        postings = connectors.fetch(provider, token, user_agent=settings.CONNECTOR_USER_AGENT)
    except UnknownBoard:
        print(f"drop  {provider}/{token}: 404")
        return None
    except httpx.HTTPError as error:
        print(f"skip  {provider}/{token}: {error}")
        return None
    organization = postings[0].organization if postings else token
    print(f"keep  {provider}/{token}: {len(postings)} internships")
    return {"provider": provider, "token": token, "organization": organization, "enabled": True}


def main():
    tokens = find_tokens(download_urls())
    sources = []
    for provider, provider_tokens in tokens.items():
        for token in provider_tokens:
            entry = check(provider, token)
            if entry:
                sources.append(entry)
    with open("sources.yaml", "w", encoding="utf-8") as file:
        yaml.safe_dump({"sources": sources}, file, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    main()
