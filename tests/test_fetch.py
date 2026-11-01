"""Fetching evidence sources as text (plan 9, Task 7; design 22.9.1). No test touches the network."""
import email.message
import io
import re
import urllib.error
from datetime import datetime, timezone

from tests.util import REPO_ROOT

SOURCES = REPO_ROOT / "tests" / "fixtures" / "sources"
NOW = datetime(2026, 11, 10, 23, 50, tzinfo=timezone.utc)
CONTACT = "The Magi System contact"
EX99 = "https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm"
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003335"
KOREAN = "배당금의 지급 (7,486,679,200) 기말현금및현금성자산 15,436,600,653"


def fixture(name):
    """(status, headers, body) of a recorded response."""
    lines = (SOURCES / f"{name}.headers").read_text(encoding="utf-8").splitlines()
    status = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return status, headers, (SOURCES / f"{name}.body").read_bytes()


class Response:
    def __init__(self, url, status, headers, body):
        self.status, self._url, self._body = status, url, io.BytesIO(body)
        self.headers = email.message.Message()
        for key, value in headers.items():
            self.headers[key] = value

    def geturl(self):
        return self._url

    def read(self, size=-1):
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    """Answers each address from `routes` (or `default`) and records every request with its headers."""

    def __init__(self, routes=None, default=None, prefixes=None):
        self.routes, self.default, self.requests = dict(routes or {}), default, []
        self.prefixes = list(prefixes or [])

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.requests.append({"url": url, "headers": {k.lower(): v for k, v in request.header_items()},
                              "timeout": timeout})
        answer = self.routes.get(url)
        if answer is None:
            answer = next((value for prefix, value in self.prefixes if url.startswith(prefix)), self.default)
        if answer is None:
            raise AssertionError(f"unexpected request {url}")
        if isinstance(answer, Exception):
            raise answer
        status, headers, body = answer
        if status >= 300:  # the Fetcher's own opener never follows a redirect; it raises, as for an error
            hdrs = email.message.Message()
            for key, value in headers.items():
                hdrs[key] = value
            raise urllib.error.HTTPError(url, status, "error", hdrs, io.BytesIO(body))
        return Response(url, status, headers, body)


class Clock:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 6))
        self.now += seconds


def fetcher(contact=CONTACT, routes=None, default=None, prefixes=None):
    from engine.fetch import Fetcher
    opener, clock = Opener(routes, default, prefixes), Clock()
    return Fetcher(contact, opener=opener, clock=clock, sleep=clock.sleep), opener, clock


HTML = (200, {"Content-Type": "text/html; charset=utf-8"}, b"<html><body><p>A plain page of text.</p></body></html>")


def test_the_contact_goes_only_to_sec_hosts():
    from engine.prices import USER_AGENT
    sec_json = "https://data.sec.gov/submissions/CIK0001717115.json"
    other = "https://dart.fss.or.kr/report/viewer.do?rcpNo=1"
    fetch, opener, _ = fetcher(routes={EX99: HTML, sec_json: HTML, other: HTML})
    for url in (EX99, sec_json, other):
        fetch.fetch(url, NOW)
    agents = {r["url"]: r["headers"]["user-agent"] for r in opener.requests}
    assert agents[EX99] == CONTACT and agents[sec_json] == CONTACT
    assert agents[other] == USER_AGENT and CONTACT not in agents[other]


def test_no_request_goes_to_sec_without_a_contact():
    for contact in (None, ""):
        fetch, opener, _ = fetcher(contact=contact, default=HTML)
        result = fetch.fetch(EX99, NOW)
        assert result.error == "pending_contact" and opener.requests == []


def test_the_code_holds_no_mail_address():
    import engine.fetch  # the module that sends the contact is among the files scanned
    assert (REPO_ROOT / "engine" / "fetch.py").exists() and engine.fetch.Fetcher
    pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    allowed = {"41898282+github-actions[bot]@users.noreply.github.com", "github-actions[bot]@users.noreply.github.com"}
    found = []
    for top in ("engine", "agents", ".github"):
        for path in (REPO_ROOT / top).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found += [f"{path.relative_to(REPO_ROOT)}: {m}" for m in pattern.findall(text)
                      if m not in allowed and not m.startswith("41898282+github-actions")]
    assert found == []


