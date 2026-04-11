"""
Tests for the fuzzy name-matching helpers in app.routers.works.

These functions are the backbone of the author-presence check — the mechanism
that warns a user when the paper they are adding does not appear to be
authored by their linked profile.  They are also exercised every time a user
tries to add a paper via arXiv or DOI while an author is linked.
"""

from app.routers.works import _author_in_paper, _name_tokens, _names_match


# ---------------------------------------------------------------------------
# _name_tokens
# ---------------------------------------------------------------------------


class TestNameTokens:
    def test_simple_name(self) -> None:
        assert _name_tokens("Jane Smith") == ["jane", "smith"]

    def test_lowercases_all(self) -> None:
        assert _name_tokens("JOHN DOE") == ["john", "doe"]

    def test_strips_dots(self) -> None:
        # "J. Smith" → ["j", "smith"]
        assert _name_tokens("J. Smith") == ["j", "smith"]

    def test_strips_hyphens(self) -> None:
        # Hyphenated names become two separate tokens
        assert _name_tokens("Anne-Marie Dupont") == ["anne", "marie", "dupont"]

    def test_empty_string_returns_empty(self) -> None:
        assert _name_tokens("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert _name_tokens("   ") == []

    def test_three_part_name(self) -> None:
        assert _name_tokens("Mary Jo Walsh") == ["mary", "jo", "walsh"]


# ---------------------------------------------------------------------------
# _names_match
# ---------------------------------------------------------------------------


class TestNamesMatch:
    def test_exact_match(self) -> None:
        assert _names_match("Jane Smith", "Jane Smith")

    def test_case_insensitive(self) -> None:
        assert _names_match("jane smith", "JANE SMITH")

    # Middle name omission
    def test_middle_name_omitted_in_shorter(self) -> None:
        # "Jane Smith" should match "Jane Marie Smith"
        assert _names_match("Jane Smith", "Jane Marie Smith")

    def test_middle_name_omitted_in_longer(self) -> None:
        assert _names_match("Jane Marie Smith", "Jane Smith")

    # First-name initials
    def test_initial_matches_full_first_name(self) -> None:
        # "J. Smith" should match "Jane Smith"
        assert _names_match("J. Smith", "Jane Smith")

    def test_full_first_name_matches_initial(self) -> None:
        assert _names_match("Jane Smith", "J. Smith")

    def test_initial_with_middle_name(self) -> None:
        # "T. K. Do" should match "Timothy Khang Do"
        assert _names_match("T. K. Do", "Timothy Khang Do")

    # Last-name mismatches
    def test_last_name_mismatch_fails(self) -> None:
        assert not _names_match("Jane Smith", "Jane Jones")

    def test_completely_different_names_fail(self) -> None:
        assert not _names_match("Alice Brown", "Bob White")

    # Edge cases
    def test_family_name_only_matches_itself(self) -> None:
        assert _names_match("Smith", "Smith")

    def test_family_name_only_mismatch(self) -> None:
        assert not _names_match("Smith", "Jones")

    def test_empty_first_arg_returns_false(self) -> None:
        assert not _names_match("", "Jane Smith")

    def test_empty_second_arg_returns_false(self) -> None:
        assert not _names_match("Jane Smith", "")

    def test_reversed_order_fails(self) -> None:
        # "Smith Jane" must NOT match "Jane Smith" — last token is treated as family name
        assert not _names_match("Smith Jane", "Jane Smith")

    def test_hyphenated_last_name_normalized(self) -> None:
        # Hyphens are stripped, so "Garcia-Lopez" and "Garcia Lopez" tokenise identically
        assert _names_match("Maria Garcia-Lopez", "Maria Garcia Lopez")

    def test_arxiv_style_author(self) -> None:
        # Typical OpenAlex display name vs. how the user typed their name
        assert _names_match("T. Nguyen", "Timothy Nguyen")

    def test_longer_given_name_vs_initial(self) -> None:
        assert _names_match("Timothy Nguyen", "T. Nguyen")


# ---------------------------------------------------------------------------
# _author_in_paper
# ---------------------------------------------------------------------------


class TestAuthorInPaper:
    def test_exact_author_found(self) -> None:
        assert _author_in_paper(["Jane Smith", "Bob Jones"], ["Jane Smith"])

    def test_initial_match_found(self) -> None:
        assert _author_in_paper(["Timothy Nguyen", "Alice Brown"], ["T. Nguyen"])

    def test_no_match_returns_false(self) -> None:
        assert not _author_in_paper(["Alice Brown", "Charlie Davis"], ["Jane Smith"])

    def test_alias_list_one_matches(self) -> None:
        # User supplies both married name and maiden name as aliases
        assert _author_in_paper(["Jane Doe"], ["Jane Smith", "Jane Doe"])

    def test_alias_list_none_match(self) -> None:
        assert not _author_in_paper(["Alice Brown"], ["Jane Smith", "Jane Doe"])

    def test_empty_paper_authors_returns_false(self) -> None:
        assert not _author_in_paper([], ["Jane Smith"])

    def test_empty_names_to_check_returns_false(self) -> None:
        assert not _author_in_paper(["Jane Smith"], [])

    def test_match_among_many_paper_authors(self) -> None:
        authors = ["Alice Brown", "Bob White", "Jane Smith", "Charlie Davis"]
        assert _author_in_paper(authors, ["Jane Smith"])

    def test_middle_name_in_paper_matches_without_middle(self) -> None:
        # OpenAlex often stores full middle names; user may omit theirs
        assert _author_in_paper(["Jane Marie Smith"], ["Jane Smith"])
