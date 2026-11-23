from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request

from client.stub_data import stub_postings
from service import connectors
from service.backends import load_backend
from service.connectors.greenhouse import UnknownBoard
from service.normalize import render_posting

# I need to make sure my requests follow ExtractRequest & FetchRequest,
# and that my responses follow ExtractResponse and FetchResponse
from service.schemas import (
    ALL_FIELDS,
    ExtractRequest,
    ExtractResponse,
    FetchRequest,
    FetchResponse,
    Health,
)
from service.settings import Settings


# this is going to be important because we will have AI so I need to load it once
@asynccontextmanager
async def lifespan(app: FastAPI):
    # I want to load my settings here and load what backend I am going to use
    print("Loading Settings...")
    settings = Settings()  # load the env settings
    app.state.settings = settings  # set the state to the env settings
    app.state.backend = load_backend(
        settings.EXTRACTOR_BACKEND
    )  # load the backend we are working with
    yield


app = FastAPI(lifespan=lifespan)


# I need heath
@app.get("/healthz", response_model=Health)
def healthz(request: Request) -> Health:
    settings = request.app.state.settings
    return Health(backend=settings.EXTRACTOR_BACKEND, connector_mode=settings.CONNECTOR_MODE)


# I need /v1/extract
@app.post("/v1/extract", response_model=ExtractResponse)
def extract(body: ExtractRequest, request: Request) -> ExtractResponse:
    # check if there is a url
    if body.url is not None:
        parsed = connectors.parse_job_url(body.url)
        if parsed is None:
            raise HTTPException(422, "Not a Greenhouse, Lever, or Ashby job URL")
        if request.app.state.settings.CONNECTOR_MODE == "stub":
            text = "(stub mode: the URL was not fetched)"
        else:
            provider, token, job_id = parsed  # unpack parsed
            try:  # try to get a list of sourcepostings
                postings = connectors.fetch(
                    provider, token, user_agent=request.app.state.settings.CONNECTOR_USER_AGENT
                )
            except UnknownBoard as error:  # if the sourceposting doesn't exists we raise
                raise HTTPException(404, "board doesn't exist") from error
            posting = [
                p for p in postings if p.external_id == job_id
            ]  # if the board exists, but the listing given doesn't
            if not posting:  # list comprehension would return [] if there is no job, is or == None would evaluate false.
                raise HTTPException(404, "Listing does not exist")  # we raise as well
            # header + body, the same shape the backends are trained and evaluated on
            text = render_posting(posting[0].model_dump())
    else:
        text = (
            body.text
        )  # if there was no URL, we just put the provided text as what we want to extract
    fields = list(
        body.fields or ALL_FIELDS
    )  # we either get all fields or a few depending on whether other fields are unchanged since last extract.

    result = request.app.state.backend.extract(text, fields)
    return ExtractResponse(
        backend=request.app.state.backend.name,
        model_version=request.app.state.backend.model_version,
        fields=result,
    )


# I need /v1/fetch
@app.post("/v1/sources/fetch", response_model=FetchResponse)
def fetch(body: FetchRequest, request: Request) -> FetchResponse:
    # check if the provider is in the allowed providers, check if we are in stub
    if request.app.state.settings.CONNECTOR_MODE == "stub":  # check if we are in stub mode
        postings = stub_postings(
            body.provider, body.token
        )  # return sample postings as a list of SourcePostings
    else:
        try:
            postings = connectors.fetch(
                body.provider,
                body.token,
                user_agent=request.app.state.settings.CONNECTOR_USER_AGENT,
            )
        except UnknownBoard as error:
            raise HTTPException(404, f"No {body.provider} board named {body.token!r}.") from error
        except httpx.HTTPError as error:
            raise HTTPException(502, f"{body.provider} didn't answer; try again later.") from error
        except ValueError as error:
            raise HTTPException(501, f"No connector for {body.provider!r} yet.") from error

    return FetchResponse(
        provider=body.provider,  # return the provider
        token=body.token,  # return the token
        fetched_at=datetime.now(UTC),  # return time fetched
        postings=postings,
    )  # return all the postings that the token (company)
    # has listed