def test_requests_to_one_host_are_a_second_apart():
    fetch, opener, clock = fetcher(default=HTML)
    host = "https://kind.krx.co.kr/external/"
    fetch.fetch(host + "a.htm", NOW)
    clock.now += 0.25
    fetch.fetch(host + "b.htm", NOW)
    fetch.fetch(host + "c.htm", NOW)
    assert clock.slept == [0.75, 1.0]
    fetch.fetch("https://www.myjvm.com/x.htm", NOW)
    assert clock.slept == [0.75, 1.0]


def test_html_becomes_text_without_scripts_and_styles():
    fetch, _, _ = fetcher(routes={EX99: fixture("sec-tem-ex99")})
    result = fetch.fetch(EX99, NOW)
    assert result.error is None and result.format == "html" and result.http_status == 200
    assert "382.5" in result.text and "<script" not in result.text and "function(" not in result.text
    assert result.parts == 1 and result.chars == len(result.text)


def test_the_charset_comes_from_the_header_then_the_page():
    url = "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814003335&eleId=24"
    fetch, _, _ = fetcher(routes={url: fixture("dart-node24")})
    result = fetch.fetch(url, NOW)
    assert "배당금의 지급" in result.text and "(7,486,679,200)" in result.text and result.decoding == "declared"
    page = f'<html><head><meta charset="euc-kr"></head><body><p>{KOREAN}</p></body></html>'.encode("cp949")
    other = "https://kind.krx.co.kr/external/euc.htm"
    fetch, _, _ = fetcher(routes={other: (200, {"Content-Type": "text/html"}, page)})
    result = fetch.fetch(other, NOW)
    assert KOREAN in result.text and result.decoding == "declared"


def test_korean_without_any_declaration_is_decoded():
    page = f"<html><body><p>{KOREAN}</p></body></html>".encode("cp949")
    url = "https://kind.krx.co.kr/external/plain.htm"
    fetch, _, _ = fetcher(routes={url: (200, {"Content-Type": "text/html"}, page)})
    result = fetch.fetch(url, NOW)
    assert KOREAN in result.text and result.decoding == "detected"
    broken = "https://kind.krx.co.kr/external/broken.htm"
    fetch, _, _ = fetcher(routes={broken: (200, {"Content-Type": "text/html"}, b"<html><p>bad \xff\xff bytes</p></html>")})
    result = fetch.fetch(broken, NOW)
    assert result.decoding == "replaced" and "bad" in result.text


def test_a_pdf_is_recognised_by_its_bytes():
    status, headers, body = fixture("jvm-q3-pdf.head")
    assert headers["Content-Type"] == "file/unknown"
    url = "https://www.myjvm.com/bbs/bbs_download.php?idx=688&download=1"
    fetch, _, _ = fetcher(routes={url: (status, headers, body)})
    result = fetch.fetch(url, NOW)
    assert (result.format, result.error, result.text) == ("pdf", "unsupported_format", "")
    status, headers, body = fixture("krx-ir-pdf.head")
    assert status == 200 and headers["Content-Type"] == "application/pdf"
    url = "https://kind.krx.co.kr/external/dst/irReference/18969/x.pdf"
    fetch, _, _ = fetcher(routes={url: (status, headers, body)})
    assert fetch.fetch(url, NOW).format == "pdf"


def test_a_dart_viewer_page_is_followed_to_its_sections():
    viewer = "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814003335&dcmNo=11536719&eleId="
    empty = (200, {"Content-Type": "text/html; charset=utf-8"}, b"<html><body></body></html>")
    # The two recorded sections stand for two top-level nodes; every other node answers with an empty page.
    prefixes = [(viewer + "17&", fixture("dart-node19")), (viewer + "114&", fixture("dart-node24"))]
    fetch, opener, clock = fetcher(routes={DART: fixture("dart-main")}, default=empty, prefixes=prefixes)
    result = fetch.fetch(DART, NOW)
    assert result.error is None and result.parts == 15
    assert "(단위 : 원)" in result.text and "15,436,600,653" in result.text and "배당금의 지급" in result.text
    assert "III. 재무에 관한 사항" in result.text
    viewers = [r["url"] for r in opener.requests[1:]]
    assert len(viewers) == 15 and all(url.startswith(viewer) and url.endswith("dtd=dart4.xsd") for url in viewers)
    assert clock.slept == [1.0] * 15


def test_long_text_is_cut_and_marked():
    import hashlib
    url = "https://www.myjvm.com/long.txt"
    fetch, _, _ = fetcher(routes={url: (200, {"Content-Type": "text/plain; charset=utf-8"}, b"a" * 1_200_000)})
    result = fetch.fetch(url, NOW)
    assert result.format == "text" and result.chars == 1_000_000 and result.truncated is True
    assert result.sha256 == hashlib.sha256(("a" * 1_000_000).encode("utf-8")).hexdigest()


