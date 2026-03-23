"""
Tests for Jinja2 email template rendering.

Covers both the digest templates (active) and the legacy citation templates.
No HTTP calls or Firebase connections required — pure template unit tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import Notification

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


def _make_digest_group(
    notifications: list[Notification],
    cited_title: str = "The Original Paper",
    cited_doi: str = "10.1038/orig",
) -> dict:
    return {
        "cited_work_title": cited_title,
        "cited_work_doi": cited_doi,
        "citations": notifications,
    }


# ---------------------------------------------------------------------------
# Digest HTML template (active)
# ---------------------------------------------------------------------------


class TestDigestHtml:
    def setup_method(self) -> None:
        self.env = _make_env()
        self.template = self.env.get_template("digest.html")

    def _render(
        self,
        groups: list[dict] | None = None,
        total: int | None = None,
    ) -> str:
        notes = groups or [_make_digest_group([_make_notification()])]
        t = total if total is not None else sum(len(g["citations"]) for g in notes)
        return self.template.render(
            **_BASE_CONTEXT,
            recipient_name="Dr. Jane Smith",
            citation_groups=notes,
            total_citations=t,
            total_papers=len(notes),
            digest_date="March 22, 2026",
        )

    def test_renders_without_error(self) -> None:
        assert self._render()

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render()

    def test_contains_app_name(self) -> None:
        assert "Citey" in self._render()

    def test_contains_cited_title(self) -> None:
        groups = [_make_digest_group([_make_notification()], cited_title="My Big Paper")]
        assert "My Big Paper" in self._render(groups)

    def test_contains_citing_title(self) -> None:
        groups = [_make_digest_group([_make_notification(citing_title="Important Citation")])]
        assert "Important Citation" in self._render(groups)

    def test_contains_citing_authors(self) -> None:
        groups = [_make_digest_group([_make_notification(authors=["Grace Hopper"])])]
        assert "Grace Hopper" in self._render(groups)

    def test_contains_doi_link(self) -> None:
        groups = [_make_digest_group([_make_notification(doi="10.9999/test")])]
        assert "10.9999/test" in self._render(groups)

    def test_singular_wording(self) -> None:
        output = self._render()
        assert "1 new citation" in output

    def test_plural_wording(self) -> None:
        notes = [_make_notification(1), _make_notification(2)]
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=2)
        assert "2 new citations" in output

    def test_overflow_link_shown_when_more_than_5(self) -> None:
        notes = [_make_notification(i) for i in range(1, 8)]  # 7 citations
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=7)
        assert "more" in output.lower()
        assert "dashboard" in output.lower()

    def test_no_overflow_link_when_5_or_fewer(self) -> None:
        notes = [_make_notification(i) for i in range(1, 6)]  # exactly 5
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=5)
        # overflow link text should NOT appear
        assert "+0" not in output

    def test_at_most_5_citations_rendered_per_group(self) -> None:
        notes = [_make_notification(i, citing_title=f"Paper {i}") for i in range(1, 9)]
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=8)
        # Papers 6-8 should not appear in the rendered body
        assert "Paper 6" not in output
        assert "Paper 7" not in output
        assert "Paper 8" not in output

    def test_contains_dashboard_link(self) -> None:
        assert "http://localhost:3000/dashboard" in self._render()

    def test_contains_settings_link(self) -> None:
        assert "http://localhost:3000/settings" in self._render()

    def test_contains_support_email(self) -> None:
        assert "support@citey.app" in self._render()

    def test_multiple_groups_all_present(self) -> None:
        groups = [
            _make_digest_group(
                [_make_notification(1, citing_title="Alpha Citation")],
                cited_title="Paper A",
            ),
            _make_digest_group(
                [_make_notification(2, citing_title="Beta Citation")],
                cited_title="Paper B",
            ),
        ]
        output = self._render(groups, total=2)
        assert "Alpha Citation" in output
        assert "Beta Citation" in output
        assert "Paper A" in output
        assert "Paper B" in output

    def test_no_script_tags(self) -> None:
        """Autoescape should prevent raw <script> injection."""
        dangerous = _make_digest_group(
            [_make_notification(citing_title="<script>alert(1)</script>")]
        )
        output = self._render([dangerous])
        assert "<script>" not in output

    def test_cited_doi_link_present(self) -> None:
        groups = [_make_digest_group([_make_notification()], cited_doi="10.1038/orig")]
        output = self._render(groups)
        assert "10.1038/orig" in output


# ---------------------------------------------------------------------------
# Digest plain-text template (active)
# ---------------------------------------------------------------------------


class TestDigestTxt:
    def setup_method(self) -> None:
        self.env = _make_env()
        self.template = self.env.get_template("digest.txt")

    def _render(
        self,
        groups: list[dict] | None = None,
        total: int | None = None,
    ) -> str:
        notes = groups or [_make_digest_group([_make_notification()])]
        t = total if total is not None else sum(len(g["citations"]) for g in notes)
        return self.template.render(
            **_BASE_CONTEXT,
            recipient_name="Dr. Jane Smith",
            citation_groups=notes,
            total_citations=t,
            total_papers=len(notes),
            digest_date="March 22, 2026",
        )

    def test_renders_without_error(self) -> None:
        assert self._render()

    def test_no_html_tags(self) -> None:
        output = self._render()
        assert "<" not in output
        assert ">" not in output

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render()

    def test_contains_app_name(self) -> None:
        assert "Citey" in self._render()

    def test_contains_citing_title(self) -> None:
        groups = [_make_digest_group([_make_notification(citing_title="TXT Citation")])]
        assert "TXT Citation" in self._render(groups)

    def test_contains_cited_title(self) -> None:
        groups = [_make_digest_group([_make_notification()], cited_title="My Cited Paper")]
        assert "My Cited Paper" in self._render(groups)

    def test_overflow_text_shown(self) -> None:
        notes = [_make_notification(i) for i in range(1, 9)]
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=8)
        assert "more" in output.lower()

    def test_at_most_5_citations_per_group(self) -> None:
        notes = [_make_notification(i, citing_title=f"TxtPaper{i}") for i in range(1, 9)]
        groups = [_make_digest_group(notes)]
        output = self._render(groups, total=8)
        assert "TxtPaper6" not in output
        assert "TxtPaper7" not in output

    def test_contains_doi_url(self) -> None:
        groups = [_make_digest_group([_make_notification(doi="10.5555/plain")])]
        assert "10.5555/plain" in self._render(groups)

    def test_contains_dashboard_url(self) -> None:
        assert "http://localhost:3000/dashboard" in self._render()

    def test_contains_settings_url(self) -> None:
        assert "http://localhost:3000/settings" in self._render()

    def test_singular_wording(self) -> None:
        output = self._render()
        assert "1 New Citation" in output or "1 new citation" in output.lower()

    def test_plural_wording(self) -> None:
        notes = [_make_notification(1), _make_notification(2)]
        output = self._render([_make_digest_group(notes)], total=2)
        assert "2 New Citations" in output or "2 new citations" in output.lower()


# ---------------------------------------------------------------------------
# Legacy citation HTML template (kept for regression coverage)
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
        assert self._render([_make_notification()])

    def test_contains_app_name(self) -> None:
        assert "Citey" in self._render([_make_notification()])

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render([_make_notification()])

    def test_contains_cited_title(self) -> None:
        assert "My Great Paper" in self._render(
            [_make_notification(cited_title="My Great Paper")]
        )

    def test_contains_citing_title(self) -> None:
        assert "A Brilliant Citation" in self._render(
            [_make_notification(citing_title="A Brilliant Citation")]
        )

    def test_contains_authors(self) -> None:
        output = self._render(
            [_make_notification(authors=["Alice Researcher", "Bob Scientist"])]
        )
        assert "Alice Researcher" in output
        assert "Bob Scientist" in output

    def test_contains_year(self) -> None:
        assert "2024" in self._render([_make_notification(year=2024)])

    def test_contains_doi_link(self) -> None:
        assert "10.9999/test" in self._render([_make_notification(doi="10.9999/test")])

    def test_multiple_notifications_all_present(self) -> None:
        output = self._render([
            _make_notification(1, citing_title="Paper Alpha"),
            _make_notification(2, citing_title="Paper Beta"),
        ])
        assert "Paper Alpha" in output
        assert "Paper Beta" in output

    def test_singular_wording_for_one_notification(self) -> None:
        output = self._render([_make_notification()])
        assert "1 new citation" in output

    def test_plural_wording_for_multiple_notifications(self) -> None:
        output = self._render([_make_notification(1), _make_notification(2)])
        assert "2 new citations" in output


# ---------------------------------------------------------------------------
# Legacy citation plain-text template
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
        assert self._render([_make_notification()])

    def test_no_html_tags_in_plain_text(self) -> None:
        output = self._render([_make_notification()])
        assert "<" not in output
        assert ">" not in output

    def test_contains_app_name(self) -> None:
        assert "Citey" in self._render([_make_notification()])

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render([_make_notification()])

    def test_contains_cited_title(self) -> None:
        assert "My Great Paper" in self._render(
            [_make_notification(cited_title="My Great Paper")]
        )

    def test_contains_citing_title(self) -> None:
        assert "A Text Citation" in self._render(
            [_make_notification(citing_title="A Text Citation")]
        )

    def test_contains_authors(self) -> None:
        output = self._render(
            [_make_notification(authors=["Charlie Darwin", "Grace Hopper"])]
        )
        assert "Charlie Darwin" in output
        assert "Grace Hopper" in output

    def test_contains_doi_url(self) -> None:
        assert "10.5555/plaintext" in self._render(
            [_make_notification(doi="10.5555/plaintext")]
        )

    def test_contains_settings_link(self) -> None:
        assert "http://localhost:3000/settings" in self._render([_make_notification()])

    def test_multiple_notifications(self) -> None:
        output = self._render([
            _make_notification(1, citing_title="Text Paper One"),
            _make_notification(2, citing_title="Text Paper Two"),
        ])
        assert "Text Paper One" in output
        assert "Text Paper Two" in output
