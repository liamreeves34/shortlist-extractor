"""Canned responses, used in two places.

1. The client's offline stub mode (EXTRACTOR_MODE=stub), so the team app runs
   with no extraction service at all.
2. The service's stub backend (EXTRACTOR_BACKEND=stub), so the running service
   returns realistic answers before any model exists.

Keeping one copy means the two can never disagree.
"""

import hashlib

STUB_FIELDS: dict[str, dict] = {
    "title": {
        "value": "Software Engineering Intern, Summer 2027",
        "confidence": 0.99,
        "evidence": "Software Engineering Intern, Summer 2027",
        "needs_review": False,
        "source": "model",
    },
    "organization": {
        "value": "Example Corp",
        "confidence": 0.99,
        "evidence": None,
        "needs_review": False,
        "source": "model",
    },
    "location": {
        "value": "Austin, TX",
        "confidence": 0.97,
        "evidence": "Location: Austin, TX",
        "needs_review": False,
        "source": "model",
    },
    "start_term": {
        "value": "Summer 2027",
        "confidence": 0.95,
        "evidence": "Summer 2027 internship",
        "needs_review": False,
        "source": "model",
    },
    "deadline": {
        "value": "2026-11-15",
        "confidence": 0.94,
        "evidence": "Applications close November 15, 2026.",
        "needs_review": False,
        "source": "model",
    },
    "deadline_type": {
        "value": "FIXED",
        "confidence": 0.93,
        "evidence": "Applications close November 15, 2026.",
        "needs_review": False,
        "source": "model",
    },
    "degree_levels": {
        "value": ["BACHELOR"],
        "confidence": 0.90,
        "evidence": "Pursuing a bachelor's degree in computer science",
        "needs_review": False,
        "source": "model",
    },
    # One low-confidence field on purpose, so the team's review queue has something to show.
    "citizenship": {
        "value": "US_CITIZEN",
        "confidence": 0.62,
        "evidence": "Candidates must be eligible to work in the U.S.",
        "needs_review": True,
        "source": "model",
    },
    "clearance": {
        "value": "NONE_MENTIONED",
        "confidence": 0.91,
        "evidence": None,
        "needs_review": False,
        "source": "model",
    },
    "work_mode": {
        "value": "HYBRID",
        "confidence": 0.88,
        "evidence": "Hybrid, 3 days in office",
        "needs_review": False,
        "source": "model",
    },
    "pay": {
        "value": {"min": 25.0, "max": 32.0, "period": "HOUR", "currency": "USD"},
        "confidence": 0.86,
        "evidence": "$25 to $32 per hour",
        "needs_review": False,
        "source": "model",
    },
    "skills": {
        "value": ["Python", "SQL"],
        "confidence": 0.80,
        "evidence": "Experience with Python and SQL",
        "needs_review": False,
        "source": "model",
    },
}


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def stub_postings(provider: str, token: str) -> list[dict]:
    """Two fake internship postings for any employer."""
    postings = []
    for n, title in (
        (1001, "Software Engineering Intern, Summer 2027"),
        (1002, "Data Science Intern, Summer 2027"),
    ):
        text = f"{title}. Example Corp. Applications close November 15, 2026."
        postings.append(
            {
                "external_id": f"{token}-{n}",
                "title": title,
                "organization": "Example Corp",
                "location_raw": "Austin, TX",
                "url": f"https://example.com/{provider}/{token}/jobs/{n}",
                "updated_at": "2026-10-30T18:22:00Z",
                "text": text,
                "content_hash": _hash(text),
                "structured": {"work_mode": None, "pay": None, "commitment": "Intern"},
            }
        )
    return postings
