# veil/netcheck.py - is the internet the slow part? (Oct 15)
#
# After a request on a route that leaves the house (stats: internet_check: routes, e.g.
# off_platform), the router times one reply from public DNS servers (servers): a ping when the
# container can send one, otherwise a DNS lookup sent to that same server (method: ping or dns).
# The fastest server's time is kept. No background process: at most one check every
# cooldown_minutes, started after the answer has gone, so it never slows the request. Every
# request on the route inside the cool-down carries the last check (net_at: when it was taken).
# Saved on the request's row in the activity log (net_ms, net_method, net_at); the Stats page
# compares it with the usual (the typical of the checks kept). A lookup always takes longer than
# a ping, so only checks of the same method are compared.
#
# The servers must be in security: outbound_allowed; one that isn't is skipped and shows on the
# Security page as refused (method: not permitted when none is).

import asyncio
import logging
import os
import socket
import struct
import time

from veil import access

log = logging.getLogger("router")


def ping(server, timeout):
    """ms for one ping reply, None when none came in time; raises OSError when the container
    can't send a ping at all (no ping socket)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP) as s:
        s.settimeout(timeout)
        t0 = time.monotonic()
        s.sendto(struct.pack("!BBHHH", 8, 0, 0, os.getpid() & 0xFFFF, 1) + b"veil", (server, 0))
        return _reply(s, t0)


def lookup(server, name, timeout):
    """ms for the answer to one DNS question (name, an address) sent to the server, None when none came."""
    labels = b"".join(bytes([len(p)]) + p.encode() for p in name.strip(".").split(".") if p)
    question = struct.pack("!HHHHHH", os.getpid() & 0xFFFF, 0x0100, 1, 0, 0, 0) + labels + b"\0" + struct.pack("!HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.monotonic()
        s.sendto(question, (server, 53))
        return _reply(s, t0)


def _reply(s, t0):
    try:
        s.recvfrom(512)
    except (socket.timeout, OSError):
        return None
    return round((time.monotonic() - t0) * 1000, 1)


class Checker:
    def __init__(self, spec, pinger=ping, looker=lookup):
        self.enabled = bool(spec.get("enabled", True))
        self.servers = [str(s) for s in spec.get("servers") or []]
        self.routes = set(spec.get("routes") or [])
        self.cooldown = float(spec.get("cooldown_minutes", 5)) * 60
        self.timeout = float(spec.get("timeout_ms", 1000)) / 1000
        self.name = str(spec.get("lookup_name") or "example.com")
        # an outside hop quicker than this answered from the app's own memory (the weather brain's
        # forecast kept: 30-100 ms, against 300 ms and more when it called out), so there's no
        # internet in it to check
        self.min_outside = float(spec.get("min_outside_ms", 200))
        self.ping, self.lookup = pinger, looker
        self.can_ping = True           # until the container refuses a ping socket
        self.last = None               # the newest check: {ms, method, server, time}
        self._busy = False

    def wanted(self, route, outside_ms=None):
        """A check is wanted after a request on one of routes whose outside hop took min_outside_ms
        or more (outside_ms None: not known, so checked)."""
        return self.enabled and bool(self.servers) and route in self.routes and (
            outside_ms is None or float(outside_ms) >= self.min_outside)

    def measure(self):
        """One check now: the fastest reply over the servers permitted (blocking; a thread)."""
        best, method = None, "not permitted"
        for server in self.servers:
            if not access.ACCESS.permits_host(server, "the internet check"):
                access.ACCESS.note("outbound_allowed", server, "the internet check")
                continue
            ms, method = self._one(server)
            if ms is not None and (best is None or ms < best["ms"]):
                best = {"ms": ms, "method": method, "server": server}
        return dict(best or {"ms": None, "method": method if method == "not permitted" else "no answer",
                             "server": None}, time=time.time())

    def _one(self, server):
        if self.can_ping:
            try:
                return self.ping(server, self.timeout), "ping"
            except OSError as e:
                self.can_ping = False
                log.info("  internet check: no ping here (%s); timing a DNS lookup instead", e)
        return self.lookup(server, self.name, self.timeout), "dns"

    async def after(self, route, rid, store):
        """After a request on a route that leaves the house: a fresh check (cool-down allowing)
        or the last one, saved on its row."""
        if not rid or not store or not self.wanted(route):
            return
        if self._busy:
            return
        if not self.last or time.time() - self.last["time"] >= self.cooldown:
            self._busy = True
            try:
                self.last = await asyncio.to_thread(self.measure)
            finally:
                self._busy = False
            log.info("  internet check: %s by %s (%s)", f"{self.last['ms']:g} ms" if self.last["ms"] is not None
                     else "no reply", self.last["method"], self.last["server"] or "no server")
        store.finish(rid, net_ms=self.last["ms"], net_method=self.last["method"], net_at=self.last["time"])

    def soon(self, route, rid, store, outside_ms=None):
        """after(), started without waiting (from inside a request)."""
        if self.wanted(route, outside_ms) and rid:
            try:
                asyncio.get_running_loop().create_task(self.after(route, rid, store))
            except RuntimeError:          # no event loop (a test)
                pass
