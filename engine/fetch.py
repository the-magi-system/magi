"""Fetching evidence sources as text (design 22.9.1; plan 9, items 6, 8, 9 and 24).

Melchior.Magi's conclusions rest only on text a program fetched and kept, never on a page the model read by itself.
This module is the one implementation of that fetch:

- Only https. The project's contact details go only to sec.gov hosts, as the SEC asks of programs that read EDGAR;
  without them no request goes to sec.gov at all and the evidence stays pending. Every other host gets the engine's
  generic User-Agent. Two requests to the same host are at least one second apart.
- The character encoding comes from the Content-Type header, a byte order mark or the page's own <meta> declaration,
  in that order; otherwise strict UTF-8, then cp949 (a superset of EUC-KR); failing both, UTF-8 with replacement
  characters. The text is NFC-normalised.
- HTML becomes text without scripts and styles. Content that starts with %PDF- is a PDF whatever its Content-Type;
  PDFs and other formats are not converted (unsupported_format).
- A DART viewer page (dart.fss.or.kr/dsaf001/main.do) holds no report text itself: its script lists the report's
  table of contents, and each top-level section is fetched from /report/viewer.do and joined after its title.
- An EDGAR filing index page (-index.htm) is followed to the filing's main document and its exhibits, at most five.
- HTTP 404, 410 and failed connections mark a fetch as a candidate for a broken link; 403, 429 and 5xx do not,
  because they say nothing about whether the page exists.
"""
from __future__ import annotations

import codecs
import hashlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

from .prices import USER_AGENT
from .timeutil import iso

MAX_CHARS = 1_000_000
MAX_BYTES = 20_000_000
TIMEOUT = 30
SPACING = 1.0  # seconds between two requests to the same host
MAX_EDGAR_PARTS = 5
SNIFF_BYTES = 4096
BROKEN_STATUSES = (404, 410)
KOREAN_CHARSETS = {"euc-kr", "euc_kr", "euckr", "ks_c_5601-1987", "ks_c_5601", "ksc5601", "cp949", "uhc", "x-windows-949"}
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
_DART_NODE = re.compile(r"""^\s*node1\['(\w+)'\]\s*=\s*"(.*)";\s*$""")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Fetched:
    url: str
    final_url: str | None
    http_status: int | None
    content_type: str | None
    format: str  # html | text | pdf | other
    text: str
    truncated: bool
    chars: int
    sha256: str | None
    parts: int
    decoding: str | None  # declared | detected | replaced
    fetched_at: str
    error: str | None  # unreachable | unsupported_format | not_https | pending_contact
    broken_candidate: bool


