import httpx

from service.connectors.filter import is_internship
from service.normalize import content_hash, html_to_text
from service.schemas import SourcePosting, Structured

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class UnknownBoard(Exception): ...


client = httpx.Client()
token = "figma"


# calling the API at some token will send back a list of jobs for that token. I need to extract only the fields that I want
# out of each job posting. and add them to a list of SourcePostings
def fetch(
    board_token: str,
    *,
    http: httpx.Client,
) -> list[SourcePosting]:
    returnlist = []

    response = http.get(API.format(token=board_token))
    if response.status_code == 404:
        raise UnknownBoard(board_token)  # the board doesn't exist; retrying won't help
    response.raise_for_status()

    jobdict = response.json()  # gets a list of jobs for the provided token
    for job in jobdict["jobs"]:
        if not is_internship(job["title"]):
            continue
        content = html_to_text(job["content"])
        hashed_content = content_hash(content)

        structured = Structured(
            work_mode=None, pay=None, commitment=None, deadline=job.get("application_deadline")
        )
        posting = SourcePosting(
            external_id=str(job["id"]),
            title=job["title"],
            organization=job["company_name"],
            location_raw=(job.get("location") or {}).get("name"),
            url=job["absolute_url"],
            updated_at=job["updated_at"],
            text=content,
            content_hash=hashed_content,
            structured=structured,
        )
        returnlist.append(posting)
    return returnlist
