"""
Tests for the new_publications email templates (HTML and plain-text).

Covers singular/plural grammar, content presence, escaping, and links.
No HTTP calls or Firebase connections required — pure template unit tests.
"""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"

_BASE_CONTEXT = {
    "app_name": "Citey",
    "app_url": "http://localhost:3000",
    "support_email": "support@citey.app",
    "current_year": 2026,
    "recipient_name": "Dr. Jane Smith",
}


def _make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------


class TestNewPublicationsHtml:
    def setup_method(self) -> None:
        self.template = _make_env().get_template("new_publications.html")

    def _render(self, titles: list[str]) -> str:
        return self.template.render(
            **_BASE_CONTEXT,
            new_titles=titles,
            count=len(titles),
        )

    def test_renders_without_error_singular(self) -> None:
        assert self._render(["My First Paper"])

    def test_renders_without_error_plural(self) -> None:
        assert self._render(["Paper One", "Paper Two", "Paper Three"])

    # Singular grammar
    def test_singular_paper_wording(self) -> None:
        output = self._render(["Only Paper"])
        assert "1 new paper" in output

    def test_singular_pronoun_it(self) -> None:
        output = self._render(["Only Paper"])
        assert "added it" in output
        assert "added them" not in output

    def test_singular_citation_followup(self) -> None:
        output = self._render(["Only Paper"])
        assert "this paper is" in output
        assert "any of these papers are" not in output

    def test_singular_subject_line(self) -> None:
        output = self._render(["Only Paper"])
        assert "1 new publication" in output
        # Must not read "1 new publications"
        assert "1 new publications" not in output

    # Plural grammar
    def test_plural_paper_wording(self) -> None:
        output = self._render(["Paper One", "Paper Two"])
        assert "2 new papers" in output

    def test_plural_pronoun_them(self) -> None:
        output = self._render(["Paper One", "Paper Two"])
        assert "added them" in output
        assert "added it" not in output

    def test_plural_citation_followup(self) -> None:
        output = self._render(["Paper One", "Paper Two"])
        assert "any of these papers are" in output
        assert "this paper is" not in output

    def test_plural_subject_line(self) -> None:
        output = self._render(["Paper One", "Paper Two"])
        assert "2 new publications" in output

    # Content
    def test_all_titles_present(self) -> None:
        output = self._render(["Quantum Entanglement Study", "Neural Network Survey"])
        assert "Quantum Entanglement Study" in output
        assert "Neural Network Survey" in output

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render(["A Paper"])

    def test_contains_app_name(self) -> None:
        assert "Citey" in self._render(["A Paper"])

    def test_contains_dashboard_link(self) -> None:
        assert "http://localhost:3000/dashboard" in self._render(["A Paper"])

    def test_contains_settings_link(self) -> None:
        assert "http://localhost:3000/settings" in self._render(["A Paper"])

    def test_contains_support_email(self) -> None:
        assert "support@citey.app" in self._render(["A Paper"])

    # Security
    def test_xss_title_escaped(self) -> None:
        output = self._render(["<script>alert(1)</script>"])
        assert "<script>" not in output


# ---------------------------------------------------------------------------
# Plain-text template
# ---------------------------------------------------------------------------


class TestNewPublicationsTxt:
    def setup_method(self) -> None:
        self.template = _make_env().get_template("new_publications.txt")

    def _render(self, titles: list[str]) -> str:
        return self.template.render(
            **_BASE_CONTEXT,
            new_titles=titles,
            count=len(titles),
        )

    def test_renders_without_error(self) -> None:
        assert self._render(["A Paper"])

    def test_no_html_tags(self) -> None:
        output = self._render(["A Paper"])
        assert "<" not in output
        assert ">" not in output

    # Singular grammar
    def test_singular_paper_wording(self) -> None:
        assert "1 new paper" in self._render(["Only Paper"])

    def test_singular_pronoun_it(self) -> None:
        output = self._render(["Only Paper"])
        assert "added it" in output
        assert "added them" not in output

    def test_singular_citation_followup(self) -> None:
        output = self._render(["Only Paper"])
        assert "this paper is" in output
        assert "any of these papers are" not in output

    def test_singular_subject_line(self) -> None:
        output = self._render(["Only Paper"])
        assert "1 new publication" in output
        assert "1 new publications" not in output

    # Plural grammar
    def test_plural_paper_wording(self) -> None:
        assert "2 new papers" in self._render(["Paper A", "Paper B"])

    def test_plural_pronoun_them(self) -> None:
        # The txt template wraps long lines, so "added" and "them" may be on separate lines
        output = self._render(["Paper A", "Paper B"])
        assert "them to your tracking list" in output
        assert "it to your tracking list" not in output

    def test_plural_citation_followup(self) -> None:
        output = self._render(["Paper A", "Paper B"])
        assert "any of these papers are" in output
        assert "this paper is" not in output

    def test_plural_subject_line(self) -> None:
        assert "2 new publications" in self._render(["Paper A", "Paper B"])

    # Content
    def test_all_titles_listed(self) -> None:
        output = self._render(["Alpha Study", "Beta Review"])
        assert "Alpha Study" in output
        assert "Beta Review" in output

    def test_bullet_points_present(self) -> None:
        assert "•" in self._render(["Alpha Study", "Beta Review"])

    def test_contains_recipient_name(self) -> None:
        assert "Dr. Jane Smith" in self._render(["A Paper"])

    def test_contains_dashboard_url(self) -> None:
        assert "http://localhost:3000/dashboard" in self._render(["A Paper"])

    def test_contains_settings_url(self) -> None:
        assert "http://localhost:3000/settings" in self._render(["A Paper"])