def normalize(text: str) -> str:
    """NFKC, every kind of white space made one space, no space at either end. Quotes and excerpts use it."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def is_sec_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return host == "sec.gov" or host.endswith(".sec.gov")


# HTML to text ----------------------------------------------------------------------------------------------------

_SKIP = {"script", "style", "noscript", "template", "head"}
_BLOCK = {"p", "div", "br", "tr", "li", "ul", "ol", "table", "thead", "tbody", "tfoot", "section", "article", "h1",
          "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "dl", "dt", "dd", "hr", "header", "footer", "title",
          "caption", "center", "form", "address", "body", "html", "document", "text"}
_CELL = {"td", "th"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skipping += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _CELL:
            self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _CELL:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


# Encodings -------------------------------------------------------------------------------------------------------

def _codec(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip().strip("\"'").lower()
    if name in KOREAN_CHARSETS:
        return "cp949"
    try:
        return codecs.lookup(name).name
    except LookupError:
        return None


def _charset(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = re.search(r"charset\s*=\s*([^;\s]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else None


def decode(body: bytes, content_type: str | None) -> tuple[str, str]:
    """The text and how its encoding was found: declared, detected or replaced."""
    declared = _codec(_charset(content_type))
    if declared is None:
        for bom, name in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"),
                          (codecs.BOM_UTF16_BE, "utf-16")):
            if body.startswith(bom):
                declared = name
                break
    if declared is None:
        match = _META_CHARSET.search(body[:SNIFF_BYTES])
        declared = _codec(match.group(1).decode("ascii", "replace")) if match else None
    if declared is not None:
        try:
            return unicodedata.normalize("NFC", body.decode(declared)), "declared"
        except (UnicodeDecodeError, LookupError):
            pass
    for name in ("utf-8", "cp949"):
        try:
            return unicodedata.normalize("NFC", body.decode(name)), "detected"
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize("NFC", body.decode("utf-8", "replace")), "replaced"


def _looks_html(body: bytes) -> bool:
    head = body[:SNIFF_BYTES].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<html" in head[:1024]


# Fetching --------------------------------------------------------------------------------------------------------

@dataclass
class _Raw:
    status: int | None
    final_url: str | None
    content_type: str | None
    body: bytes
    truncated: bool
    error: str | None = None
    broken: bool = False


class Fetcher:
    def __init__(self, contact: str | None, opener=urllib.request.urlopen, clock=time.monotonic, sleep=time.sleep):
        self._contact = (contact or "").strip() or None
        self._open, self._clock, self._sleep = opener, clock, sleep
        self._last: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = SPACING - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)

    def _get(self, url: str) -> _Raw:
        host = urllib.parse.urlsplit(url).hostname or ""
        agent = self._contact if is_sec_host(host) else USER_AGENT
        self._wait(host)
        request = urllib.request.Request(url, headers={"User-Agent": agent})
        try:
            with self._open(request, timeout=TIMEOUT) as response:
                body = response.read(MAX_BYTES + 1)
                status = getattr(response, "status", None) or 200
                final = response.geturl() if hasattr(response, "geturl") else url
                content_type = response.headers.get("Content-Type") if response.headers is not None else None
        except urllib.error.HTTPError as exc:
            return _Raw(exc.code, url, None, b"", False, "unreachable", exc.code in BROKEN_STATUSES)
        except (urllib.error.URLError, OSError, ValueError):
            return _Raw(None, url, None, b"", False, "unreachable", True)
        finally:
            self._last[host] = self._clock()
        truncated = len(body) > MAX_BYTES
        return _Raw(status, final, content_type, body[:MAX_BYTES], truncated)

    def _result(self, url: str, now: datetime, raw: _Raw | None = None, *, format: str = "other", text: str = "",
                error: str | None = None, parts: int = 1, decoding: str | None = None,
                truncated: bool = False) -> Fetched:
        cut = len(text) > MAX_CHARS
        text = text[:MAX_CHARS]
        has_text = error is None
        return Fetched(url=url, final_url=raw.final_url if raw else None, http_status=raw.status if raw else None,
                       content_type=raw.content_type if raw else None, format=format, text=text if has_text else "",
                       truncated=truncated or cut or bool(raw and raw.truncated),
                       chars=len(text) if has_text else 0,
                       sha256=hashlib.sha256(text.encode("utf-8")).hexdigest() if has_text else None,
                       parts=parts if has_text else 0, decoding=decoding, fetched_at=iso(now), error=error,
                       broken_candidate=bool(raw and raw.broken))

    def _convert(self, raw: _Raw) -> tuple[str, str, str | None, str | None]:
        """(format, text, decoding, error) of one successful response."""
        if raw.body.startswith(b"%PDF-"):
            return "pdf", "", None, "unsupported_format"
        content_type = (raw.content_type or "").split(";")[0].strip().lower()
        if content_type in ("text/html", "application/xhtml+xml") or (
                content_type in ("", "application/octet-stream") and _looks_html(raw.body)):
            text, decoding = decode(raw.body, raw.content_type)
            return "html", html_to_text(text), decoding, None
        if content_type == "text/plain":
            text, decoding = decode(raw.body, raw.content_type)
            return "text", text, decoding, None
        return "other", "", None, "unsupported_format"

    def fetch(self, url: str, now: datetime) -> Fetched:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() != "https" or not parts.hostname:
            return self._result(url, now, error="not_https")
        if is_sec_host(parts.hostname) and self._contact is None:
            return self._result(url, now, error="pending_contact")
        raw = self._get(url)
        if raw.error:
            return self._result(url, now, raw, error=raw.error)
        format_, text, decoding, error = self._convert(raw)
        if error:
            return self._result(url, now, raw, format=format_, error=error)
        if parts.hostname.lower() == "dart.fss.or.kr" and parts.path == "/dsaf001/main.do":
            return self._dart(url, now, raw, text_source=decode(raw.body, raw.content_type)[0], decoding=decoding)
        if is_sec_host(parts.hostname) and parts.path.endswith("-index.htm"):
            return self._edgar_index(url, now, raw, decode(raw.body, raw.content_type)[0], decoding)
        return self._result(url, now, raw, format=format_, text=text, decoding=decoding)

    def page(self, url: str) -> str | None:
        """One page as decoded HTML, without following anything: an EDGAR filing index page, to read its filing
        date. None when it cannot be fetched; the same rules for https, the contact and spacing apply."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() != "https" or not parts.hostname:
            return None
        if is_sec_host(parts.hostname) and self._contact is None:
            return None
        raw = self._get(url)
        if raw.error or raw.body.startswith(b"%PDF-"):
            return None
        return decode(raw.body, raw.content_type)[0]

    # DART ------------------------------------------------------------------------------------------------------

    def _dart(self, url: str, now: datetime, raw: _Raw, text_source: str, decoding: str | None) -> Fetched:
        nodes = dart_nodes(text_source)
        if not nodes:
            return self._result(url, now, raw, format="html", text=html_to_text(text_source), decoding=decoding)
        sections, worst, truncated = [], decoding, False
        for node in nodes:
            query = urllib.parse.urlencode({key: node[key] for key in
                                            ("rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")})
            part = self._get(f"https://dart.fss.or.kr/report/viewer.do?{query}")
            if part.error:
                return self._result(url, now, _Raw(part.status, raw.final_url, raw.content_type, b"", False,
                                                   "unreachable", False), error="unreachable")
            format_, text, part_decoding, error = self._convert(part)
            if error:
                return self._result(url, now, raw, format=format_, error=error)
            truncated = truncated or part.truncated
            if part_decoding == "replaced" or (part_decoding == "detected" and worst == "declared"):
                worst = part_decoding
            sections.append(f"{node['text']}\n{text}".strip())
        return self._result(url, now, raw, format="html", text="\n\n".join(sections), parts=len(nodes),
                            decoding=worst, truncated=truncated)

    # EDGAR filing index ----------------------------------------------------------------------------------------

    def _edgar_index(self, url: str, now: datetime, raw: _Raw, html: str, decoding: str | None) -> Fetched:
        documents = edgar_documents(html, url)
        if not documents:
            return self._result(url, now, raw, format="html", text=html_to_text(html), decoding=decoding)
        texts, truncated = [], False
        for document in documents:
            part = self._get(document)
            if part.error:
                return self._result(url, now, _Raw(part.status, raw.final_url, raw.content_type, b"", False,
                                                   "unreachable", False), error="unreachable")
            format_, text, _, error = self._convert(part)
            if error:
                continue
            truncated = truncated or part.truncated
            texts.append(text)
        if not texts:
            return self._result(url, now, raw, format="other", error="unsupported_format")
        return self._result(url, now, raw, format="html", text="\n\n".join(texts), parts=len(texts),
                            decoding=decoding, truncated=truncated)


