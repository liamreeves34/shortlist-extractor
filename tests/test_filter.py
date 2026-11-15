"""Step 2.4: service/connectors/filter.py. Write these before the code."""

import pytest

from service.connectors.filter import is_internship


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineering Intern",
        "Summer 2027 Internship",
        "Co-op, Data",
        "Data Engineer (Intern)",
        "Software Engineer - Internship",
        "SOFTWARE ENGINEERING INTERN",
        "Student Researcher",
    ],
)
def test_internship_titles(title):
    assert is_internship(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Internal Audit Manager",  # a naive `"intern" in title` gets this wrong
        "International Sales",
        "Internet Security Engineer",
        "Senior Backend Engineer",
        "Cooperative Partnerships Lead",
    ],
)
def test_non_internship_titles(title):
    assert is_internship(title) is False


def test_commitment_alone_marks_an_internship():
    assert is_internship("Engineer", commitment="Intern") is True


def test_commitment_internship_spelling():
    assert is_internship("Engineer", commitment="Internship") is True


def test_full_time_commitment_is_not_an_internship():
    assert is_internship("Engineer", commitment="Full-time") is False


# Lever commitments are free text, typed by each employer.
@pytest.mark.parametrize(
    ("commitment", "expected"),
    [
        ("Intern (Hourly)", True),
        ("Summer Internship", True),
        ("Co-op / Internship", True),
        ("Regular Full Time (Salary)", False),
        ("Part-time", False),
        ("Contract", False),
    ],
)
def test_free_text_commitments(commitment, expected):
    assert is_internship("Engineer", commitment=commitment) is expected


def test_title_wins_over_a_full_time_commitment():
    assert is_internship("Software Engineering Intern", commitment="Full-time") is True


def test_missing_commitment_falls_back_to_the_title():
    assert is_internship("Engineer", commitment=None) is False
