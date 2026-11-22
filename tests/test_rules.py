"""Step 4.1: service/backends/rules.py on invented postings (no real posting text)."""

import pytest

from service.backends import load_backend
from service.backends.rules import (
    FALLBACK,
    MATCHED,
    RulesBackend,
    get_citizenship,
    get_clearance,
    get_deadline,
    get_deadline_type,
    get_degree_levels,
    get_location,
    get_organization,
    get_pay,
    get_skills,
    get_start_term,
    get_title,
    get_work_mode,
    parse_date,
)
from service.schemas import ALL_FIELDS, Pay

DEFENSE = """Systems Engineering Intern, Summer 2027
Location: Huntsville, AL

About Ironpeak Defense
Ironpeak Defense builds guidance software for aerospace programs.

This is an on-site role. Must be a U.S. citizen. Active Secret clearance required.
Pursuing a Bachelor's or Master's degree in electrical engineering.
Experience with C/C++, MATLAB, and Linux.
Pay: $28 - $34 per hour.
Applications close December 5, 2026.
"""

STARTUP = """Software Engineering Intern
At Lumen Analytics, we help hospitals plan staffing.

We are a hybrid team: 3 days a week in our Denver, CO office.
Applications are reviewed on a rolling basis.
Students pursuing a BS/MS in Computer Science. Rising juniors and seniors welcome.
You'll write Python and SQL, with some React and TypeScript on the frontend.
Candidates must be authorized to work in the United States without visa sponsorship.
Compensation: $45/hr.
"""

REMOTE = """Data Science Intern - Summer or Fall 2027
Quillmark is a fully remote company.
This is a remote internship open to graduate students and PhD candidates.
Must be a U.S. citizen or permanent resident (ITAR).
Tools: Python or R, pandas, scikit-learn, and AWS.
Ability to obtain a security clearance is a plus.
"""

BARE = """We are looking for people who go above and beyond.
Tell us about yourself and why you'd be a great fit for the team.
"""


# ---------- whole postings ----------


def test_defense_posting():
    fields = RulesBackend().extract(DEFENSE, list(ALL_FIELDS))
    values = {name: result.value for name, result in fields.items()}
    assert values["title"] == "Systems Engineering Intern, Summer 2027"
    assert values["organization"] == "Ironpeak Defense"
    assert values["location"] == "Huntsville, AL"
    assert values["start_term"] == "Summer 2027"
    assert values["deadline"] == "2026-12-05"
    assert values["deadline_type"] == "FIXED"
    assert values["degree_levels"] == ["BACHELOR", "MASTER"]
    assert values["citizenship"] == "US_CITIZEN"
    assert values["clearance"] == "REQUIRED"
    assert values["work_mode"] == "ONSITE"
    assert values["pay"] == Pay(min=28, max=34, period="HOUR", currency="USD")
    assert values["skills"] == ["C", "C++", "MATLAB", "Linux"]


def test_startup_posting():
    fields = RulesBackend().extract(STARTUP, list(ALL_FIELDS))
    values = {name: result.value for name, result in fields.items()}
    assert values["title"] == "Software Engineering Intern"
    assert values["organization"] == "Lumen Analytics"
    assert values["location"] == "Denver, CO"
    assert values["deadline"] is None
    assert values["deadline_type"] == "ROLLING"
    assert values["degree_levels"] == ["BACHELOR", "MASTER"]
    assert values["citizenship"] == "NO_SPONSORSHIP"
    assert values["clearance"] == "NONE_MENTIONED"
    assert values["work_mode"] == "HYBRID"
    assert values["pay"] == Pay(min=45, max=45, period="HOUR", currency="USD")
    assert values["skills"] == ["Python", "TypeScript", "SQL", "React"]


def test_remote_posting():
    fields = RulesBackend().extract(REMOTE, list(ALL_FIELDS))
    values = {name: result.value for name, result in fields.items()}
    assert values["start_term"] == "Summer 2027"  # earliest of "Summer or Fall 2027"
    assert values["organization"] == "Quillmark"
    assert values["degree_levels"] == ["MASTER", "PHD"]
    assert values["citizenship"] == "US_PERSON"
    assert values["clearance"] == "PREFERRED"
    assert values["work_mode"] == "REMOTE"
    assert values["pay"] is None
    assert set(values["skills"]) == {"Python", "R", "pandas", "scikit-learn", "AWS"}


def test_bare_posting_falls_back_everywhere():
    fields = RulesBackend().extract(BARE, list(ALL_FIELDS))
    expected = {
        "title": None,
        "organization": None,
        "location": None,
        "start_term": None,
        "deadline": None,
        "deadline_type": "NONE_MENTIONED",
        "degree_levels": [],
        "citizenship": "NONE_MENTIONED",
        "clearance": "NONE_MENTIONED",
        "work_mode": "NONE_MENTIONED",
        "pay": None,
        "skills": [],  # "go above and beyond" is not the Go language
    }
    assert {name: result.value for name, result in fields.items()} == expected


# ---------- the FieldResult contract ----------


def test_returns_only_the_requested_fields():
    assert set(RulesBackend().extract(DEFENSE, ["pay", "deadline"])) == {"pay", "deadline"}


def test_matched_fields_have_high_confidence_and_evidence():
    result = RulesBackend().extract(DEFENSE, ["citizenship"])["citizenship"]
    assert result.confidence == MATCHED
    assert result.needs_review is False
    assert "U.S. citizen" in result.evidence
    assert result.source == "rules"


def test_fallback_fields_have_low_confidence_and_need_review():
    result = RulesBackend().extract(BARE, ["citizenship"])["citizenship"]
    assert result.confidence == FALLBACK
    assert result.needs_review is True
    assert result.evidence is None


