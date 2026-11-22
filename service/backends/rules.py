"""Step 4.1: the rules backend. Regexes and keyword lists, one function per field.

Every `get_<field>(text)` returns a Hit (the value plus the line it came from) or None.
`extract` turns None into the field's "not stated" value from docs/labeling_guide.md,
with low confidence. Confidence is a placeholder until Stage 7 measures it:
0.9 when a pattern matched, 0.3 when the field fell back to its default.

Patterns are compiled with re.IGNORECASE unless noted. Where case matters (US vs "us",
React vs "react", Go vs "go") the pattern uses a case-sensitive group: (?-i:...).
"""

import re
from datetime import date, datetime
from typing import NamedTuple

from service.connectors.filter import INTERNSHIP_RE_PATTERN
from service.schemas import FieldResult, Pay

MATCHED, FALLBACK = 0.9, 0.3


class Hit(NamedTuple):
    value: object
    evidence: str


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def _line(text: str, match: re.Match) -> str:
    """The line a match sits on, as evidence (trimmed to 200 characters)."""
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    line = text[start : end if end != -1 else len(text)].strip()
    return line[:200]


def _first(text: str, table: list[tuple[str, re.Pattern]]) -> Hit | None:
    """Try each (value, pattern) in order; the first that matches wins."""
    for value, pattern in table:
        match = pattern.search(text)
        if match:
            return Hit(value, _line(text, match))
    return None


# Shared pieces
US = r"(?:(?-i:U\.\s?S\.(?:A\.)?|US|USA)|united\s+states)"
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"


# ---------- citizenship ----------

# Not followed by "or permanent resident" / "or green card" (that's US_PERSON).
NOT_OR_PR = r"(?!\s*(?:or|/|and)\s+(?:a\s+)?(?:lawful\s+)?(?:permanent|green))"

CITIZENSHIP = [  # most restrictive first
    (
        "US_CITIZEN",
        _rx(
            rf"(?:must|required\s+to)\s+(?:be|hold)\s+(?:a\s+)?{US}\s+citizen(?:ship)?{NOT_OR_PR}"
            rf"|{US}\s+citizenship\s+(?:is\s+)?required"
            rf"|{US}\s+citizens\s+only"
        ),
    ),
    (
        "US_PERSON",
        _rx(
            rf"{US}\s+persons?\b"
            r"|citizens?\s+(?:or|/)\s+(?:a\s+)?(?:lawful\s+)?permanent\s+residents?"
            r"|citizens?\s+or\s+green\s+card"
        ),
    ),
    (
        "NO_SPONSORSHIP",
        _rx(
            r"(?:not|unable\s+to|cannot|can't|won't)\s+(?:\w+\s+){0,3}sponsor"
            r"|without\s+(?:\w+\s+){0,4}sponsorship"
            r"|sponsorship\s+(?:\w+\s+){0,3}not\s+(?:be\s+)?(?:available|offered|provided)"
        ),
    ),
    (
        "WORK_AUTHORIZED",
        _rx(
            rf"(?:authori[sz]ed|eligible|legally\s+able)\s+to\s+work\s+in\s+the\s+{US}"
            rf"|{US}\s+work\s+authori[sz]ation"
        ),
    ),
]


def get_citizenship(text: str) -> Hit | None:
    return _first(text, CITIZENSHIP)


# ---------- clearance ----------

CLEARANCE_MENTION = _rx(
    r"\bsecurity\s+clearance\b"
    r"|\b(?:secret|top\s+secret|ts/sci|dod|government|federal|active)\s+clearance\b"
    r"|\bclearance\s+(?:is\s+)?required\b"
    r"|\bobtain\s+(?:and\s+maintain\s+)?(?:a|an)?\s*clearance\b"
    r"|\bTS/SCI\b"
)
CLEARANCE_PREFERRED = _rx(r"prefer|a\s+plus|desired|nice\s+to\s+have|bonus")
CLEARANCE_OBTAIN = _rx(r"obtain|eligib|able\s+to|ability\s+to|willing")
CLEARANCE_ORDER = ["REQUIRED", "ABLE_TO_OBTAIN", "PREFERRED"]  # most restrictive first


