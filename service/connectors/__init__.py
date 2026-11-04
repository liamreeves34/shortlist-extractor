from service.connectors import greenhouse, lever
from service.schemas import SourcePosting

def fetch(provider: str, token: str, *, user_agent: str) -> [SourcePosting]:
    