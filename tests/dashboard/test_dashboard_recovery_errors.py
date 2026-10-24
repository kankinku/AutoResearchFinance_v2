"""The dashboard must never silently drop HTTP connections on read-only data failures."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from scripts import fresh_original_dashboard as original
from scripts import fresh_research_dashboard as current


@pytest.mark.parametrize(
    ("module", "handler", "path"),
    [
        (current, current.DashboardHandler, "/api/status"),
        (original, original.OriginalDashboardHandler, "/api/dashboard"),
    ],
)
def test_unexpected_metric_type_is_safe_503_instead_of_dropped_connection(
    monkeypatch: pytest.MonkeyPatch, module: object, handler: type, path: str
) -> None:
    def unavailable(*args: object, **kwargs: object) -> object:
        raise TypeError("invalid raw metric encountered")

    monkeypatch.setattr(module, "snapshot", unavailable)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}{path}"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url, timeout=3)
        assert error.value.code == 503
        assert json.load(error.value)["error"]
        assert error.value.headers["Cache-Control"].startswith("no-store")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_dashboard_js_automatically_retries_without_credentials_in_code() -> None:
    page = original.page("index.html").decode("utf-8")
    script = original.script("app.js").decode("utf-8")
    performance_js = (original.STATIC / "fresh-performance.js").read_text(encoding="utf-8")
    assert 'src="static/fresh-performance.js"' in page
    assert 'fetch("api/status",{cache:"no-store",credentials:"same-origin"})' in performance_js
    assert "setInterval(refresh,5000)" in performance_js
    assert "connection-recheck" in performance_js
    assert "fetch(\"api/dashboard\")" in script
