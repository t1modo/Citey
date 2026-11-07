"""Tests for app.services.text_clean, using markup seen in real source data."""

import pytest

from citey.services.text_clean import clean_name, clean_names, clean_text


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Crossref / JATS
        ("<i>Drosophila</i> <scp>dna</scp> repair", "Drosophila dna repair"),
        ("Splitting H<sub>2</sub>O with light", "Splitting H₂O with light"),
        ("Effects of Ca<sup>2+</sup> signalling", "Effects of Ca²⁺ signalling"),
        ("<jats:title>Deep   learning\n for proteins</jats:title>", "Deep learning for proteins"),
        ('<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:mi>x</mml:mi></mml:math> bounds', "x bounds"),
        # Entities, including double encoding
        ("Q&amp;A systems", "Q&A systems"),
        ("Texas A&amp;amp;M", "Texas A&M"),
        ("Br&#xF6;nsted acids", "Brönsted acids"),
        ("Sch&ouml;dinger&#39;s cat", "Schödinger's cat"),
        # ADS / INSPIRE LaTeX
        (r"Measurement of the $\alpha_s$ coupling", "Measurement of the αₛ coupling"),
        (r"$H_2O$ masers in $10^{6}$ M$_\odot$ haloes", "H₂O masers in 10⁶ M⊙ haloes"),
        (r"A $\sim 5\sigma$ excess", "A ∼ 5σ excess"),
        (r"Search for $\mathrm{B}^{0}$ decays", "Search for B⁰ decays"),
        (r"Schr{\"o}dinger equation", "Schrödinger equation"),
        (r"G\"odel and Erd\H{o}s", "Gödel and Erdős"),
        (r"The {B}ayesian {DNA} model", "The Bayesian DNA model"),
        (r"50\% faster", "50% faster"),
        # Plain text is left alone
        ("A survey of graph neural networks", "A survey of graph neural networks"),
        ("Costs < benefits > zero", "Costs < benefits > zero"),
        ("Price: $5 and up", "Price: $5 and up"),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_clean_text_normalizes_to_nfc() -> None:
    decomposed = "Müller"  # u + combining diaeresis
    assert clean_text(decomposed) == "Müller"
    assert len(clean_text(decomposed)) == len("Müller")


def test_clean_text_is_idempotent() -> None:
    raw = r"<i>E. coli</i> &amp; $\beta$-lactams"
    once = clean_text(raw)
    assert clean_text(once) == once == "E. coli & β-lactams"


@pytest.mark.parametrize("value", [None, ""])
def test_clean_text_passes_empty_through(value) -> None:
    assert clean_text(value) == value


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Jane Smith 0001", "Jane Smith"),
        ("Wei Wang 0042", "Wei Wang"),
        ("José  García", "José García"),
        ("ATLAS Collaboration", "ATLAS Collaboration"),
        ("Malcolm X", "Malcolm X"),
    ],
)
def test_clean_name(raw: str, expected: str) -> None:
    assert clean_name(raw) == expected


def test_clean_names_keeps_order_and_drops_empty() -> None:
    assert clean_names(["Zoë Ng 0003", "  ", "Ada Lovelace", "<b></b>"]) == ["Zoë Ng", "Ada Lovelace"]
