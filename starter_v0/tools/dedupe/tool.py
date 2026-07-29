from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from tools._shared import err, fold_text

VALID_KEYS = {"url", "title", "both"}


def _norm_url(url: str) -> str:
    """Chuẩn hoá URL trước khi so trùng.

    Bỏ query string / fragment, bỏ `www.`, bỏ `/` cuối, hạ chữ thường host+path.
    Nhờ vậy `https://X.com/a/` và `https://x.com/a?utm_source=1` được coi là một.
    """
    cleaned = (url or "").split("?")[0].split("#")[0].strip().rstrip("/")
    if not cleaned:
        return ""
    parsed = urlparse(cleaned if "//" in cleaned else f"//{cleaned}")
    host = parsed.netloc.replace("www.", "").lower()
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}" if host else cleaned.lower()


def _fingerprint(item: dict[str, Any], key: str) -> tuple[Any, ...]:
    url = _norm_url(item.get("url") or "")
    # fold_text bỏ dấu tiếng Việt + hạ chữ thường, nên "Tin AI" == "tin ai".
    title = fold_text((item.get("title") or "").strip())
    if key == "title":
        return ("title", title)
    if key == "both":
        return ("both", url, title)
    # Mặc định so theo URL; item không có URL (ví dụ tweet thiếu id) thì lấy title thay.
    return ("url", url or title)


def dedupe_items(
    items: list[dict[str, Any]] | None = None,
    key: str = "url",
    max_items: int = 20,
) -> dict[str, Any]:
    try:
        source = items or []
        if not isinstance(source, list):
            raise TypeError(f"items must be a list, got {type(source).__name__}")
        if key not in VALID_KEYS:
            raise ValueError(f"key must be one of {sorted(VALID_KEYS)}, got {key!r}")

        limit = int(max_items or 20)
        seen: set[tuple[Any, ...]] = set()
        kept: list[dict[str, Any]] = []
        duplicates = 0

        for item in source:
            if not isinstance(item, dict):
                continue
            fingerprint = _fingerprint(item, key)
            if fingerprint in seen:
                duplicates += 1
                continue
            seen.add(fingerprint)
            kept.append(item)
            if len(kept) >= limit:
                break

        return {
            "tool": "dedupe_items",
            "key": key,
            "items": kept,
            "input_count": len(source),
            "kept_count": len(kept),
            "removed_count": duplicates,
        }
    except Exception as exc:
        return err("dedupe_items", exc)
