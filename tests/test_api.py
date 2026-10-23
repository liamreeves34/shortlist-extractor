def test_healthz(api):
    response = api.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "backend": "stub", "connector_mode": "stub"}


def test_extract_returns_only_requested_fields(api):
    response = api.post("/v1/extract", json={"text": "any posting", "fields": ["deadline"]})
    assert response.status_code == 200
    body = response.json()
    assert set(body["fields"]) == {"deadline"}
    assert body["fields"]["deadline"]["value"] == "2026-11-15"
    assert body["backend"] == "stub"


def test_extract_with_no_fields_returns_all(api):
    response = api.post("/v1/extract", json={"text": "any posting"})
    assert len(response.json()["fields"]) == 12


def test_extract_rejects_both_text_and_url(api):
    response = api.post("/v1/extract", json={"text": "x", "url": "https://jobs.lever.co/example/1"})
    assert response.status_code == 422


def test_extract_rejects_unknown_field(api):
    response = api.post("/v1/extract", json={"text": "x", "fields": ["favorite_color"]})
    assert response.status_code == 422


def test_url_must_be_on_the_allowlist(api):
    response = api.post("/v1/extract", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert response.status_code == 422


def test_fetch_returns_two_postings(api):
    response = api.post(
        "/v1/sources/fetch", json={"provider": "greenhouse", "token": "examplecorp"}
    )
    assert response.status_code == 200
    postings = response.json()["postings"]
    assert len(postings) == 2
    assert postings[0]["content_hash"].startswith("sha256:")


def test_fetch_rejects_unknown_provider(api):
    response = api.post("/v1/sources/fetch", json={"provider": "indeed", "token": "x"})
    assert response.status_code == 422
