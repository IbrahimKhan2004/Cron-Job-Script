"""
main.py — Legacy URL Monitor
Keeps legacy hardcoded URLs alive by pinging them periodically.
Run standalone: python main.py
"""

import asyncio
import aiohttp
import os

# ─── Legacy URLs ──────────────────────────────────────────────────────────────
URLS: list[str] = [] ✓ {url}  →  HTTP {resp.status}")
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
