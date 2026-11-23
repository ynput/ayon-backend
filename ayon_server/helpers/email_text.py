"""The plain text version of an HTML email.

Mail clients show it when they do not render HTML, and spam filters score an
email without it lower. It is derived from the HTML, so every template gets one.
"""

import re
from html.parser import HTMLParser

# elements that start and end a line of text
BLOCK_TAGS = {
    "blockquote",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ol",
    "p",
    "table",
    "ul",
}
# elements that end a line, one right under the other
LINE_TAGS = {"li", "tr"}
# elements whose content is not text the reader sees
SKIP_TAGS = {"head", "script", "style", "title"}
# elements without an end tag
VOID_TAGS = {"area", "base", "br", "col", "hr", "img", "input", "link", "meta", "wbr"}


def _hidden(attrs: dict[str, str | None]) -> bool:
    style = (attrs.get("style") or "").replace(" ", "").lower()
    return "display:none" in style or "hidden" in attrs


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.skip_depth: int | None = None
        self.links: list[tuple[str | None, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_TAGS:
            if tag == "br" and self.skip_depth is None:
                self.parts.append("\n")
            return
        self.stack.append(tag)
        if self.skip_depth is not None:
            return
        if tag in SKIP_TAGS or _hidden(dict(attrs)):
            self.skip_depth = len(self.stack)
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")
        elif tag == "a":
            self.links.append((dict(attrs).get("href"), len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.stack:
            return
        # close what was left open inside, as a browser does
        while self.stack:
            closed = self.stack.pop()
            depth = len(self.stack) + 1
            if self.skip_depth is not None:
                if depth == self.skip_depth:
                    self.skip_depth = None
                if closed == tag:
                    return
                continue
            self._close(closed)
            if closed == tag:
                return

    def _close(self, tag: str) -> None:
        if tag in BLOCK_TAGS or tag in LINE_TAGS:
            self.parts.append("\n")
        elif tag == "a" and self.links:
            href, start = self.links.pop()
            label = "".join(self.parts[start:]).strip()
            if href and href.startswith(("http://", "https://")) and href != label:
                self.parts.append(f" ({href})" if label else href)

    def handle_data(self, data: str) -> None:
        if self.skip_depth is None:
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    """The text of an HTML email: one line per block, links as `label (url)`."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in "".join(parser.parts).splitlines()
    ]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
