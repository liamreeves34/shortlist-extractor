from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request

from client.stub_data import stub_postings
from service.backends import load_backend

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

ALLOWED_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
}


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
    if body.url is not None or "":
        host = urlparse(body.url).hostname
        if host not in ALLOWED_HOSTS:
            raise HTTPException(422, "Invalid input")
        elif request.app.state.settings.EXTRACTOR_BACKEND == "stub":
            text = "(stub mode: the URL was not fetched)"
        else:
            raise HTTPException(501, f"URL host {host!r} isn't supported.")
    else:
        text = body.text

    fields = list(
        body.fields or ALL_FIELDS
    )  # we either get all fields or some others remain the same.

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
        raise HTTPException(
            501, "Other Backends Pending"
        )  # if we aren't in stub, raise error bc we don't have others
    return FetchResponse(
        provider=body.provider,  # return the provider
        token=body.token,  # return the token
        fetched_at=datetime.now(UTC),  # return time fetched
        postings=postings,
    )  # return all the postings that the token (company)
    # has listed
