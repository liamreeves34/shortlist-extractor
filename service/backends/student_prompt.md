Extract facts from the internship posting inside `<posting>` tags. Reply with one JSON object and nothing else, with exactly these keys:

- `title`, `organization`, `location`: text, or null. Location is "City, ST" in the US and "City, Country" elsewhere; separate several with "; ".
- `start_term`: "Spring|Summer|Fall|Winter YYYY", or null.
- `deadline`: "YYYY-MM-DD" when deadline_type is FIXED, otherwise null.
- `deadline_type`: FIXED, ROLLING or NONE_MENTIONED.
- `degree_levels`: a list of HIGH_SCHOOL, ASSOCIATE, BACHELOR, MASTER, PHD (empty if not stated).
- `citizenship`: US_CITIZEN, US_PERSON, NO_SPONSORSHIP, WORK_AUTHORIZED or NONE_MENTIONED.
- `clearance`: REQUIRED, ABLE_TO_OBTAIN, PREFERRED or NONE_MENTIONED.
- `work_mode`: ONSITE, HYBRID, REMOTE or NONE_MENTIONED.
- `pay`: {"min", "max", "period": HOUR, YEAR or UNKNOWN, "currency"}, or null if no pay is stated.
- `skills`: a list of named tools, languages and technologies (empty if none).
