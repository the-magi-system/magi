# Recorded source pages

Real responses from the sources that production's evidence cites, recorded once so that the evidence-check tests of plan 9 run without network access (Task 5). They are third-party documents: they are not covered by this repository's licence, and they are here only as test data.

| Files | Request | Recorded (UTC) | HTTP | `Content-Type` | Body bytes |
|---|---|---|---|---|---|
| `sec-tem-ex99.body`, `sec-tem-ex99.headers` | https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm | 2026-11-01T06:02:24Z | 200 | `text/html` | 1363860 |
| `sec-tem-ex99-index.body`, `sec-tem-ex99-index.headers` | https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/0001193125-26-326083-index.htm | 2026-11-01T06:02:26Z | 200 | `text/html; charset=UTF-8` | 9354 |
| `sec-tem-submissions.body`, `sec-tem-submissions.headers` | https://data.sec.gov/submissions/CIK0001717115.json | 2026-11-01T06:02:28Z | 200 | `application/json` | 79362 |
| `sec-ccc-8k-index.body`, `sec-ccc-8k-index.headers` | https://www.sec.gov/Archives/edgar/data/1818201/000119312526438167/0001193125-26-438167-index.htm | 2026-11-01T06:02:30Z | 200 | `text/html; charset=UTF-8` | 6939 |
| `sec-ccc-browse.body`, `sec-ccc-browse.headers` | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001818201&type=8-K&dateb=&owner=include&count=40 | 2026-11-01T06:02:32Z | 200 | `text/html; charset=UTF-8` | 38715 |
| `dart-main.body`, `dart-main.headers` | https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003335 | 2026-11-01T06:02:36Z | 200 | `text/html; charset=UTF-8` | 115031 |
| `dart-node19.body`, `dart-node19.headers` | https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814003335&dcmNo=11536719&eleId=19&offset=223813&length=150293&dtd=dart4.xsd | 2026-11-01T06:02:38Z | 200 | `text/html; charset=utf-8` | 42631 |
| `dart-node24.body`, `dart-node24.headers` | https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814003335&dcmNo=11536719&eleId=24&offset=347120&length=26990&dtd=dart4.xsd | 2026-11-01T06:02:41Z | 200 | `text/html; charset=utf-8` | 8679 |
| `krx-valueup.body`, `krx-valueup.headers` | https://kind.krx.co.kr/external/2026/03/18/000199/20260318000891/72101.htm | 2026-11-01T06:02:43Z | 200 | `text/html` | 15704 |
| `krx-ir-pdf.head.body`, `krx-ir-pdf.head.headers` | https://kind.krx.co.kr/external/dst/irReference/18969/JVM_IR%EC%9E%90%EB%A3%8C_2026%20AUG_KR.pdf | 2026-11-01T06:02:48Z | 200 | `application/pdf` | 4096 |
| `jvm-q3-pdf.head.body`, `jvm-q3-pdf.head.headers` | https://www.myjvm.com/bbs/bbs_download.php?idx=688&download=1 | 2026-11-01T06:02:56Z | 200 | `file/unknown` | 4096 |

Each response is stored twice: `<name>.body` holds the response body byte for byte, and `<name>.headers` holds the status line and the response headers, with `Set-Cookie` removed. `.gitattributes` keeps these files out of line-ending conversion.

- The two PDFs keep only their first 4,096 bytes, because the tests only need to recognise the format. They are `krx-ir-pdf.head.*` and `jvm-q3-pdf.head.*`.
- The SEC requests carried a generic User-Agent, not the project's contact, because the contact is a repository secret that does not pass through the session that recorded these. No contact details are in these files.
- The maintainer's network received HTTP 200 from `kind.krx.co.kr` for both KRX requests. A cloud address received 403 when plan 9 was written, so GitHub's runners may too. The tests treat 403 separately (plan 9, item 8); the live behaviour is checked in the sandbox.
