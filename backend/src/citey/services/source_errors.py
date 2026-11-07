"""Errors shared by the citation source clients."""


class SourceUnavailable(Exception):
    """A citation source could not answer (rate limit, outage, network error).

    Distinct from "no results": callers must not treat this as an empty list,
    or a bad night at the source silently hides citations.
    """

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail
