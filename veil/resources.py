# veil/resources.py - what the router costs to run: CPU and memory, the way Oread measures itself.
#
# Every stats: sample_seconds the router notes its own CPU time and memory (two reads from the
# kernel; nothing else). Each note is folded into its hour in veil.db (the resources table), so
# averages and peaks cover the last hour, day, week and month and survive restarts; hours older
# than stats: keep_days are dropped. CPU is shown as a share of one core: 150% means one and a
# half cores busy. CPU per minute is exact (CPU time used over the whole minute, not a snapshot).
#
# Each request also records the CPU time the router used while answering it (cpu_ms in the
# activity log): the process's CPU time at the end minus at the start. Two requests at once
# would share it; in a house they rarely overlap. The app's own CPU (the weather brain,
# Donetick) is in its own container and isn't counted here. Each request also notes how busy the
# whole machine was (load: the last minute's load over its cores), so Stats can tell a busy
# machine from slow code.

import asyncio
import logging
import os
import resource
import time
from collections import deque

log = logging.getLogger("router")
_PAGE = os.sysconf("SC_PAGE_SIZE")
START = time.time()


def cpu_seconds():
    """CPU time used by the whole router process so far (all threads, user and system)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def rss_mb():
    """The router's memory right now."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * _PAGE / 2**20
    except OSError:
        return 0.0


def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def machine_load():
    """How busy the whole machine is right now (myserver, not just the router): the last minute's
    load as a share of its cores (100% = every core busy), or None."""
    try:
        return round(os.getloadavg()[0] / (os.cpu_count() or 1) * 100, 1)
    except (OSError, AttributeError):
        return None


def cores():
    """Cores the router may use (the container's limit when it has one)."""
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max":
            return round(int(quota) / int(period), 2)
    except (OSError, ValueError):
        pass
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


class Sampler:
    """Notes CPU and memory every `seconds`, into `store` (Activity.note_resources)."""

    def __init__(self, store, seconds=60, keep_days=30):
        self.store = store
        self.seconds = max(5, float(seconds))
        self.keep_days = float(keep_days)
        self.minutes = deque(maxlen=max(1, int(3600 / self.seconds)))   # the last hour, note by note
        self._last = (time.time(), cpu_seconds())

    def sample(self):
        now, cpu = time.time(), cpu_seconds()
        (t0, c0), self._last = self._last, (now, cpu)
        if now <= t0:
            return None
        percent = 100 * (cpu - c0) / (now - t0)
        mem = rss_mb()
        self.minutes.append((now, percent, mem))
        if self.store:
            try:
                self.store.note_resources(now, percent, mem, self.keep_days)
            except Exception as e:
                log.info("  ! couldn't note CPU and memory: %s", e)
        return percent, mem

    async def run(self):
        while True:
            await asyncio.sleep(self.seconds)
            self.sample()

    def now(self):
        """The last few minutes and the last hour, from the notes in memory."""
        recent = [p for t, p, _ in self.minutes if t > time.time() - 300]
        out = {"cores": cores(), "memory_mb": round(rss_mb()), "memory_peak_mb": round(peak_mb()),
               "running_hours": round((time.time() - START) / 3600, 2),
               "cpu_since_start": round(100 * cpu_seconds() / max(time.time() - START, 1), 1)}
        if recent:
            out["cpu_last_5_minutes"] = round(sum(recent) / len(recent), 1)
        return out