def test_failures_are_classified():
    url = "https://kind.krx.co.kr/external/2026/03/18/000199/20260318000891/72101.htm"
    for status, broken in ((404, True), (410, True), (403, False), (429, False), (503, False)):
        fetch, _, _ = fetcher(routes={url: (status, {}, b"")})
        result = fetch.fetch(url, NOW)
        assert (result.error, result.broken_candidate, result.http_status) == ("unreachable", broken, status)
    fetch, _, _ = fetcher(routes={url: urllib.error.URLError("connection reset")})
    result = fetch.fetch(url, NOW)
    assert (result.error, result.broken_candidate, result.http_status) == ("unreachable", True, None)


def test_only_https_is_fetched():
    for url in ("http://www.sec.gov/x.htm", "ftp://example.org/x.txt"):
        fetch, opener, _ = fetcher(default=HTML)
        assert fetch.fetch(url, NOW).error == "not_https" and opener.requests == []


# Redirects (review of PR #111): every hop is checked, and the contact still goes only to sec.gov ---------------------

def moved(location, status=301):
    return status, {"Location": location}, b""


def test_a_redirect_from_sec_to_another_host_never_gets_the_contact():
    from engine.prices import USER_AGENT
    other = "https://mirror.example.org/tem-ex99_1.htm"
    fetch, opener, _ = fetcher(routes={EX99: moved(other), other: HTML})
    result = fetch.fetch(EX99, NOW)
    assert result.error is None and result.final_url == other and result.url == EX99
    agents = [(r["url"], r["headers"]["user-agent"]) for r in opener.requests]
    assert agents == [(EX99, CONTACT), (other, USER_AGENT)]


def test_a_redirect_to_http_is_refused():
    plain = "http://www.sec.gov/Archives/x.htm"
    fetch, opener, _ = fetcher(routes={EX99: moved(plain, 302)}, default=HTML)
    result = fetch.fetch(EX99, NOW)
    assert result.error == "not_https" and result.final_url == plain and [r["url"] for r in opener.requests] == [EX99]


def test_another_host_redirecting_to_sec_gets_the_contact_or_waits_for_it():
    from engine.prices import USER_AGENT
    start = "https://www.example.org/filing"
    leading_zero = "https://www.sec.gov/Archives/edgar/data/0001717115/000119312526326083/tem-ex99_1.htm"
    routes = {start: moved(leading_zero, 302), leading_zero: moved(EX99), EX99: HTML}
    fetch, opener, _ = fetcher(routes=routes)
    result = fetch.fetch(start, NOW)
    assert result.error is None and result.final_url == EX99
    assert [r["headers"]["user-agent"] for r in opener.requests] == [USER_AGENT, CONTACT, CONTACT]
    fetch, opener, _ = fetcher(contact=None, routes=routes)
    result = fetch.fetch(start, NOW)
    assert result.error == "pending_contact" and [r["url"] for r in opener.requests] == [start]


def test_more_than_five_redirects_are_unreachable():
    hops = [f"https://www.example.org/hop{n}" for n in range(7)]
    routes = {hop: moved(hops[n + 1], 307) for n, hop in enumerate(hops[:-1])}
    routes[hops[-1]] = HTML
    fetch, opener, _ = fetcher(routes=routes)
    result = fetch.fetch(hops[0], NOW)
    assert result.error == "unreachable" and result.broken_candidate is False and len(opener.requests) == 6
    fetch, _, _ = fetcher(routes={**routes, hops[5]: HTML})
    assert fetch.fetch(hops[0], NOW).error is None  # five hops are followed


def test_an_ip_address_or_localhost_is_never_fetched():
    for url in ("https://127.0.0.1/x.htm", "https://[::1]/x.htm", "https://localhost/x.htm", "https://10.0.0.8/a"):
        fetch, opener, _ = fetcher(default=HTML)
        result = fetch.fetch(url, NOW)
        assert result.error == "unreachable" and result.broken_candidate is False and opener.requests == [], url
    fetch, opener, _ = fetcher(routes={"https://www.example.org/a": moved("https://169.254.169.254/latest")})
    assert fetch.fetch("https://www.example.org/a", NOW).error == "unreachable" and len(opener.requests) == 1
