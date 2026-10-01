"""Normalize browser/device metadata for authentication audit records.

Client-provided values are descriptive only. Server-observed IP and User-Agent
remain authoritative for audit and are never used as session credentials.
"""
from __future__ import annotations

import re
from typing import Any

from .models import Device

_ALLOWED_CLIENT_METADATA = {
    "locale": 64,
    "timezone": 128,
    "screen_width": 8,
    "screen_height": 8,
    "color_depth": 8,
    "device_memory": 16,
    "hardware_concurrency": 8,
    "touch_points": 8,
    "mobile": 8,
    "platform_hint": 64,
    "brands": 1000,
}

_WINDOWS_VERSIONS = {
    "10.0": "Windows 10/11",
    "6.4": "Windows 10/11",
    "6.3": "Windows 8.1",
    "6.2": "Windows 8",
    "6.1": "Windows 7",
}

def _clean(value: Any, limit: int = 256) -> str:
    return str(value or "").strip()[:limit]

def parse_user_agent(user_agent: str) -> dict[str, str]:
    ua = _clean(user_agent, 500)
    browser = ""
    browser_version = ""
    os_name = ""
    os_version = ""
    device_type = "desktop"
    device_model = ""

    patterns = [
        ("Edge", r"Edg(?:A|iOS)?/([\d.]+)"),
        ("Opera", r"OPR/([\d.]+)"),
        ("Samsung Internet", r"SamsungBrowser/([\d.]+)"),
        ("Firefox", r"(?:Firefox|FxiOS)/([\d.]+)"),
        ("Chrome", r"(?:Chrome|CriOS)/([\d.]+)"),
        ("Chromium", r"Chromium/([\d.]+)"),
        ("Yandex", r"YaBrowser/([\d.]+)"),
        ("Safari", r"Version/([\d.]+).*Safari/"),
    ]
    for name, pattern in patterns:
        match = re.search(pattern, ua, re.I)
        if match:
            browser = name
            browser_version = match.group(1)
            break
    if not browser and "Electron/" in ua:
        match = re.search(r"Electron/([\d.]+)", ua, re.I)
        browser = "Electron"
        browser_version = match.group(1) if match else ""
    elif not browser and ua:
        browser = "Browser"

    match = re.search(r"Windows NT/([\d.]+)", ua, re.I)
    if match:
        os_name = "Windows"
        os_version = match.group(1)
        device_type = "desktop"
        os_version = _WINDOWS_VERSIONS.get(os_version, os_version)
    else:
        match = re.search(r"Android[ /]([\d.]+)", ua, re.I)
        if match:
            os_name = "Android"
            os_version = match.group(1)
            device_type = "tablet" if "Mobile" not in ua else "mobile"
            model_match = re.search(r";\s*([^;()]+?)\s+Build/", ua, re.I)
            device_model = _clean(model_match.group(1), 120) if model_match else ""
        elif re.search(r"(?:iPhone|CPU iPhone OS)", ua, re.I):
            os_name = "iOS"
            version_match = re.search(r"(?:OS|iPhone OS)\s*([\d_]+)", ua, re.I)
            os_version = version_match.group(1).replace("_", ".") if version_match else ""
            device_type = "mobile"
            device_model = "iPhone"
        elif re.search(r"(?:iPad|CPU OS)", ua, re.I):
            os_name = "iPadOS"
            version_match = re.search(r"OS\s*([\d_]+)", ua, re.I)
            os_version = version_match.group(1).replace("_", ".") if version_match else ""
            device_type = "tablet"
            device_model = "iPad"
        elif re.search(r"CrOS", ua, re.I):
            os_name = "ChromeOS"
            match = re.search(r"CrOS\s+[^;]+\s+([\w.-]+)", ua, re.I)
            os_version = match.group(1) if match else ""
            device_type = "desktop"
        elif re.search(r"Mac OS X", ua, re.I):
            os_name = "macOS"
            match = re.search(r"Mac OS X\s*([\d_\.]+)", ua, re.I)
            os_version = match.group(1).replace("_", ".") if match else ""
        elif re.search(r"Linux", ua, re.I):
            os_name = "Linux"

    if "Mobile" in ua and device_type == "desktop":
        device_type = "mobile"
    elif "Tablet" in ua and device_type == "desktop":
        device_type = "tablet"

    return {
        "browser": browser,
        "browser_version": browser_version,
        "os": os_name,
        "os_version": os_version,
        "device_type": device_type,
        "device_model": device_model,
    }

def normalize_client_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, limit in _ALLOWED_CLIENT_METADATA.items():
        if key not in value:
            continue
        raw = value.get(key)
        if isinstance(raw, bool):
            result[key] = raw
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            result[key] = raw
        else:
            result[key] = _clean(raw, limit)
    return result

def collect_request_device_metadata(request, *, client_signature: str = "", client_metadata=None) -> dict[str, Any]:
    user_agent = _clean(request.META.get("HTTP_USER_AGENT", ""), 500) if request else ""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR", "") or "").strip() if request else ""
    ip = forwarded.split(",", 1)[0].strip() if forwarded else (request.META.get("REMOTE_ADDR") if request else None)
    parsed = parse_user_agent(user_agent)
    client = _clean(request.data.get("client"), 120) if request is not None else ""
    platform = _clean(request.data.get("platform"), 64) if request is not None else ""
    signature = _clean(client_signature, 128)
    return {
        "last_ip": ip or None,
        "user_agent": user_agent,
        "client": client or "Web browser",
        "platform": platform or parsed["os"],
        "browser": parsed["browser"],
        "browser_version": parsed["browser_version"],
        "os": parsed["os"],
        "os_version": parsed["os_version"],
        "device_type": parsed["device_type"],
        "device_model": parsed["device_model"],
        "client_signature": signature,
        "client_metadata": normalize_client_metadata(client_metadata),
        "parser_version": 1,
    }

def device_display_name(metadata: dict[str, Any]) -> str:
    browser = _clean(metadata.get("browser"), 64)
    os_name = _clean(metadata.get("os"), 64)
    model = _clean(metadata.get("device_model"), 96)
    if browser and model:
        return f"{browser} · {model}"
    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name or ("Mobile device" if metadata.get("device_type") == "mobile" else "Web browser")

def device_descriptor(device: Device, *, session=None) -> dict[str, Any]:
    base = dict(device.metadata or {})
    session_meta = dict((session.metadata if session is not None else {}) or {})
    merged = {**base, **session_meta}
    ua = _clean(session.user_agent if session is not None else device.user_agent, 500)
    parsed = parse_user_agent(ua)
    for key, value in parsed.items():
        if not merged.get(key):
            merged[key] = value
    ip = (session.last_ip if session is not None else device.last_ip)
    client_meta = merged.get("client_metadata")
    return {
        "id": str(device.public_id),
        "name": device.name or device_display_name(merged),
        "client": merged.get("client") or device.client or "Web browser",
        "platform": merged.get("platform") or device.platform or merged.get("os") or "",
        "browser": merged.get("browser", ""),
        "browser_version": merged.get("browser_version", ""),
        "os": merged.get("os", ""),
        "os_version": merged.get("os_version", ""),
        "device_type": merged.get("device_type", "desktop"),
        "device_model": merged.get("device_model", ""),
        "ip": ip,
        "last_ip": ip,
        "user_agent": ua,
        "client_signature": merged.get("client_signature", ""),
        "client_metadata": client_meta if isinstance(client_meta, dict) else {},
    }
