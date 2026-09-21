"""Live host CPU / RAM metrics for Wagtail home gauges.

Prefers ``psutil`` when installed; falls back to Linux ``/proc`` so the
panel still works in minimal containers.
"""
from __future__ import annotations

import os
import time
from typing import Any


def _cpu_percent_proc(sample_seconds: float = 0.15) -> float | None:
    """Estimate CPU usage from /proc/stat over a short interval."""
    try:
        def read_idle_total():
            with open("/proc/stat", "r", encoding="utf-8") as f:
                line = f.readline()
            parts = [int(x) for x in line.split()[1:]]
            idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
            total = sum(parts)
            return idle, total

        idle1, total1 = read_idle_total()
        time.sleep(sample_seconds)
        idle2, total2 = read_idle_total()
        d_total = total2 - total1
        d_idle = idle2 - idle1
        if d_total <= 0:
            return 0.0
        return round(max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0)), 1)
    except Exception:
        return None


def _mem_from_proc() -> dict[str, Any] | None:
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                parts = val.strip().split()
                if not parts:
                    continue
                # values are in kB
                info[key] = int(parts[0]) * 1024
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable")
        if available is None:
            free = info.get("MemFree", 0)
            buffers = info.get("Buffers", 0)
            cached = info.get("Cached", 0)
            available = free + buffers + cached
        used = max(0, total - available) if total else 0
        percent = round((used / total) * 100.0, 1) if total else 0.0
        return {
            "total": total,
            "available": available,
            "used": used,
            "percent": percent,
        }
    except Exception:
        return None


def _fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def get_system_metrics() -> dict[str, Any]:
    """Return only the CPU/RAM data needed by the admin gauge.

    Internal implementation details (hostname, OS/proc source, library name)
    are intentionally omitted from the response.
    """
    out: dict[str, Any] = {
        "ok": True,
        "cpu_percent": None,
        "ram_percent": None,
        "ram_used": None,
        "ram_total": None,
        "ram_available": None,
        "ram_used_human": "—",
        "ram_total_human": "—",
        "ram_available_human": "—",
    }
    try:
        import psutil  # type: ignore

        out["cpu_percent"] = round(float(psutil.cpu_percent(interval=0.15)), 1)
        vm = psutil.virtual_memory()
        out["ram_percent"] = round(float(vm.percent), 1)
        out["ram_used"] = int(vm.used)
        out["ram_total"] = int(vm.total)
        out["ram_available"] = int(vm.available)
    except Exception:
        cpu = _cpu_percent_proc()
        mem = _mem_from_proc()
        out["cpu_percent"] = cpu
        if mem:
            out["ram_percent"] = mem["percent"]
            out["ram_used"] = mem["used"]
            out["ram_total"] = mem["total"]
            out["ram_available"] = mem["available"]

    out["ram_used_human"] = _fmt_bytes(out["ram_used"])
    out["ram_total_human"] = _fmt_bytes(out["ram_total"])
    out["ram_available_human"] = _fmt_bytes(out["ram_available"])
    if out["cpu_percent"] is None and out["ram_percent"] is None:
        out["ok"] = False
    return out
