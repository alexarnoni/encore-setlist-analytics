"""Build-time content policy check (spec R5): what a generated page must and must not contain.

Every rule guards the data policy in `docs/context/product.md`: the site is built from
aggregated marts and must never show an individual setlist, a show date, a venue or a
setlist.fm identifier, and every page credits setlist.fm with a followable link.

Rules, per page:
- no forbidden field name (the dbt `assert_no_forbidden_columns_in_analytics` list) anywhere in
  the HTML; `venue`, a plain word that legitimately appears in prose, is checked only as an
  attribute, an id/class or a table header;
- no date more precise than a year, except inside the one `data-build-stamp` element that
  carries the build date and the pipeline run date (R1.4), which must exist and hold exactly
  two ISO dates;
- any link to setlist.fm points at the site root, never at a setlist or a show;
- a followable setlist.fm link (no `nofollow`) and the MusicBrainz CC0 credit are present.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

logger = logging.getLogger(__name__)

# Same names as dbt/tests/assert_no_forbidden_columns_in_analytics.sql.
FORBIDDEN_FIELDS = (
    "setlist_id", "show_date", "venue", "song_name_raw", "show_key", "show_id", "show_index", "setlist_url",
)
STAMP_ATTRIBUTE = "data-build-stamp"

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
)
_DATE_PATTERNS = {
    "ISO date": re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)"),
    "numeric date": re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"),
    "day and month name": re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:de\s+|of\s+)?(?:{_MONTHS})\b", re.I),
    "month name and day or year": re.compile(rf"\b(?:{_MONTHS})\s+(?:de\s+)?\d{{1,4}}\b", re.I),
}
# Attributes that carry readable content or addresses; SVG geometry (`d`, `points`, `transform`, ...)
# is numbers only and is left out so path data can never look like a date.
_CONTENT_ATTRIBUTES = {"href", "title", "alt", "aria-label", "content", "name", "id", "value", "src", "lang",
                       "hreflang", "class"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class PolicyError(Exception):
    """One or more generated pages break the content policy; the build must not ship."""


@dataclass(frozen=True)
class Violation:
    """A single rule broken on a single page."""

    page: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.page}: {self.rule}: {self.detail}"


class _Scan(HTMLParser):
    """Splits a page into what is checked (text and attributes) and the exempt stamp element."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.attributes: list[tuple[str, str, str]] = []  # tag, name, value (outside the stamp)
        self.headers: list[str] = []
        self.links: list[dict[str, str]] = []
        self.stamp_text: list[str] = []
        self.stamp_seen = False
        self._stamp_tag: str | None = None
        self._stamp_depth = 0
        self._skip = 0
        self._th: list[str] | None = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = {k: (v or "") for k, v in attrs}
        if self._stamp_tag is None and STAMP_ATTRIBUTE in attributes:
            self._stamp_tag, self._stamp_depth, self.stamp_seen = tag, 0, True
        in_stamp = self._stamp_tag is not None
        if in_stamp and tag == self._stamp_tag and tag not in _VOID:
            self._stamp_depth += 1
        if in_stamp:
            self.stamp_text.extend(attributes.values())
        else:
            for name, value in attributes.items():
                self.attributes.append((tag, name, value))
            if tag == "a":
                self.links.append(attributes)
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "th":
            self._th = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag == "th" and self._th is not None:
            self.headers.append("".join(self._th).strip())
            self._th = None
        if self._stamp_tag is not None and tag == self._stamp_tag:
            self._stamp_depth -= 1
            if self._stamp_depth <= 0:
                self._stamp_tag = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._stamp_tag is not None:
            self.stamp_text.append(data)
            return
        self.text.append(data)
        if self._th is not None:
            self._th.append(data)


def _link_violations(scan: _Scan, page: str) -> list[Violation]:
    found: list[Violation] = []
    for link in scan.links:
        href = link.get("href", "")
        if re.match(r"https?://(www\.)?setlist\.fm", href, re.I):
            path = re.sub(r"^https?://(www\.)?setlist\.fm", "", href, flags=re.I)
            if path.strip("/") or "?" in path or "#" in path:
                found.append(Violation(page, "setlist.fm link", f"{href} points past the site root"))
    return found


def check_html(html: str, page: str, *, is_page: bool = True) -> list[Violation]:
    """Check one page. `is_page=False` skips the attribution and stamp rules (the root redirect)."""
    scan = _Scan(html)
    found: list[Violation] = []
    outside_stamp = " ".join(scan.text) + " " + " ".join(
        v for _, n, v in scan.attributes if n in _CONTENT_ATTRIBUTES or n.startswith("data-"))

    lowered = html.lower()
    for name in FORBIDDEN_FIELDS:
        if name == "venue":
            continue
        if re.search(rf"\b{name}\b", lowered):
            found.append(Violation(page, "forbidden field name", name))
    identifiers = [w for _, n, _ in scan.attributes for w in re.split(r"[\s_-]+", n)] + [
        w for _, n, v in scan.attributes if n in ("id", "class", "name") for w in re.split(r"[\s_-]+", v)]
    if any(i.lower() == "venue" for i in identifiers) or any(h.lower() == "venue" for h in scan.headers):
        found.append(Violation(page, "forbidden field name", "venue (as an attribute, id, class or table header)"))

    for label, pattern in _DATE_PATTERNS.items():
        match = pattern.search(outside_stamp)
        if match:
            found.append(Violation(page, "date more precise than a year", f"{label}: {match.group(0)!r}"))

    found.extend(_link_violations(scan, page))

    if is_page:
        if not scan.stamp_seen:
            found.append(Violation(page, "build stamp", f"no element with {STAMP_ATTRIBUTE}"))
        elif len(re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", " ".join(scan.stamp_text))) < 2:
            found.append(Violation(page, "build stamp", "does not hold the build date and the run date"))
        setlistfm = [l for l in scan.links if "setlist.fm" in l.get("href", "").lower()]
        if not setlistfm:
            found.append(Violation(page, "attribution", "no link to setlist.fm"))
        for link in setlistfm:
            if "nofollow" in link.get("rel", "").lower():
                found.append(Violation(page, "attribution", "setlist.fm link has nofollow"))
        if not any("musicbrainz.org" in l.get("href", "").lower() for l in scan.links) or "CC0" not in outside_stamp:
            found.append(Violation(page, "attribution", "MusicBrainz credit with CC0 is missing"))
    return found


def check_site(out: Path) -> list[Violation]:
    """Check every generated HTML page under `out`; the root redirect only gets the content rules."""
    found: list[Violation] = []
    for path in sorted(out.rglob("*.html")):
        relative = path.relative_to(out).as_posix()
        found.extend(check_html(path.read_text(encoding="utf8"), relative, is_page=relative != "index.html"))
    return found


def enforce(out: Path) -> None:
    """Raise `PolicyError` listing every violation under `out`; log a one-line pass otherwise."""
    violations = check_site(out)
    if violations:
        raise PolicyError(f"{len(violations)} content policy violation(s):\n" + "\n".join(f"  - {v}" for v in violations))
    logger.info("Content policy check passed for %d pages", len(list(out.rglob("*.html"))))
