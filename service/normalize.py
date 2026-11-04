import hashlib
import html
import re
import codecs
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

def unicode_to_text(text: str) -> str:
    text = codecs.decode(text, "unicode_escape") #precursor step for lever lists
    text = html_to_text(text)
    return text

def content_hash(text: str) -> str:
    text = "".join(text.strip().split())  # remove all of the whitespace
    return (
        "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    )  # return a hashed version of the string.
