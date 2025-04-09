import asyncio
import aiohttp
from fastapi import FastAPI
import uvicorn

app = FastAPI()

URLS = [
    "https://forward-n6az.onrender.com/",
    "https://newcodex-az1m.onrender.com/",
    "https://main-2tft.onrender.com/",
    "https://gemini-r0rz.onrender.com/",
    "https://newcodex-p0tx.onrender.com/",
    "https://previous-constance-alexpinaorg-7b7546a0.koyeb.app/",
    "https://stream-eliteflixmedia.koyeb.app/",
    "https://liquid-pooh-jahahagwksj-4d9ff8e1.koyeb.app/"
]

INTERVAL_SECONDS = 5

@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "ok"}

async def ping(session, url):
    try:
        async with session.get(url, timeout=5) as resp:
            print(f"Pinged {url} - Status: {resp.status}")
    except Exception as e:
        print(f"Failed to ping {url}: {e}")

async def ping_forever():
    async with aiohttp.ClientSession() as session:
        while True:
            tasks = [ping(session, url) for url in URLS]
            await asyncio.gather(*tasks)
            await asyncio.sleep(INTERVAL_SECONDS)

# Background task runner
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ping_forever())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
