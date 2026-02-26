from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json
import html as ihtml
from typing import Any


def _normalize_ranks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cur = 0
    for item in items:
        raw = item.get("rank")
        if raw is None:
            cur += 1
        else:
            candidate = int(raw) + 1
            if candidate <= cur:
                candidate = cur + 1
            cur = candidate
        item["rank"] = cur
    return items


def find_domens(html: str) -> list[dict[str, Any]]:
    def _domain(u: str) -> str:
        if not u:
            return ""
        if "://" not in u:
            u = "http://" + u
        host = urlparse(u).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []

    for item in soup.select(".serp-item.serp-item_card"):
        rank_raw = item.get("data-cid")
        try:
            rank = int(str(rank_raw)) if rank_raw is not None else None
        except ValueError:
            rank = None

        a = item.find("a")
        if not a:
            continue

        vnl = a.get("data-vnl")
        if vnl:
            try:
                data = json.loads(ihtml.unescape(str(vnl)))
                url = data.get("noRedirectUrl") or data.get("url") or None
                is_ad = True
            except json.JSONDecodeError:
                url = a.get("href")
                is_ad = False
        else:
            url = a.get("href")
            is_ad = False

        if not url:
            continue
        url = str(url)

        out.append(
            {
                "rank": rank,
                "url": url,
                "domain": _domain(url),
                "is_ad": is_ad,
            }
        )

    return _normalize_ranks(out)
