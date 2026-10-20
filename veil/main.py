# veil/main.py - starts Wepwawet Veil: the chat door (router.py, port 8770, plain http for
# LiteLLM) and the pages with their admin API (veil/web.py, port 8771, https), in one process
# so the pages see exactly the router that's running.
#   python -m veil.main          (the container's command; see the Dockerfile)
# The pages can be switched off with web: enabled: false in settings.yaml.
# With Oread on and its source wyoming, the router also opens a Wyoming port per device and
# sits in the audio path in front of Oread (veil/wyoming.py).

import asyncio
import contextlib
import logging
import os
import signal

import uvicorn

from veil import config, tls, wyoming

log = logging.getLogger("router")


class Quiet(logging.Filter):
    """Leave routine check-ins out of the log (router: quiet_paths), so real requests stand out."""

    def __init__(self, paths):
        super().__init__()
        self.paths = [str(p) for p in paths or []]

    def filter(self, record):
        msg = record.getMessage()
        return not any(f" {p} " in msg or f" {p}?" in msg for p in self.paths)


async def serve():
    import router                      # loads settings, topics, phrases... and logs them
    from veil import web
    s = router.SETTINGS
    logging.getLogger("uvicorn.access").addFilter(
        Quiet(config.section(s, "router").get("quiet_paths", ["/v1/models", "/health", "/firewall/summary"])))
    chat_port = int(os.environ.get("ROUTER_PORT", 8770))
    servers = [uvicorn.Server(uvicorn.Config(router.app, host="0.0.0.0", port=chat_port,
                                             log_level="info", proxy_headers=False))]
    w = config.section(s, "web")
    if w.get("enabled", True):
        cert, key = tls.files(w, config.DATA_DIR)
        port = int(os.environ.get("WEB_PORT", w.get("port", 8771)))
        web.SECURE_COOKIES = bool(cert)
        servers.append(uvicorn.Server(uvicorn.Config(
            web.app, host="0.0.0.0", port=port, log_level="warning", proxy_headers=False,
            ssl_certfile=cert, ssl_keyfile=key)))
        log.info("the pages: %s://<server>:%d/", "https" if cert else "http", port)
        web.startup()
    else:
        log.info("the pages are off (web: enabled: false)")
    await wyoming.start(s)
    # one stop (docker compose stop, Ctrl+C) stops both servers
    for srv in servers:
        srv.capture_signals = contextlib.nullcontext          # uvicorn 0.29 and later
        srv.install_signal_handlers = lambda: None            # older uvicorn
    loop = asyncio.get_running_loop()

    def stop(*_):
        for srv in servers:
            srv.should_exit = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await asyncio.gather(*(srv.serve() for srv in servers))
    finally:
        await wyoming.stop()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