def get_clearance(text: str) -> Hit | None:
    """Classify each line that mentions a clearance; the most restrictive line wins."""
    best: Hit | None = None
    for match in CLEARANCE_MENTION.finditer(text):
        line = _line(text, match)
        if CLEARANCE_PREFERRED.search(line):
            value = "PREFERRED"
        elif CLEARANCE_OBTAIN.search(line):
            value = "ABLE_TO_OBTAIN"
        else:
            value = "REQUIRED"
        if best is None or CLEARANCE_ORDER.index(value) < CLEARANCE_ORDER.index(best.value):
            best = Hit(value, line)
    return best


# ---------- work_mode ----------

WORK_MODE = [  # hybrid first: hybrid postings also mention the office
    (
        "HYBRID",
        _rx(
            r"\bhybrid\b(?!\s+(?:cloud|vehicles?|apps?|systems?|engines?))"
            r"|\b\d\s*(?:-\s*\d\s*)?days?\s+(?:a|per)\s+week\s+in\s+(?:the\s+|our\s+)?office"
            r"|\b\d\s*(?:-\s*\d\s*)?days?\s+in\s+(?:the\s+|our\s+)?office"
        ),
    ),
    (
        "REMOTE",
        _rx(
            r"\bfully\s+remote\b|\b100%\s+remote\b"
            r"|\bremote\s+(?:position|role|internship|opportunity|work)\b"
            r"|\bwork\s+(?:from\s+home|remotely)\b"
            r"|\b(?:this|is)\s+(?:a\s+)?remote\b"
        ),
    ),
    (
        "ONSITE",
        _rx(r"\bon[\s-]?site\b|\bin[\s-]office\b|\bin[\s-]person\b|\bfully\s+in\s+office\b"),
    ),
]


def get_work_mode(text: str) -> Hit | None:
    return _first(text, WORK_MODE)


# ---------- deadline and deadline_type ----------

DATE = (
    rf"{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"  # November 15, 2026
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH},?\s+\d{{4}}"  # 15 November 2026
    r"|\d{1,2}/\d{1,2}/\d{4}"  # 11/15/2026
    r"|\d{4}-\d{2}-\d{2}"  # 2026-11-15
)
DEADLINE_WORDS = (
    r"deadline|apply\s+by|applications?\s+(?:\w+\s+){0,2}(?:close|due)|closing\s+date"
    r"|no\s+later\s+than|(?:submit|submitted)\s+(?:\w+\s+){0,4}by"
    r"|accept(?:ing|ed)\s+(?:applications\s+)?(?:through|until)"
)
# A deadline word, then a date within the next 100 characters on the same line.
DEADLINE = _rx(rf"(?:{DEADLINE_WORDS})[^\n]{{0,100}}?({DATE})")

ROLLING = _rx(
    r"rolling\s+(?:basis|review|admissions?)"
    r"|until\s+(?:the\s+)?(?:position|role|internship)\s+is\s+filled"
    r"|until\s+filled"
)