def test_load_backend_knows_rules():
    backend = load_backend("rules")
    assert backend.name == "rules"
    assert backend.model_version == "rules-1"


# ---------- single rules ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Must be a U.S. citizen.", "US_CITIZEN"),
        ("US citizenship is required for this role.", "US_CITIZEN"),
        ("Must be a U.S. person as defined by ITAR.", "US_PERSON"),
        ("Must be a US citizen or lawful permanent resident.", "US_PERSON"),
        ("We are unable to sponsor visas.", "NO_SPONSORSHIP"),
        ("Must be eligible to work in the U.S.", "WORK_AUTHORIZED"),
        # most restrictive wins
        ("Must be eligible to work in the U.S. Must be a U.S. citizen.", "US_CITIZEN"),
        # EEO boilerplate is not a requirement
        ("We hire without regard to race, religion, or citizenship status.", None),
        ("Tell us about your projects.", None),  # "us" is not "US"
    ],
)
def test_citizenship(text, expected):
    hit = get_citizenship(text)
    assert (hit.value if hit else None) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Active TS/SCI clearance required.", "REQUIRED"),
        ("Ability to obtain and maintain a Secret clearance.", "ABLE_TO_OBTAIN"),
        ("Must obtain a security clearance within six months.", "ABLE_TO_OBTAIN"),
        ("Active clearance preferred.", "PREFERRED"),
        ("Clearance preferred.\nActive Secret clearance required.", "REQUIRED"),
        ("We have a clearance sale on hoodies.", None),
    ],
)
def test_clearance(text, expected):
    hit = get_clearance(text)
    assert (hit.value if hit else None) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This is a hybrid role.", "HYBRID"),
        ("2-3 days per week in the office.", "HYBRID"),
        ("We build hybrid cloud tooling. This role is on-site.", "ONSITE"),
        ("This is a fully remote position.", "REMOTE"),
        ("Work from home with an on-site kickoff week.", "REMOTE"),
        ("Our office is in Austin, TX.", None),  # an address alone isn't evidence
    ],
)
def test_work_mode(text, expected):
    hit = get_work_mode(text)
    assert (hit.value if hit else None) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("November 15, 2026", "2026-11-15"),
        ("Nov. 15th, 2026", "2026-11-15"),
        ("Sept 3, 2026", "2026-09-03"),
        ("15 November 2026", "2026-11-15"),
        ("11/15/2026", "2026-11-15"),
        ("2026-11-15", "2026-11-15"),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw).isoformat() == expected


def test_deadline_takes_the_final_date():
    text = "Priority deadline: October 1, 2026. Final deadline: November 15, 2026."
    assert get_deadline(text).value == "2026-11-15"


def test_rolling_with_a_close_date_is_fixed():
    text = "Rolling review; applications close Dec 5, 2026."
    assert get_deadline_type(text).value == "FIXED"
    assert get_deadline(text).value == "2026-12-05"


def test_dates_that_are_not_deadlines_are_ignored():
    assert get_deadline("The program starts June 1, 2027.") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pursuing a bachelor's degree.", ["BACHELOR"]),
        ("Bachelor's degree or higher.", ["BACHELOR", "MASTER", "PHD"]),
        ("Undergraduate students only.", ["BACHELOR"]),
        ("Open to graduate students.", ["MASTER", "PHD"]),
        ("MBA candidates.", ["MASTER"]),
        ("Ph.D. in physics.", ["PHD"]),
        ("Proficient in MS Office.", None),
        ("You will master new tools quickly.", None),
    ],
)
def test_degree_levels(text, expected):
    hit = get_degree_levels(text)
    assert (hit.value if hit else None) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Experience with Postgres and k8s.", ["PostgreSQL", "Kubernetes"]),
        ("Go, Rust, or Java.", ["Java", "Go", "Rust"]),
        ("Ready to go the extra mile.", None),
        ("Strong R&D background.", None),
        ("JavaScript and Java.", ["Java", "JavaScript"]),
        ("Python (pandas, NumPy).", ["Python", "pandas", "NumPy"]),
    ],
)
def test_skills(text, expected):
    hit = get_skills(text)
    assert (hit.value if hit else None) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$25–$32/hr", Pay(min=25, max=32, period="HOUR", currency="USD")),
        ("$80,000 per year", Pay(min=80000, max=80000, period="YEAR", currency="USD")),
        ("$80K - $95K", Pay(min=80000, max=95000, period="YEAR", currency="USD")),
        ("Up to $40/hour", Pay(min=None, max=40, period="HOUR", currency="USD")),
        ("$6,000 monthly stipend", Pay(min=6000, max=6000, period="UNKNOWN", currency="USD")),
        ("C$30 per hour", Pay(min=30, max=30, period="HOUR", currency="CAD")),
        (
            "NYC: $35-$40/hr. Austin: $30-$36/hr.",
            Pay(min=30, max=40, period="HOUR", currency="USD"),
        ),
        ("$5,000 relocation bonus.", None),
        ("Competitive pay.", None),
    ],
)
def test_pay(text, expected):
    hit = get_pay(text)
    assert (hit.value if hit else None) == expected


def test_title_location_organization_start_term_fallbacks():
    assert get_title("About the team\nWe build things.") is None
    assert get_organization("About the role\nYou will build things.") is None
    assert get_location("Remote-friendly team.") is None
    assert get_start_term("Starting ASAP.") is None


def test_organization_drops_legal_suffix():
    assert get_organization("At Acme Robotics Inc., we build robots.").value == "Acme Robotics"


def test_start_term_handles_autumn_and_of():
    assert get_start_term("Starting in Autumn of 2027.").value == "Fall 2027"
