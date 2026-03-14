from __future__ import annotations

from typing import Protocol

from cogerlapala.models import JobPosting, SearchParameters


class JobSource(Protocol):
    source_name: str

    async def search(self, params: SearchParameters) -> list[JobPosting]:
        """Return relevant jobs for a given search request."""
