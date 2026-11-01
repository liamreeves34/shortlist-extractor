import re

INTERNSHIP_KEYWORDS = [
    "intern",
    "interns",
    "internship",
    "internships",
    "co-op",
    "coop",
    "extern",
    "externship",
    "student researcher",
    "student trainee",
    "working student",
    "summer student",
    "summer analyst",
    "summer associate",
    "industrial placement",
    "year in industry",
    "undergraduate researcher",
    "undergraduate research assistant",
]
# define the regex pattern: given some string, we check if there is a component in the list
INTERNSHIP_RE_PATTERN = re.compile(rf"\b(?:{'|'.join(INTERNSHIP_KEYWORDS)})\b", re.IGNORECASE)

# we want to check if any of the components of title or commitment match the pattern defined


def is_internship(title: str, commitment: str | None = None) -> bool:
    if commitment is not None and INTERNSHIP_RE_PATTERN.search(
        commitment
    ):  # check if the commitment is an internship
        return True  # the commitment matched our internship criteria so we return true

    return bool(INTERNSHIP_RE_PATTERN.search(title))
