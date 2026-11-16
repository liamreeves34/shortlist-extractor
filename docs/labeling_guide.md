# Labeling guide

How to label a posting for the gold set. Every backend (rules, teacher, student) is scored
against these labels, so they must be **consistent**: two people, or you on two different
days, should produce the same label for the same posting. When this guide and your instinct
disagree, follow the guide. When the guide doesn't cover a case, decide, then add the case to
[Decisions log](#decisions-log) so the next posting gets the same answer.

Version: 1 (2026-11-14)

---

## General rules

1. **Label only what the text says.** The model sees only the posting text, so the label must
   be recoverable from that text. Don't use the API's structured fields, the company's website,
   or what you know about the employer. A posting that says "Austin, TX" but never says
   "in office" has `work_mode = NONE_MENTIONED`.
2. **Ignore boilerplate that isn't about this role.** Equal-opportunity statements ("without
   regard to citizenship status..."), benefits paragraphs for full-time staff, and company-wide
   policies don't count as requirements.
3. **Requirements and preferences both count**, unless a field says otherwise.
4. **When several statements conflict, the most specific or most restrictive one wins.** Each
   field lists its order.
5. **"Not stated" has one spelling per field.** Category fields use `NONE_MENTIONED`, text and
   object fields use `null`, list fields use `[]`. Never leave a field out.
6. **Unsure?** Pick the best label under these rules and set `"unsure": true` on the record.
   Revisit unsure postings at the end and turn any new decisions into log entries.

### Record format

One JSON object per line in `data/labels/gold.jsonl`:

```json
{"hash": "sha256:…", "labeled_at": "2026-11-14", "guide_version": 1, "unsure": false,
 "fields": {
   "title": "Software Engineering Intern, Summer 2027",
   "organization": "Acme Robotics",
   "location": "Austin, TX",
   "start_term": "Summer 2027",
   "deadline": "2026-12-01",
   "deadline_type": "FIXED",
   "degree_levels": ["BACHELOR", "MASTER"],
   "citizenship": "NONE_MENTIONED",
   "clearance": "NONE_MENTIONED",
   "work_mode": "HYBRID",
   "pay": {"min": 30, "max": 38, "period": "HOUR", "currency": "USD"},
   "skills": ["Python", "SQL"]
 }}
```

Labels are your own work, so they're committed. Evidence sentences are quotes of employer
text, so they are **not** committed. If the helper records evidence, keep it in a gitignored
file.

### Summary

| Field | Type | Not stated | Scored by |
| --- | --- | --- | --- |
| `title` | text | — (always present) | exact match* |
| `organization` | text | — (always present) | exact match* |
| `location` | text | `null` | exact match* |
| `start_term` | text | `null` | exact match* |
| `deadline` | `YYYY-MM-DD` | `null` | exact match |
| `deadline_type` | category | `NONE_MENTIONED` | accuracy, macro-F1 |
| `degree_levels` | set | `[]` | set P/R/F1 |
| `citizenship` | category | `NONE_MENTIONED` | accuracy, macro-F1 |
| `clearance` | category | `NONE_MENTIONED` | accuracy, macro-F1 |
| `work_mode` | category | `NONE_MENTIONED` | accuracy, macro-F1 |
| `pay` | object | `null` | per-part match |
| `skills` | set | `[]` | set P/R/F1 |

\* after lowercasing and trimming. Case doesn't matter, but punctuation and wording do, so the
formats below matter.

---

## Text fields

### `title`

The role's title as the posting states it.

- Copy it from the posting's heading. Keep the term or year if it's part of the title
  ("Data Science Intern, Summer 2027").
- Remove requisition IDs and codes: "Software Intern (R-104552)" → "Software Intern".
- Remove location suffixes that just repeat the location field:
  "ML Intern - New York, NY" → "ML Intern".
- Keep the posting's own wording. Don't expand "SWE" or fix capitalization.

### `organization`

The employer as the posting names itself.

- Drop legal suffixes: "Acme Robotics, Inc." → "Acme Robotics". Drop "LLC", "Ltd.", "Corp."
  and "Corporation" too, unless removing it leaves an ambiguous name.
- If a subsidiary posts the job, use the name the posting uses ("AWS", not "Amazon", if the
  posting says AWS).
- Recruiting agencies: use the hiring company if the posting names it, otherwise the agency.

### `location`

Where the intern works.

| Case | Format | Example |
| --- | --- | --- |
| US city | `City, ST` (USPS state code) | `Austin, TX` |
| Non-US city | `City, Country` | `Toronto, Canada` |
| Nicknames | the city's official name | "NYC" → `New York, NY`; "SF" → `San Francisco, CA` |
| Region | the region as written, plus state | `San Francisco Bay Area, CA` |
| Fully remote | `Remote`, plus country in parentheses if restricted | `Remote (US)` |
| Hybrid or onsite | the office city; the mode goes in `work_mode` | `Chicago, IL` |
| Several locations | each one, in the posting's order, joined by `; ` | `Seattle, WA; Austin, TX` |
| Several locations plus remote | the cities, then `Remote` | `Denver, CO; Remote (US)` |
| "Multiple locations" with no list | `null` | |

### `start_term`

When the internship starts: `Spring`, `Summer`, `Fall` or `Winter`, a space, and a four-digit
year. For example, `Summer 2027`.

- If the posting gives months, map the **start** month: Jan–Apr → Spring, May–Aug → Summer,
  Sep–Dec → Fall. Use Winter only if the posting says "Winter".
  "June–August 2027" → `Summer 2027`.
- Several possible terms ("Summer or Fall 2027"): use the **earliest**.
- Co-ops spanning terms ("January–August 2027"): use the start, `Spring 2027`.
- A term with no year: use the year only if the posting makes it unambiguous, for example the
  title says 2027. Otherwise `null`.
- "Starting ASAP" or "flexible start": `null`.

---

## Deadline

### `deadline_type`

| Value | When |
| --- | --- |
| `FIXED` | The posting gives a date by which applications must be in. |
| `ROLLING` | The posting says applications are reviewed on a rolling basis, or "until filled", with no closing date. |
| `NONE_MENTIONED` | Neither. |

- "Rolling basis, applications close December 1": `FIXED`. A hard close date wins.
- "Apply early, we review on a rolling basis" with no date: `ROLLING`.
- A date for something else (interview dates, the program start, a career fair) isn't a
  deadline.

### `deadline`

The application close date as `YYYY-MM-DD`, or `null`.

- `null` whenever `deadline_type` isn't `FIXED`.
- Use the last day applications are accepted. "Apply by November 15" → `…-11-15`.
  "Applications close at 11:59 pm PT on Nov 15" → `…-11-15`. Ignore times and time zones.
- A date with no year: use the next occurrence after the posting was published. If you can't
  tell, use `null` and set `unsure`.
- Several deadlines (priority and final): use the **final** one.

---

## `degree_levels`

The degree programs the posting targets. A set of:
`HIGH_SCHOOL`, `ASSOCIATE`, `BACHELOR`, `MASTER`, `PHD`.

- Count both "currently pursuing" and "completed".
- MBA, MS, MEng and MA are all `MASTER`. MD and JD aren't in the set, so leave them out.
- "BS/MS in CS" → `["BACHELOR", "MASTER"]`.
- "Bachelor's or higher" → `["BACHELOR", "MASTER", "PHD"]`. Expand "or higher" and "or above".
- "Undergraduate" → `BACHELOR`. "Graduate student" → `["MASTER", "PHD"]`.
- "Rising juniors and seniors" → `BACHELOR`, because class years imply the level.
- "Students" with no level, or a field of study with no level: `[]`.
- Order doesn't matter, but write them in the order above for readability.

---

## Eligibility

These two fields decide whether a student can apply at all, so they get the most care.

### `citizenship`

What the posting requires about nationality or work status. Most restrictive first:

| Value | When | Examples |
| --- | --- | --- |
| `US_CITIZEN` | Only US citizens. | "Must be a U.S. citizen" |
| `US_PERSON` | US persons under export-control law: citizens, permanent residents, refugees, asylees. | "Must be a U.S. person", "ITAR/EAR: U.S. person required", "U.S. citizen or permanent resident" |
| `NO_SPONSORSHIP` | Must be authorized to work **without** visa sponsorship, now or in the future. | "We are unable to sponsor visas", "must not require sponsorship now or in the future" |
| `WORK_AUTHORIZED` | Must be authorized to work in the US, with nothing said about sponsorship. | "Must be eligible to work in the U.S." |
| `NONE_MENTIONED` | None of the above. | |

- "U.S. person" is `US_PERSON`, never `US_CITIZEN`. Permanent residents qualify.
- "U.S. citizen or green card holder" is `US_PERSON`. It's the same group in practice.
- Several statements: use the **most restrictive** one, the highest row in the table.
- Don't infer citizenship from clearance. "Must obtain a Secret clearance" alone is
  `citizenship = NONE_MENTIONED`, `clearance = ABLE_TO_OBTAIN`, even though clearances
  require citizenship in practice. Rule 1: label what the text says.
- EEO boilerplate ("without regard to … citizenship status") is `NONE_MENTIONED`.
- Requirements about another country ("must have the right to work in Canada") are
  `NONE_MENTIONED`. This field is about the US only. Add a log entry if they turn out to
  be common.

### `clearance`

What the posting requires about a US security clearance. Most restrictive first:

| Value | When | Examples |
| --- | --- | --- |
| `REQUIRED` | Must already hold an active clearance. | "Active Secret clearance required" |
| `ABLE_TO_OBTAIN` | Must be able or willing to obtain one. | "Ability to obtain a clearance", "must be eligible for a Secret clearance" |
| `PREFERRED` | A clearance is a plus but not required. | "Active clearance preferred" |
| `NONE_MENTIONED` | No clearance mentioned. | |

- The clearance level (Secret, TS/SCI) isn't recorded.
- "Must obtain within six months of hire" is `ABLE_TO_OBTAIN`.
- "Some roles on this team require a clearance", where it's unclear whether this role does:
  `NONE_MENTIONED`, with `unsure` set.

---

## `work_mode`

| Value | When |
| --- | --- |
| `ONSITE` | Says in office or on site full time. |
| `HYBRID` | Some days in office and some remote, or explicitly "hybrid". |
| `REMOTE` | Fully remote. A few onsite events, like an orientation week, still count as remote. |
| `NONE_MENTIONED` | Gives a location but says nothing about where the work happens. |

- An office address alone isn't evidence of `ONSITE` (rule 1).
- "Remote or in our Austin office": the posting lets you choose, so `REMOTE`.
- "Remote, must live within commuting distance of Denver" is `REMOTE`. That's a location
  restriction, not office time.
- Write `ONSITE` as one word, without the Lever API's hyphen.

---

## `pay`

`{"min": number|null, "max": number|null, "period": "HOUR"|"YEAR"|"UNKNOWN", "currency": "USD"|…}`,
or `null` if the posting gives no pay figure.

- **Numbers** are plain numbers: "$80K" → `80000`, "$32.50/hr" → `32.5`.
- **Ranges:** "$25–$32/hr" → `{"min": 25, "max": 32, "period": "HOUR", …}`.
- **A single figure:** "$30/hr" → `min = max = 30`.
- **"Up to $40/hr"** → `min = null, max = 40`. **"Starting at $25/hr"** → `min = 25, max = null`.
- **`period`:**
  - "/hr", "hourly", "per hour" → `HOUR`.
  - "/yr", "annual", "salary", and annual-looking figures with no unit, like "$80,000–$95,000" → `YEAR`.
  - Monthly, weekly or per-program stipends → `UNKNOWN`, with the amounts as written. Don't convert.
- **Several ranges** (by location or level): the lowest min and the highest max, if they share
  a period. If the periods differ, use the first range listed.
- **`currency`** is an ISO 4217 code. Use what's stated, or infer `$` from the location:
  a US location → `USD`, Canada → `CAD`. If `$` is ambiguous, use `USD` and set `unsure`.
- **Not pay:** relocation, housing stipends, signing bonuses, equity and benefits. A posting
  that mentions only these has `pay = null`.
- "Competitive pay" or "paid internship" with no figure: `null`.

---

## `skills`

The named technical tools a candidate is asked to know: programming languages, frameworks,
libraries, databases, platforms and tools. A set.

- Include both required and preferred skills.
- Use each skill's standard spelling, as its maintainers write it: `Python`, `JavaScript`,
  `TypeScript`, `C++`, `C#`, `PostgreSQL`, `AWS`, `PyTorch`, `scikit-learn`, `Kubernetes`, `Git`.
- Split combined mentions: "C/C++" → `["C", "C++"]`. "HTML/CSS" → `["HTML", "CSS"]`.
- Merge aliases: "Postgres" → `PostgreSQL`, "JS" → `JavaScript`, "golang" → `Go`,
  "k8s" → `Kubernetes`.
- **Exclude:**
  - Broad areas like "machine learning", "data structures", "distributed systems" or "statistics".
  - Soft skills.
  - Degree fields.
  - Vague mentions like "a modern programming language" or "cloud platforms".
- A category with named examples counts the examples: "a scripting language such as Python or
  Bash" → `["Python", "Bash"]`.
- Tools named only in the company description ("we build on AWS") count only if the posting
  asks the candidate to use them.
- Excel, Figma and similar tools count if they're named as something the candidate should know.

---

## Worked examples

| Posting text | Field | Label |
| --- | --- | --- |
| "Applications are reviewed on a rolling basis." | `deadline_type`, `deadline` | `ROLLING`, `null` |
| "Rolling review; the posting closes Dec 5, 2026." | `deadline_type`, `deadline` | `FIXED`, `2026-12-05` |
| "Must be a U.S. person as defined by ITAR." | `citizenship` | `US_PERSON` |
| "Candidates must be eligible to work in the U.S." | `citizenship` | `WORK_AUTHORIZED` |
| "We will not sponsor visas for this role." | `citizenship` | `NO_SPONSORSHIP` |
| "Ability to obtain a Secret clearance." | `clearance`, `citizenship` | `ABLE_TO_OBTAIN`, `NONE_MENTIONED` |
| "$25–$32/hr" | `pay` | `{"min": 25, "max": 32, "period": "HOUR", "currency": "USD"}` |
| "$80,000/yr" | `pay` | `{"min": 80000, "max": 80000, "period": "YEAR", "currency": "USD"}` |
| "$6,000 monthly stipend" | `pay` | `{"min": 6000, "max": 6000, "period": "UNKNOWN", "currency": "USD"}` |
| "NYC or SF (hybrid, 3 days in office)" | `location`, `work_mode` | `New York, NY; San Francisco, CA`, `HYBRID` |
| "Pursuing a BS or MS in CS" | `degree_levels` | `["BACHELOR", "MASTER"]` |
| "Experience with C/C++ and Postgres" | `skills` | `["C", "C++", "PostgreSQL"]` |

---

## Decisions log

Add a line whenever you decide a case this guide doesn't cover. If a decision changes an
earlier rule, bump the version at the top and relabel the affected postings.

| Date | Field | Case | Decision |
| --- | --- | --- | --- |
| 2026-11-14 | — | Guide created | Version 1 |
