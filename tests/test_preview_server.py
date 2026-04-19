from __future__ import annotations

import http.client
import json
import threading
from functools import partial
from pathlib import Path

from prefxplain.preview_server import PreviewRequestHandler, resolve_safe_child_path


def test_resolve_safe_child_path_blocks_traversal(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    assert resolve_safe_child_path(root, "dir/file.txt") == root / "dir" / "file.txt"
    assert resolve_safe_child_path(root, "../escape.txt") is None
    assert resolve_safe_child_path(root, "/tmp/escape.txt") is None


def test_preview_server_reads_and_writes_files(tmp_path: Path) -> None:
    file_path = tmp_path / "src" / "main.js"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("console.log('before');\n", encoding="utf-8")

    handler = partial(
        PreviewRequestHandler,
        directory=str(tmp_path),
        root_dir=tmp_path,
    )

    from http.server import ThreadingHTTPServer

    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/__prefxplain__/file?path=src%2Fmain.js")
        res = conn.getresponse()
        payload = json.loads(res.read().decode("utf-8"))
        conn.close()

        assert res.status == 200
        assert payload["ok"] is True
        assert payload["content"] == "console.log('before');\n"

        body = json.dumps({
            "path": "src/main.js",
            "content": "console.log('after');\n",
        }).encode("utf-8")
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/__prefxplain__/file",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        res = conn.getresponse()
        payload = json.loads(res.read().decode("utf-8"))
        conn.close()

        assert res.status == 200
        assert payload["ok"] is True
        assert file_path.read_text(encoding="utf-8") == "console.log('after');\n"

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/__prefxplain__/file?path=..%2Fsecret.txt")
        res = conn.getresponse()
        payload = json.loads(res.read().decode("utf-8"))
        conn.close()

        assert res.status == 400
        assert payload["ok"] is False

        server.shutdown()
        thread.join(timeout=5)
