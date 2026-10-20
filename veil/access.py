# veil/access.py - permitted addresses, in and out (the IP allow lists).
#
# Three lists in settings.yaml, security: (each a list of addresses like 192.168.1.50 or
# ranges like 192.168.1.0/24; edited on the Security page):
#   inbound_allowed:  who may call the chat door (port 8770: LiteLLM, Home Assistant, the tools)
#   admin_allowed:    who may open the pages and the admin API (port 8771)
#   outbound_allowed: where the router may call out to (LiteLLM, the weather brain, Donetick,
#                     Oread, Home Assistant). A call anywhere else is refused before it's made.
# An empty list means the local network only (private, loopback and Tailscale addresses),
# never an address on the internet, the same rule as Oread's listening ports.
#
# Refused callers and refused calls out are remembered (the last 20 of each) for the
# Security page, and logged at most once a minute per address. Permitted ones are remembered
# too (the last 30 addresses on each list, with when and what), so the page can show who
# really uses each door and offer to add them before the list is narrowed. Each refused address
# is also counted per door (how many, first, last), so the Integrations page can warn when one
# kept being refused lately, and name who used that door before from another address (Oct 18:
# Home Assistant came back from a power cut at a new address and was refused for an hour, with
# only the log saying so).

import ipaddress
import logging
import socket
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlparse

from veil.errors import VeilError

log = logging.getLogger("router")

LOCAL = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
    "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10")]

LISTS = ("inbound_allowed", "admin_allowed", "outbound_allowed")


def parse(entries):
    networks = []
    for entry in entries or []:
        try:
            networks.append(ipaddress.ip_network(str(entry).strip(), strict=False))
        except ValueError as e:
            raise VeilError(f"'{entry}' isn't an address or range (like 192.168.1.50 or 192.168.1.0/24)") from e
    return networks


def _ip(address):
    try:
        ip = ipaddress.ip_address(address or "")
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


class Access:
    def __init__(self, security):
        self.refused = {k: deque(maxlen=20) for k in LISTS}
        self.seen = {k: {} for k in LISTS}            # address -> {time, what}
        self.counts = {}                              # (list, address, what) -> {n, first, last}
        self._last_log = {}
        self._dns = {}
        self.load(security)

    def load(self, security):
        security = security or {}
        self.entries = {k: [str(e) for e in (security.get(k) or [])] for k in LISTS}
        self.networks = {k: parse(v) for k, v in self.entries.items()}

    def allowed(self, which, address, what=""):
        ip = _ip(address)
        if ip is None:
            return False
        ok = any(ip in net for net in (self.networks[which] or LOCAL))
        if ok:
            self._seen(which, str(ip), what)
        return ok

    def _seen(self, which, address, what):
        seen = self.seen[which]
        seen[address] = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "what": what}
        if len(seen) > 30:
            oldest = min(seen, key=lambda a: seen[a]["time"])
            del seen[oldest]

    def note(self, which, address, what):
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.refused[which].appendleft({"address": address, "what": what, "time": when})
        c = self.counts.setdefault((which, address, what), {"n": 0, "first": time.time()})
        c["n"], c["last"] = c["n"] + 1, time.time()
        if len(self.counts) > 50:
            del self.counts[min(self.counts, key=lambda k: self.counts[k]["last"])]
        now = time.monotonic()
        key = (which, address)
        if now - self._last_log.get(key, 0) > 60:
            self._last_log[key] = now
            log.info("  ! refused (%s): %s %s", which.replace("_allowed", ""), address, what)

    # calls out

    def _resolve(self, host):
        hit = self._dns.get(host)
        if hit and time.monotonic() - hit[1] < 300:
            return hit[0]
        try:
            addrs = sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
        except OSError:
            addrs = []
        self._dns[host] = (addrs, time.monotonic())
        return addrs

    def check_outbound(self, url):
        """Raise VeilError if the router may not call this address."""
        host = urlparse(str(url)).hostname or ""
        addrs = [host] if _ip(host) else self._resolve(host)
        if addrs and all(self.allowed("outbound_allowed", a, str(url).split("?")[0]) for a in addrs):
            return
        self.note("outbound_allowed", host, str(url).split("?")[0])
        raise VeilError(f"Calls to {host} aren't permitted (security: outbound_allowed)", 403)

    def lately(self, minutes):
        """The refusals of the last `minutes`, one per list, address and door, newest first: how many,
        first and last (epoch seconds), and the address that last used the same door and was
        permitted (before: "it came from there before"), or None."""
        since = time.time() - float(minutes) * 60
        out = []
        for (which, address, what), c in self.counts.items():
            if c["last"] < since:
                continue
            before = next((a for a, v in sorted(self.seen[which].items(), key=lambda x: x[1]["time"], reverse=True)
                           if v.get("what") == what and a != address), None)
            out.append({"list": which, "address": address, "what": what, "n": c["n"], "first": c["first"],
                        "last": c["last"], "before": before})
        return sorted(out, key=lambda x: x["last"], reverse=True)

    def view(self):
        return {k: {"entries": self.entries[k], "local_network_only": not self.networks[k],
                    "recently_refused": list(self.refused[k]),
                "recently_allowed": sorted(({"address": a, **v} for a, v in self.seen[k].items()),
                                           key=lambda x: x["time"], reverse=True)} for k in LISTS}


