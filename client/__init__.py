"""Client for the shortlist-extractor service.

Source of truth: shortlist-extractor/client/. The team repo keeps a copy in
apps/extraction_client/. Edit here, then re-copy.
"""

from .api import ExtractionError, extract, fetch_source
from .models import ExtractionResult, FetchedPosting, FieldValue

__all__ = [
    "ExtractionError",
    "ExtractionResult",
    "FetchedPosting",
    "FieldValue",
    "extract",
    "fetch_source",
]
