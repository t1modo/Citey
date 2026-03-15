"""
Tests for Jinja2 email template rendering.

No HTTP calls or Firebase connections required — pure template unit tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import Notification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"


def _make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _make_notification(
    n: int = 1,
    *,
    cited_title: str = "The Original Paper",
    citing_title: str = "A Citing Paper",
    doi: str = "10.1234/citing",
    year: int = 2023,
    authors: list[str] | None = None,
    affiliations: list[str] | None = None,
) -> Notification:
    return Notification(
        id=f"cited_work__{n}",
        cited_work_id="10.1038__orig",
        cited_work_title=cited_title,
        citing_work_id=f"https://openalex.org/W{n:010d}",
        citing_work_title=citing_title,
        citing_work_doi=doi,
        citing_work_url=f"https://doi.org/{doi}",
        citing_authors=authors or ["Alice Researcher", "Bob Scientist"],
        citing_affiliations=affiliations or ["MIT", "Harvard"],
        citing_year=year,
        seen=False,
        created_at=datetime.now(tz=timezone.utc),
    )


_BASE_CONTEXT = {
    "app_name": "Citey",
    "app_url": "http://localhost:3000",
    "support_email": "support@citey.app",
    "current_year": 2026,
}


# ---------------------------------------------------------------------------
# HTML template tests
# ---------------------------------------------------------------------------


class TestCitationHtml:
    def setup_method(self) -> None:
        self.env = _make_env()
        self.template = self.env.get_template("citation.html")

    def _render(self, notifications: list[Notification]) -> str:
        return self.template.render(
            **_BASE_CONTEXT,
            recipient_name="Dr. Jane Smith",
            notifications=notifications,
            notification_count=len(notifications),
        )

    def test_renders_without_error(self) -> None:
        output = self._render([_make_notification()])
        assert output

    def test_contains_app_name(self) -> None:
        output = self._render([_make_notification()])
        assert "Citey" in output

    def test_contains_recipient_name(self) -> None:
        output = self._render([_make_notification()])
        assert "Dr. Jane Smith" in output

    def test_contains_cited_title(self) -> None:
        output = self._render([_make_notification(cited_title="My Great Paper")])
        assert "My Great Paper" in output

    def test_contains_citing_title(self) -> None:
        output = self._render([_make_notification(citing_title="A Brilliant Citation")])
        assert "A Brilliant Citation" in output

    def test_contains_authors(self) -> None:
        output = self._render(
            [_make_notification(authors=["Alice Researcher", "Bob Scientist"])]
        )
        assert "Alice Researcher" in output
        assert "Bob Scientist" in output

    def test_contains_affiliations(self) -> None:
        output = self._render(
            [_make_notification(affiliations=["Stanford University"])]
        )
        assert "Stanford University" in output

    def test_contains_year(self) -> None:
        output = self._render([_make_notification(year=2024)])
        assert "2024" in output

    def test_contains_doi_link(self) -> None:
        output = self._render([_make_notification(doi="10.9999/test")])
        assert "10.9999/test" in output

    def test_contains_app_url(self) -> None:
        output = self._render([_make_notification()])
        assert "http://localhost:3000" in output

    def test_contains_support_email(self) -> None:
        output = self._render([_make_notification()])
        assert "support@citey.app" in output

    def test_multiple_notifications_all_present(self) -> None:
        notes = [
            _make_notification(1, citing_title="Paper Alpha"),
            _make_notification(2, citing_title="Paper Beta"),
        ]
        output = self._render(notes)
        assert "Paper Alpha" in output
        assert "Paper Beta" in output

    def test_singular_wording_for_one_notification(self) -> None:
        output = self._render([_make_notification()])
        # Should say "1 new citation" not "1 new citations"
        assert "1 new citation" in output
        assert "citations" not in output.split("1 new citation")[1][:10]

    def test_plural_wording_for_multiple_notifications(self) -> None:
        notes = [_make_notification(1), _make_notification(2)]
        output = self._render(notes)
        assert "2 new citations" in output

    def test_notification_count_in_title(self) -> None:
        output = self._render([_make_notification()])
        assert "1" in output

    def test_no_affiliations_section_when_empty(self) -> None:
        output = self._render([_make_notification(affiliations=[])])
        # "Affiliations:" label should not appear when list is empty
        assert "Affiliations:" not in output


# ---------------------------------------------------------------------------
# Plain text template tests
# ---------------------------------------------------------------------------


class TestCitationTxt:
    def setup_method(self) -> None:
        self.env = _make_env()
        self.template = self.env.get_template("citation.txt")

    def _render(self, notifications: list[Notification]) -> str:
        return self.template.render(
            **_BASE_CONTEXT,
            recipient_name="Dr. Jane Smith",
            notifications=notifications,
            notification_count=len(notifications),
        )

    def test_renders_without_error(self) -> None:
        output = self._render([_make_notification()])
        assert output

    def test_contains_app_name(self) -> None:
        output = self._render([_make_notification()])
        assert "Citey" in output

    def test_contains_recipient_name(self) -> None:
        output = self._render([_make_notification()])
        assert "Dr. Jane Smith" in output

    def test_contains_cited_title(self) -> None:
        output = self._render([_make_notification(cited_title="My Great Paper")])
        assert "My Great Paper" in output

    def test_contains_citing_title(self) -> None:
        output = self._render([_make_notification(citing_title="A Text Citation")])
        assert "A Text Citation" in output

    def test_contains_authors(self) -> None:
        output = self._render(
            [_make_notification(authors=["Charlie Darwin", "Grace Hopper"])]
        )
        assert "Charlie Darwin" in output
        assert "Grace Hopper" in output

    def test_contains_year(self) -> None:
        output = self._render([_make_notification(year=2025)])
        assert "2025" in output

    def test_contains_doi_url(self) -> None:
        output = self._render([_make_notification(doi="10.5555/plaintext")])
        assert "10.5555/plaintext" in output

    def test_contains_app_url_settings_link(self) -> None:
        output = self._render([_make_notification()])
        assert "http://localhost:3000/settings" in output

    def test_contains_support_email(self) -> None:
        output = self._render([_make_notification()])
        assert "support@citey.app" in output

    def test_multiple_notifications(self) -> None:
        notes = [
            _make_notification(1, citing_title="Text Paper One"),
            _make_notification(2, citing_title="Text Paper Two"),
        ]
        output = self._render(notes)
        assert "Text Paper One" in output
        assert "Text Paper Two" in output

    def test_no_html_tags_in_plain_text(self) -> None:
        output = self._render([_make_notification()])
        assert "<" not in output
        assert ">" not in output