def dart_nodes(page: str) -> list[dict]:
    """The top-level nodes of a DART viewer page's table of contents, in order.

    The page's script builds the tree with `var node1 = {}` for each top-level node and `node2` and deeper for the
    nodes below it, each pushed into its parent; a request for a top-level node returns every section below it."""
    nodes, current = [], None
    for line in page.splitlines():
        stripped = line.strip()
        if stripped == "var node1 = {};":
            current = {}
            nodes.append(current)
            continue
        match = _DART_NODE.match(line)
        if match and current is not None:
            current[match.group(1)] = match.group(2)
    keys = ("text", "rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")
    return [node for node in nodes if all(node.get(key) for key in keys)]


class _FileTable(HTMLParser):
    """The rows of an EDGAR index page's "Document Format Files" table: (seq, type, href)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.rows: list[list] = []
        self.cell: list[str] | None = None
        self.row: list | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("summary") == "Document Format Files":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag == "td" and self.row is not None:
            self.cell = []
            self.row.append({"text": "", "href": None})
        elif self.in_table and tag == "a" and self.row:
            self.row[-1]["href"] = attrs.get("href")

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        elif self.in_table and tag == "td" and self.row and self.cell is not None:
            self.row[-1]["text"] = " ".join("".join(self.cell).split())
            self.cell = None
        elif self.in_table and tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def edgar_documents(html: str, base: str) -> list[str]:
    """The filing's main document (sequence 1) and its exhibits (type EX-...), at most five, as https addresses."""
    table = _FileTable()
    table.feed(html)
    found = []
    for row in table.rows:
        if len(row) < 4 or not row[2]["href"]:
            continue
        seq, kind, href = row[0]["text"], row[3]["text"], row[2]["href"]
        if seq != "1" and not kind.upper().startswith("EX-"):
            continue
        if href.startswith("/ix?doc="):
            href = href[len("/ix?doc="):]
        address = urllib.parse.urljoin(base, href)
        if address.startswith("https://") and address not in found:
            found.append(address)
    return found[:MAX_EDGAR_PARTS]


def filing_date(html: str) -> str | None:
    """The Filing Date an EDGAR filing index page states, as YYYY-MM-DD."""
    match = re.search(r'Filing Date</div>\s*<div class="info">\s*(\d{4}-\d{2}-\d{2})\s*</div>', html)
    return match.group(1) if match else None


def edgar_index_url(url: str) -> str | None:
    """The filing index page of a document in an EDGAR filing directory, or None for other addresses."""
    parts = urllib.parse.urlsplit(url)
    match = re.match(r"^/Archives/edgar/data/(\d+)/(\d{18})/[^/]+$", parts.path)
    if not is_sec_host(parts.hostname or "") or not match:
        return None
    accession = match.group(2)
    dashed = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    return f"https://www.sec.gov/Archives/edgar/data/{match.group(1)}/{accession}/{dashed}-index.htm"
