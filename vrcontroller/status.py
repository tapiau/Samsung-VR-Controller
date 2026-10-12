"""Local status page: GET / serves the page, GET /events streams daemon state (SSE)."""
import asyncio
import json
import logging
from pathlib import Path

log = logging.getLogger("vrcontroller")

PAGE = Path(__file__).with_name("status.html")
UPDATE_INTERVAL = 0.05  # 20 updates/s


class StatusServer:
    def __init__(self, daemon, host: str = "127.0.0.1", port: int = 8765):
        self.daemon = daemon
        self.host = host
        self.port = port

    async def start(self) -> asyncio.AbstractServer:
        server = await asyncio.start_server(self.handle, self.host, self.port)
        log.info("status page: http://%s:%d/", self.host, self.port)
        return server

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.readline()
            while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass  # skip headers
            parts = request.decode("latin-1").split()
            path = parts[1] if len(parts) > 1 else "/"
            if path == "/":
                body = PAGE.read_bytes()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                             b"Cache-Control: no-store\r\n"
                             b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
            elif path == "/events":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                             b"Cache-Control: no-store\r\nConnection: keep-alive\r\n\r\n")
                while True:
                    data = json.dumps(self.daemon.snapshot(), separators=(",", ":"))
                    writer.write(f"data: {data}\n\n".encode())
                    await writer.drain()
                    await asyncio.sleep(UPDATE_INTERVAL)
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n"
                             b"Connection: close\r\n\r\n")
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass  # browser closed the tab
        finally:
            writer.close()
