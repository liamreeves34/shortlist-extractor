import hashlib
import html
import re

from bs4 import BeautifulSoup


# #this is primarily for greenhouse because
def html_to_text(text: str) -> str:  # removes all the html aspects from a description
    text = html.unescape(text)  # turn all the weird symbols into actual HTML tags

    inline_tags = [
        "a",
        "span",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "small",
        "sub",
        "sup",
        "code",
        "mark",
        "abbr",
        "font",
        "label",
        "time",
    ]
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all(True):  # loop through all the tags
        if tag.name not in inline_tags:  # if the tag isn't an inline tag,
            tag = tag.insert_before("\n")  # prepend a newline
    text = soup.get_text()  # remove the tags, but puts whitespaces in
    text = text.replace("\xa0", " ")  # replace non-breaking spaces with regular spaces
    text = "\n".join(
        lines.strip() for lines in text.splitlines()
    )  # remove any leading or trainling whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text)  # remove significant newline additions
    return text.strip()  # further remove any artifact whitespace


UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def unicode_to_text(text: str) -> str:
    # Lever's list content can hold literal \uXXXX escapes, so decode only those.
    # codecs.decode(text, "unicode_escape") also re-read every non-ASCII character as
    # Latin-1 bytes, which garbled "We’re" into "Weâ\x80\x99re" in 178 stored postings.
    text = UNICODE_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), text)
    return html_to_text(text)


def content_hash(text: str) -> str:
    text = "".join(text.strip().split())  # remove all of the whitespace
    return (
        "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    )  # return a hashed version of the string.


def render_posting(posting: dict) -> str:
    """A stored posting as every backend sees it: the job board's header, then the body.

    The connectors keep the title, organization and location apart from the body text, and
    the body usually doesn't repeat them. label_gold.py shows people the same three lines,
    so the teacher, the eval harness and the student must see them too:

        Software Engineering Intern
        Organization: Acme Robotics
        Location: Austin, TX

        <body>
    """
    lines = [posting["title"], f"Organization: {posting['organization']}"]
    if posting.get("location_raw"):
        lines.append(f"Location: {posting['location_raw']}")
    return "\n".join(lines) + "\n\n" + posting["text"]
