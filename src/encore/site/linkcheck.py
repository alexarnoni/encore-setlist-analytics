"""Link check over the generated site (spec R8.3): no broken internal link, anchor or alternate.

Internal means root-relative (`/pt/...`), relative to the page, or absolute under the site's own origin
(canonical and hreflang links are written that way). Each must resolve to a file in the output, and a
`#fragment` must name an element that exists on the target page. External links are not fetched: the
build makes no network request.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from encore.site.policy import Violation

logger = logging.getLogger(__name__)

_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


class LinkError(Exception):
    """One or more internal links are broken; the build must not ship."""


class _Page(HTMLParser):
    """The addresses a page points at, and the ids it defines."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, str]] = []  # (tag, address)
        self.ids: set[str] = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for attribute in ("href", "src"):
            if tag in ("a", "link", "script", "img", "source") and a.get(attribute):
                self.targets.append((tag, a[attribute]))
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            match = re.search(r"url\s*=\s*(\S+)", a.get("content", ""), re.I)
            if match:
                self.targets.append(("meta refresh", match.group(1)))


def _file_for(out: Path, url_path: str) -> Path | None:
    """The file a URL path serves, following the static host's rules (`/x/` serves `x/index.html`)."""
    relative = unquote(url_path).lstrip("/")
    candidate = out / relative
    if url_path.endswith("/") or not relative:
        candidate = candidate / "index.html"
    if candidate.is_file():
        return candidate
    if candidate.is_dir() and (candidate / "index.html").is_file():
        return candidate / "index.html"
    return None


def check_links(out: Path, origin: str) -> list[Violation]:
    """Check every internal link, `link`, `script` and `meta refresh` target of every page under `out`."""
    origin_host = urlparse(origin).netloc
    pages = {path: _Page(path.read_text(encoding="utf8")) for path in out.rglob("*.html")}
    found: list[Violation] = []
    for path, page in pages.items():
        relative = path.relative_to(out).as_posix()
        page_url = "/" + relative.removesuffix("index.html")
        for tag, address in page.targets:
            if address.startswith(_SKIP_SCHEMES) or address.startswith("//"):
                continue
            parsed = urlparse(address)
            if parsed.scheme and parsed.netloc != origin_host:
                continue  # external
            if parsed.scheme:  # absolute, under our own origin
                url_path = parsed.path or "/"
            else:  # root-relative or relative to this page; a pure `#fragment` stays on the page
                url_path = urljoin(page_url, parsed.path) if parsed.path else page_url
            target = _file_for(out, url_path)
            if target is None:
                found.append(Violation(relative, "broken link", f"<{tag}> {address} does not exist in the site"))
                continue
            fragment = parsed.fragment
            if fragment and target.suffix == ".html" and unquote(fragment) not in pages[target].ids:
                found.append(Violation(relative, "broken anchor", f"<{tag}> {address}: no element with id {fragment!r}"))
    return found


def enforce(out: Path, origin: str) -> None:
    """Raise `LinkError` listing every broken link under `out`."""
    violations = check_links(out, origin)
    if violations:
        raise LinkError(f"{len(violations)} broken link(s):\n" + "\n".join(f"  - {v}" for v in violations))
    logger.info("Link check passed for %d pages", len(list(out.rglob("*.html"))))
