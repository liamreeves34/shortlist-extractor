from datetime import UTC, datetime

import httpx

from service.connectors.filter import is_internship
from service.normalize import content_hash, html_to_text, unicode_to_text
from service.schemas import Pay, SourcePosting, Structured

API = "https://api.lever.co/v0/postings/{token}?mode=json"
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

    for job in response.json():
        commitment = ((job.get("categories") or {}).get("commitment") or "")
        
        # needs to check if the title or commitment signals internship. 
        if not (is_internship(job["text"]) or is_internship(commitment)):
            continue
        
        content_string = (job["descriptionPlain"] + job["additionalPlain"]) #add all description strings together
                                                                            #need to include the lists, but that will
                                                                            #require normalizing then removing 
                                                                            #unicode tags
        content = html_to_text(content_string) #if any html leaks through, we call this
        
        list_of_additional_info = job["lists"] #returns a list of dicts full of what we want
        for dict_of_title_section in list_of_additional_info: #add lists to the content string
            title, text = dict_of_title_section.values()
            text = unicode_to_text(text)
            buildstring = f"{title}\n{text}"
            content+= buildstring

        hashed_content = content_hash(content)

        salary = job.get("salaryRange") or {}
        pay = Pay(
            min=salary.get("min"),
            max=salary.get("max"),
            period=salary.get("interval"),
            currency=salary.get("currency"),
        ) if salary else None

        structured = Structured(
            work_mode=job["workplaceType"].upper(),
            pay=pay,
            commitment=((job.get("categories") or {}).get("commitment") or None),
            deadline=job.get("application_deadline")
        )
        dt_object = datetime.fromtimestamp(job["createdAt"] / 1000.0, tz=UTC)
        posting = SourcePosting(
            external_id=str(job["id"]),
            title=job["text"],
            organization=board_token, #there is no company name in json, but the token used is the comapy name
            location_raw=(job.get("categories") or {}).get("location"),
            url=job["hostedUrl"],
            updated_at=dt_object, #milliseconds since 1970
            text=content,
            content_hash=hashed_content,
            structured=structured,
        )
        returnlist.append(posting)
    return returnlist