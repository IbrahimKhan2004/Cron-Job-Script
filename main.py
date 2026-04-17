"""
main.py — Legacy URL Monitor
Keeps legacy hardcoded URLs alive by pinging them periodically.
Run standalone: python main.py
"""

import asyncio
import aiohttp
import os

# ─── Legacy URLs ──────────────────────────────────────────────────────────────
URLS: list[str] = [
    "https://unpleasant-tapir-alexpinaorg-ee539153.koyeb.app/",
    "https://bot-pl0g.onrender.com/",
    "https://brilliant-celestyn-mustafaorgka-608d1ba4.koyeb.app/",
    "https://fsb-latest-yymc.onrender.com/",
    "https://gemini-5re4.onrender.com/",
    "https://late-alameda-streamppl-f38f75e1.koyeb.app/",
    "https://main-diup.onrender.com/",
    "https://marxist-theodosia-ironblood-b363735f.koyeb.app/",
    "https://mltb-x2pj.onrender.com/",
    "https://neutral-ralina-alwuds-cc44c37a.koyeb.app/",
    "https://ssr-fuz6.onrender.com",
    "https://unaware-joanne-eliteflixmedia-976ac949.koyeb.app/",
    "https://worthwhile-gaynor-nternetke-5a83f931.koyeb.app/",
    "https://cronjob-sxmj.onrender.com",
    "https://native-darryl-jahahagwksj-902a75ed.koyeb.app/",
    "https://prerss.onrender.com/skymovieshd/latest-updated-movies",
    "https://gofile-spht.onrender.com",
    "https://gofile-g1dl.onrender.com",
    "https://regex-k9as.onrender.com",
    "https://namechanged.onrender.com",
    "https://telegram-stremio-v9ur.onrender.com",
]

PING_INTERVAL_SECONDS: int = int(os.getenv("LEGACY_PING_INTERVAL", "300"))  # default 5 min


# ─── Core ping functions ───────────────────────────────────────────────────────

async def ping_url(session: aiohttp.ClientSession, url: str) -> None:
    """Send a GET request to a URL and log the result."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            print(f"[LEGACY] ✓ {url}  →  HTTP {resp.status}")
    except asyncio.TimeoutError:
        print(f"[LEGACY] ✗ {url}  →  TIMEOUT")
    except Exception as exc:
        print(f"[LEGACY] ✗ {url}  →  ERROR: {exc}")


async def monitor_loop() -> None:
    """Continuously ping all legacy URLs at a fixed interval."""
    print(f"[LEGACY] Starting monitor — {len(URLS)} URLs, interval={PING_INTERVAL_SECONDS}s")
    connector = aiohttp.TCPConnector(limit=40)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            tasks = [ping_url(session, url) for url in URLS]
            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"[LEGACY] Cycle complete. Next in {PING_INTERVAL_SECONDS}s.")
            await asyncio.sleep(PING_INTERVAL_SECONDS)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(monitor_loop())
    except KeyboardInterrupt:
        print("\n[LEGACY] Monitor stopped.")