def parse_date(raw: str) -> date | None:
    """'Nov. 15th, 2026', '15 November 2026', '11/15/2026', '2026-11-15' -> date."""
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", raw)
    cleaned = cleaned.replace(",", " ").replace(".", " ")
    cleaned = re.sub(r"\bsept\b", "sep", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split())
    for fmt in ("%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def get_deadline(text: str) -> Hit | None:
    """The latest dated deadline (the guide: priority and final deadlines -> the final one)."""
    best: tuple[date, str] | None = None
    for match in DEADLINE.finditer(text):
        found = parse_date(match.group(1))
        if found and (best is None or found > best[0]):
            best = (found, _line(text, match))
    return Hit(best[0].isoformat(), best[1]) if best else None


def get_deadline_type(text: str) -> Hit | None:
    """FIXED if there's a dated deadline (a hard close beats "rolling"), else ROLLING."""
    deadline = get_deadline(text)
    if deadline:
        return Hit("FIXED", deadline.evidence)
    match = ROLLING.search(text)
    return Hit("ROLLING", _line(text, match)) if match else None


# ---------- degree_levels ----------

DEGREES = [  # in the guide's order
    ("HIGH_SCHOOL", _rx(r"\bhigh\s+school\b")),
    ("ASSOCIATE", _rx(r"\bassociate'?s?\s+degree\b")),
    (
        "BACHELOR",
        _rx(
            r"\bbachelor'?s?\b|\bundergrad(?:uate)?\b"
            r"|\b(?-i:B\.S\.|B\.A\.|BS|BA|BSc|BEng|B\.Eng\.?)(?![\w.])"
            r"|\brising\s+(?:sophomore|junior|senior)s?\b"
        ),
    ),
    (
        "MASTER",
        _rx(
            r"\bmaster'?s\b|\bmasters?\s+(?:degree|program|student)"
            r"|\b(?-i:M\.S\.|MS|MSc|MEng|M\.Eng\.?|MBA)(?![\w.])(?!\s+(?:Office|Excel|Word|Teams))"
        ),
    ),
    ("PHD", _rx(r"\bPh\.?\s?D\b|\bdoctoral\b|\bdoctorate\b")),
]
GRADUATE = _rx(r"(?<!under)\bgraduate\s+(?:student|degree|program|studies)")
OR_HIGHER = _rx(r"bachelor'?s?\s+(?:degree\s+)?(?:or|and)\s+(?:higher|above)")


def get_degree_levels(text: str) -> Hit | None:
    found: dict[str, str] = {}
    for level, pattern in DEGREES:
        match = pattern.search(text)
        if match:
            found[level] = _line(text, match)
    for pattern in (GRADUATE, OR_HIGHER):
        match = pattern.search(text)
        if match:  # "graduate student" or "bachelor's or higher" -> master's and PhD too
            for level in ("MASTER", "PHD"):
                found.setdefault(level, _line(text, match))
    if not found:
        return None
    levels = [level for level, _ in DEGREES if level in found]
    return Hit(levels, found[levels[0]])


# ---------- skills ----------

# Canonical name -> pattern. Ambiguous short names (C, Go, R) only count in a list,
# e.g. "C/C++", "Go, Rust", "Python or R".
LIST_NEXT = r"(?=\s*(?:,|/|\)|\band\b|\bor\b))"
SKILLS = [
    ("Python", _rx(r"\bpython\b")),
    ("Java", _rx(r"\bjava\b")),
    ("JavaScript", _rx(r"\bjavascript\b|(?-i:\bJS\b)")),
    ("TypeScript", _rx(r"\btypescript\b")),
    ("C", _rx(rf"(?-i:\bC\b)(?![+#]){LIST_NEXT}")),
    ("C++", _rx(r"\bC\+\+")),
    ("C#", _rx(r"\bC#")),
    ("Go", _rx(rf"\bgolang\b|(?-i:\bGo\b){LIST_NEXT}")),
    ("Rust", _rx(r"(?-i:\bRust\b)")),
    ("Ruby", _rx(r"\bruby\b")),
    ("Kotlin", _rx(r"\bkotlin\b")),
    ("Swift", _rx(r"(?-i:\bSwift\b)")),
    ("Scala", _rx(r"\bscala\b")),
    ("R", _rx(rf"(?-i:\bR\b)(?!&){LIST_NEXT}")),
    ("MATLAB", _rx(r"\bmatlab\b")),
    ("SQL", _rx(r"\bSQL\b")),
    ("PostgreSQL", _rx(r"\bpostgres(?:ql)?\b")),
    ("MySQL", _rx(r"\bmysql\b")),
    ("MongoDB", _rx(r"\bmongo(?:db)?\b")),
    ("HTML", _rx(r"\bHTML5?\b")),
    ("CSS", _rx(r"\bCSS3?\b")),
    ("React", _rx(r"(?-i:\bReact(?:\.js|JS)?\b)(?!\s+Native)")),
    ("Node.js", _rx(r"\bnode(?:\.js|js)\b")),
    ("Django", _rx(r"\bdjango\b")),
    ("Flask", _rx(r"(?-i:\bFlask\b)")),
    ("PyTorch", _rx(r"\bpytorch\b")),
    ("TensorFlow", _rx(r"\btensorflow\b")),
    ("scikit-learn", _rx(r"\bscikit-learn\b|\bsklearn\b")),
    ("pandas", _rx(r"\bpandas\b")),
    ("NumPy", _rx(r"\bnumpy\b")),
    ("Spark", _rx(r"(?-i:\b(?:Apache\s+)?Spark\b)|\bpyspark\b")),
    ("Kafka", _rx(r"\bkafka\b")),
    ("AWS", _rx(r"(?-i:\bAWS\b)|\bamazon\s+web\s+services\b")),
    ("GCP", _rx(r"(?-i:\bGCP\b)|\bgoogle\s+cloud\b")),
    ("Azure", _rx(r"(?-i:\bAzure\b)")),
    ("Docker", _rx(r"\bdocker\b")),
    ("Kubernetes", _rx(r"\bkubernetes\b|\bk8s\b")),
    ("Git", _rx(r"(?-i:\bGit\b)|\bgithub\b")),
    ("Linux", _rx(r"\blinux\b")),
    ("Bash", _rx(r"\bbash\b")),
    ("Excel", _rx(r"(?-i:\bExcel\b)(?!\s+(?:in|at)\b)")),
    ("Tableau", _rx(r"\btableau\b")),
    ("Figma", _rx(r"\bfigma\b")),
    ("Verilog", _rx(r"\b(?:system)?verilog\b")),
    ("VHDL", _rx(r"\bvhdl\b")),
    ("SolidWorks", _rx(r"\bsolidworks\b")),
]


def get_skills(text: str) -> Hit | None:
    found: list[str] = []
    evidence = ""
    for name, pattern in SKILLS:
        match = pattern.search(text)
        if match:
            found.append(name)
            evidence = evidence or _line(text, match)
    return Hit(found, evidence) if found else None


# ---------- pay ----------

AMOUNT = r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?"
PAY = _rx(rf"(?:(up\s+to|starting\s+at)\s+)?({AMOUNT})(?:\s*(?:-|–|—|to)\s*({AMOUNT}))?")
HOUR = _rx(r"/\s?h(?:ou)?r\b|per\s+hour|an\s+hour|\bhourly\b")
YEAR = _rx(r"/\s?y(?:ea)?r\b|per\s+year|a\s+year|\bannual(?:ly)?\b|per\s+annum|\bsalary\b")
OTHER_PERIOD = _rx(r"per\s+(?:month|week)|/\s?(?:mo|month|wk|week)\b|\bmonthly\b|\bweekly\b")
NOT_PAY = _rx(r"relocation|bonus|signing|housing|equity|reimburs|401")
CAD = _rx(r"\bCAD\b|\bC\$|\bCA\$")


def _amount(raw: str) -> float:
    raw = raw.replace("$", "").replace(",", "").strip().lower()
    value = float(raw.removesuffix("k")) * (1000 if raw.endswith("k") else 1)
    return int(value) if value.is_integer() else value


def _period(window: str, top: float) -> str:
    if OTHER_PERIOD.search(window):
        return "UNKNOWN"
    if HOUR.search(window):
        return "HOUR"
    if YEAR.search(window):
        return "YEAR"
    return "YEAR" if top >= 10_000 else "UNKNOWN"  # "$80,000-$95,000" with no unit


def get_pay(text: str) -> Hit | None:
    """Every $ amount or range with its period, read from the 40 characters around it.

    Ranges sharing the first range's period are merged (lowest min, highest max).
    Amounts next to relocation, bonus, housing or equity words are skipped.
    """
    ranges = []
    for match in PAY.finditer(text):
        window = text[max(0, match.start() - 40) : match.end() + 40]
        if NOT_PAY.search(window):
            continue
        qualifier = (match.group(1) or "").lower()
        low = _amount(match.group(2))
        high = _amount(match.group(3)) if match.group(3) else low
        if qualifier.startswith("up"):
            low = None
        elif qualifier.startswith("starting"):
            high = None
        top = high if high is not None else low
        period = _period(window, top)
        currency = "CAD" if CAD.search(window) else "USD"
        ranges.append((low, high, period, currency, _line(text, match)))
    if not ranges:
        return None

    period, currency, evidence = ranges[0][2], ranges[0][3], ranges[0][4]
    same = [r for r in ranges if r[2] == period]
    lows = [r[0] for r in same if r[0] is not None]
    highs = [r[1] for r in same if r[1] is not None]
    pay = Pay(
        min=min(lows) if lows else None,
        max=max(highs) if highs else None,
        period=period,
        currency=currency,
    )
    return Hit(pay, evidence)


# ---------- title, organization, location, start_term ----------


def get_title(text: str) -> Hit | None:
    """A short line near the top that names an internship."""
    for line in text.splitlines()[:15]:
        line = line.strip()
        if 0 < len(line) <= 100 and INTERNSHIP_RE_PATTERN.search(line):
            return Hit(line.rstrip(":"), line)
    return None


LEGAL_SUFFIX = _rx(r",?\s+(?:inc\.?|llc|ltd\.?|corp\.?|corporation)$")
ORG_PATTERNS = [
    # "About Acme Robotics" heading (not "About the role", "About you")
    re.compile(
        r"^\s*about\s+(?!(?:the|this|you|us|our|me)\b)([^\n:]{2,60}?)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    # "At Acme Robotics, we ..."
    re.compile(r"\bAt\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3}),\s+(?:we|our)\b"),
    # "Acme Robotics is a/an/the ..." at the start of a line
    re.compile(r"^([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\s+is\s+(?:a|an|the)\b", re.MULTILINE),
]


def get_organization(text: str) -> Hit | None:
    for pattern in ORG_PATTERNS:
        match = pattern.search(text)
        if match:
            name = LEGAL_SUFFIX.sub("", match.group(1).strip())
            return Hit(name, _line(text, match))
    return None


STATE = (
    r"A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]"
    r"|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY]"
)
LOCATION_LINE = _rx(r"^\s*locations?\s*[:\-–]\s*(.+?)\s*$")
CITY_STATE = re.compile(rf"\b([A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z.]+){{0,2}}),\s((?:{STATE}))\b")


def get_location(text: str) -> Hit | None:
    """A "Location:" line if there is one, otherwise the first "City, ST"."""
    for line in text.splitlines():
        match = LOCATION_LINE.match(line)
        if match:
            return Hit(match.group(1), line.strip())
    match = CITY_STATE.search(text)
    return Hit(f"{match.group(1)}, {match.group(2)}", _line(text, match)) if match else None


SEASONS = ["spring", "summer", "fall", "winter"]
TERM = _rx(
    r"\b(spring|summer|fall|autumn|winter)"
    r"(?:\s+(?:or|and|/)\s+(?:spring|summer|fall|autumn|winter))?"
    r"\s+(?:of\s+)?(20\d\d)\b"
)


def get_start_term(text: str) -> Hit | None:
    """The earliest "Season YYYY" mentioned ("Summer or Fall 2027" -> Summer 2027)."""
    best = None
    for match in TERM.finditer(text):
        season = match.group(1).lower().replace("autumn", "fall")
        key = (int(match.group(2)), SEASONS.index(season))
        if best is None or key < best[0]:
            best = (key, f"{season.title()} {match.group(2)}", _line(text, match))
    return Hit(best[1], best[2]) if best else None


# ---------- the backend ----------

# field -> (function, value when nothing matched), defaults from docs/labeling_guide.md
FIELDS = {
    "title": (get_title, None),
    "organization": (get_organization, None),
    "location": (get_location, None),
    "start_term": (get_start_term, None),
    "deadline": (get_deadline, None),
    "deadline_type": (get_deadline_type, "NONE_MENTIONED"),
    "degree_levels": (get_degree_levels, []),
    "citizenship": (get_citizenship, "NONE_MENTIONED"),
    "clearance": (get_clearance, "NONE_MENTIONED"),
    "work_mode": (get_work_mode, "NONE_MENTIONED"),
    "pay": (get_pay, None),
    "skills": (get_skills, []),
}


class RulesBackend:
    name = "rules"
    model_version = "rules-1"

    def extract(self, text: str, fields: list[str]) -> dict[str, FieldResult]:
        results = {}
        for field in fields:
            get, default = FIELDS[field]
            hit = get(text)
            if hit is None:
                results[field] = FieldResult(
                    value=default,
                    confidence=FALLBACK,
                    evidence=None,
                    needs_review=True,
                    source="rules",
                )
            else:
                results[field] = FieldResult(
                    value=hit.value,
                    confidence=MATCHED,
                    evidence=hit.evidence,
                    needs_review=False,
                    source="rules",
                )
        return results
