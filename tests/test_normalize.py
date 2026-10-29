"""Step 2.3: service/normalize.py.

Decision tested here: content_hash ignores whitespace-only differences, so a
board that re-flows its HTML doesn't make every posting look "changed" and
trigger re-extraction. Flip test_whitespace_only_differences_give_the_same_hash
if you decide otherwise.
"""

import hashlib
import re

import pytest

from service.normalize import content_hash, html_to_text


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# ---------- html_to_text ----------


def test_escaped_html_comes_out_readable():
    # Greenhouse escapes its HTML once, so "&" arrives as "&amp;amp;".
    escaped = "&lt;p&gt;Build robots &amp;amp; ship code.&lt;/p&gt;"
    assert html_to_text(escaped) == "Build robots & ship code."


def test_raw_html_works_too():
    text = html_to_text("<p>Hello <strong>world</strong></p>")
    assert " ".join(text.split()) == "Hello world"


@pytest.mark.parametrize(
    "html",
    [
        "&lt;div class=&quot;intro&quot;&gt;&lt;p&gt;Hi&lt;/p&gt;&lt;/div&gt;",
        '<div class="intro"><p>Hi</p><br/><a href="https://example.com">link</a></div>',
    ],
)
def test_no_tags_or_entities_survive(html):
    text = html_to_text(html)
    assert not re.search(r"<[^>]+>", text)
    assert not re.search(r"&[a-z]+;|&#\d+;", text)


def test_entities_are_decoded():
    assert html_to_text("&lt;p&gt;You&#39;ll ship&lt;/p&gt;") == "You'll ship"


def test_non_breaking_spaces_become_plain_spaces():
    text = html_to_text("&lt;p&gt;Pay&amp;nbsp;range&lt;/p&gt;")
    assert text == "Pay range"
    assert "\xa0" not in text


def test_paragraph_breaks_are_kept():
    assert lines(html_to_text("<p>One</p><p>Two</p>")) == ["One", "Two"]


def test_list_items_get_their_own_lines():
    assert lines(html_to_text("<ul><li>Python</li><li>SQL</li></ul>")) == ["Python", "SQL"]


def test_runs_of_blank_lines_are_collapsed():
    text = html_to_text("<p>One</p>\n\n\n\n<br><br><br><p>Two</p>")
    assert "\n\n\n" not in text
    assert lines(text) == ["One", "Two"]


def test_whitespace_only_lines_count_as_blank():
    # Lever's *Plain fields separate paragraphs with "\n \n"; &nbsp;-only divs do the same.
    text = html_to_text("One\n \n \n \nTwo<div>&nbsp;</div><div>&nbsp;</div>Three")
    assert not re.search(r"\n[ \t\xa0]*\n[ \t\xa0]*\n", text)
    assert lines(text) == ["One", "Two", "Three"]


def test_no_leading_or_trailing_whitespace():
    text = html_to_text("\n\n  <p>  Padded  </p>  \n")
    assert text == text.strip()


def test_plain_text_passes_through():
    assert html_to_text("Just text.") == "Just text."


def test_empty_input_gives_empty_text():
    assert html_to_text("") == ""


# ---------- content_hash ----------


def test_hash_format():
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", content_hash("anything"))


def test_hash_is_sha256_of_the_text():
    # Text with no whitespace is already normalized, so it hashes as-is.
    assert content_hash("abc") == "sha256:" + hashlib.sha256(b"abc").hexdigest()


def test_same_text_same_hash():
    assert content_hash("Apply by Nov 15") == content_hash("Apply by Nov 15")


def test_different_text_different_hash():
    assert content_hash("Apply by Nov 15") != content_hash("Apply by Nov 16")


@pytest.mark.parametrize(
    "variant",
    ["Apply  by Nov 15", "  Apply by Nov 15\n", "Apply\tby Nov 15", "Apply\n\n\nby Nov 15"],
)
def test_whitespace_only_differences_give_the_same_hash(variant):
    assert content_hash(variant) == content_hash("Apply by Nov 15")


def test_reformatted_html_gives_the_same_hash():
    tidy = "<p>Apply by Nov 15</p><p>Pay: $30/hr</p>"
    messy = "\n  <p>Apply   by Nov 15</p>\n\n\n  <p>Pay:  $30/hr</p>\n"
    assert content_hash(html_to_text(tidy)) == content_hash(html_to_text(messy))
