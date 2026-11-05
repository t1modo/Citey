"""
Clean bibliographic text from upstream sources before it is stored or shown.

Sources disagree on how they encode titles and names:

* Crossref and PubMed embed JATS/HTML markup (``<i>Drosophila</i>``,
  ``H<sub>2</sub>O``, ``<scp>dna</scp>``) and HTML entities (``Q&amp;A``).
* NASA ADS and INSPIRE-HEP use LaTeX (``$\\alpha$``, ``$H_2O$``, ``{\\"o}``).
* DBLP appends a four digit disambiguation number to names (``Jane Smith 0001``).

React and Jinja both escape output, so any markup left in the data is shown
to the reader literally. Everything here is pure and safe to run more than
once on the same string.
"""

from __future__ import annotations

import html
import re
import unicodedata

_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUP = str.maketrans("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ")
_SUB_CHARS = set("0123456789+-=()aehijklmnoprstuvx")
_SUP_CHARS = set("0123456789+-=()in")

_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_TEX_SYMBOLS = {
    "times": "×", "pm": "±", "mp": "∓", "cdot": "·", "sim": "∼", "approx": "≈",
    "simeq": "≃", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "infty": "∞", "odot": "⊙",
    "sun": "☉", "circ": "°", "prime": "′", "ell": "ℓ", "hbar": "ℏ", "partial": "∂",
    "nabla": "∇", "sqrt": "√", "langle": "⟨", "rangle": "⟩", "%": "%", "&": "&",
    "_": "_", "#": "#", "$": "$",
}
_TEX_ACCENTS = {
    '"': "̈", "'": "́", "`": "̀", "^": "̂", "~": "̃",
    "=": "̄", ".": "̇", "c": "̧", "v": "̌", "u": "̆",
    "H": "̋", "k": "̨", "r": "̊",
}
_TEX_LETTERS = {"ss": "ß", "o": "ø", "O": "Ø", "aa": "å", "AA": "Å", "ae": "æ",
                "AE": "Æ", "oe": "œ", "OE": "Œ", "l": "ł", "L": "Ł", "i": "ı"}

_TAG = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
_SUB_TAG = re.compile(r"<(?:sub|inf)>(.*?)</(?:sub|inf)>", re.IGNORECASE | re.DOTALL)
_SUP_TAG = re.compile(r"<sup>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_MATH_SPAN = re.compile(r"\$([^$]+)\$")
# {\"o}, \"{o}, \"o, \c{c}, \'{\i}
_ACCENT = re.compile(r"\{?\\([\"'`^~=.]|[cvuHkr](?=[{\s]))\s*\{?\\?([A-Za-z])\}?\}?")
_LETTER = re.compile(r"\{?\\(ss|aa|AA|ae|AE|oe|OE|o|O|l|L|i)(?![A-Za-z])\}?")
_DBLP_SUFFIX = re.compile(r"\s+\d{4}$")
_SPACE = re.compile(r"\s+")


def _script(text: str, chars: set[str], table: dict[int, str]) -> str | None:
    """Convert *text* to sub/superscript characters, or None if it can't be."""
    text = text.strip()
    if text and all(c in chars for c in text):
        return text.translate(table)
    return None


def _replace_sub(match: re.Match[str]) -> str:
    inner = _TAG.sub("", match.group(1))
    return _script(inner, _SUB_CHARS, _SUB) or inner


def _replace_sup(match: re.Match[str]) -> str:
    inner = _TAG.sub("", match.group(1))
    return _script(inner, _SUP_CHARS, _SUP) or inner


def _tex_command(match: re.Match[str]) -> str:
    name = match.group(1)
    if name in _GREEK:
        return _GREEK[name]
    if name in _TEX_SYMBOLS:
        return _TEX_SYMBOLS[name]
    # Font and layout commands (\mathrm, \rm, \textit, \left …) carry no text.
    return ""


def _tex_math(body: str) -> str:
    """Render the inside of a ``$…$`` span as plain Unicode text."""
    body = re.sub(r"\\([A-Za-z]+|[%&_#$])", _tex_command, body)

    def scripted(match: re.Match[str]) -> str:
        marker, group, single = match.group(1), match.group(2), match.group(3)
        inner = group if group is not None else single
        if marker == "_":
            return _script(inner, _SUB_CHARS, _SUB) or inner
        return _script(inner, _SUP_CHARS, _SUP) or inner

    body = re.sub(r"([_^])(?:\{([^{}]*)\}|(\S))", scripted, body)
    body = body.replace("{", "").replace("}", "").replace("~", " ")
    return body


def _tex_accent(match: re.Match[str]) -> str:
    return unicodedata.normalize("NFC", match.group(2) + _TEX_ACCENTS[match.group(1)])


def clean_text(value: str | None) -> str | None:
    """Return *value* as plain, normalized Unicode text.

    Decodes HTML entities, turns ``<sub>``/``<sup>`` and simple LaTeX into
    Unicode, drops any other markup, collapses whitespace and applies NFC.
    ``None`` and empty strings are returned unchanged.
    """
    if not value:
        return value
    text = value
    # Entities can arrive double encoded ("&amp;amp;"); two passes undo that
    # without touching legitimate text.
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded

    if "<" in text:
        text = _SUB_TAG.sub(_replace_sub, text)
        text = _SUP_TAG.sub(_replace_sup, text)
        text = _TAG.sub("", text)

    if "\\" in text or "$" in text:
        if text.count("$") >= 2 and text.count("$") % 2 == 0:
            text = _MATH_SPAN.sub(lambda m: _tex_math(m.group(1)), text)
        text = _ACCENT.sub(_tex_accent, text)
        text = _LETTER.sub(lambda m: _TEX_LETTERS[m.group(1)], text)
        text = re.sub(r"\\([%&_#$])", r"\1", text)

    if "{" in text:
        # Braces that only protected capitalisation in BibTeX ({DNA}, {B}ayesian).
        text = re.sub(r"\{([^{}\\]*)\}", r"\1", text)

    text = _SPACE.sub(" ", text).strip()
    return unicodedata.normalize("NFC", text)


def clean_name(value: str | None) -> str | None:
    """Clean an author name and drop DBLP's numeric disambiguation suffix."""
    text = clean_text(value)
    if not text:
        return text
    return _DBLP_SUFFIX.sub("", text)


def clean_names(values: list[str] | None) -> list[str]:
    """Clean a list of names, keeping order and dropping any that end up empty."""
    out: list[str] = []
    for value in values or []:
        name = clean_name(value)
        if name:
            out.append(name)
    return out