ACCESS = Access({})


def outside(url):
    """Is this address on the internet (not the house's own network, loopback or Tailscale)?"""
    host = urlparse(str(url or "")).hostname or ""
    addrs = [host] if _ip(host) else ACCESS._resolve(host)
    ips = [_ip(a) for a in addrs if _ip(a)]
    return bool(ips) and not any(ip in net for ip in ips for net in LOCAL)


def client(timeout, verify=True):
    """The one way the router calls out: an httpx client whose every request is checked against
    security: outbound_allowed first (a refused address is a connection error, before anything is sent).
    Every call says who it is (router: user_agent): an outside app may refuse one that doesn't
    (Wikipedia answers 403 to httpx's own name)."""
    import httpx
    from veil import phases
    headers = {"User-Agent": user_agent()} if phases.on("dump5") and user_agent() else None
    return httpx.AsyncClient(timeout=timeout, verify=verify, event_hooks=outbound_hook(), headers=headers)


_UA = []


def user_agent():
    """The router's name on its calls out (settings: router: user_agent), read once."""
    if not _UA:
        from veil import config
        _UA.append(str(config.section(config.settings(), "router").get("user_agent") or "").strip())
    return _UA[0]


async def capped(c, method, url, most_kb, **kw):
    """One call out, its answer read at most most_kb (a huge or endless answer is refused as it comes,
    never held whole: inbound defense 3, dump16)."""
    import httpx
    most = int(float(most_kb or 0) * 1024)
    async with c.stream(method, url, **kw) as r:
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body += chunk
            if most and len(body) > most:
                raise VeilError(f"{urlparse(str(url)).hostname} answered more than {most_kb} KB: not read", 502)
        # read as it was decoded (gzip undone): its headers no longer describe an encoding or a length
        headers = [(k, v) for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
        return httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request)


def most_kb(key):
    """A size cap from settings, router: (app_answer_max_kb, spec_max_kb), read once."""
    if key not in _CAPS:
        from veil import config
        _CAPS[key] = float(config.section(config.settings(), "router").get(key) or 0)
    return _CAPS[key]


_CAPS = {}


def outbound_hook():
    """An httpx request hook that refuses calls to addresses not permitted."""
    async def guard(request):
        try:
            ACCESS.check_outbound(str(request.url))
        except VeilError as e:
            import httpx
            raise httpx.ConnectError(str(e), request=request)
    return {"request": [guard]}
