"""本机 HTTP 接收器。

页面上拿到 Blob 后直接 POST 过来写盘。绕开 base64：一张 500KB 的图，
base64 之后要在 JS 里拼 70 万字符的字符串，再传回 Python 解码，慢十几倍。
"""
import pathlib
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_state = {"dir": pathlib.Path("."), "last": 0}


class _Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = q.get("name", ["unnamed.bin"])[0]
        size = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(size) if size else b""
        try:
            target = pathlib.Path(_state["dir"]) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            _state["last"] = len(body)
            reply = b"ok"
        except Exception as exc:  # 写盘失败要让页面知道
            reply = f"ERR {exc}".encode()[:120]
        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


class Sink:
    def __init__(self, port: int = 8899):
        self.port = port
        self._srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._srv.shutdown()

    def set_dir(self, path: pathlib.Path):
        path.mkdir(parents=True, exist_ok=True)
        _state["dir"] = path

    @staticmethod
    def last_size() -> int:
        return _state["last"]
