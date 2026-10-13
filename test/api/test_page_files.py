import asyncio

import pytest

pytest.importorskip("fastapi")

from api.page_files import PageFiles  # noqa: E402


def _get(app, path, headers=None):
    """The status and the headers that `app` answers a GET of `path` with."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = sent[0]
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


def test_the_page_is_served_for_the_browser_to_check_each_time_it_opens_it(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    app = PageFiles(directory=tmp_path, html=True)

    status, headers = _get(app, "/")
    assert status == 200
    assert headers["cache-control"] == "no-cache"

    # Asked again with what it kept, the browser is told it is still the page
    status, headers = _get(app, "/", {"if-none-match": headers["etag"]})
    assert status == 304
    assert headers["cache-control"] == "no-cache"
