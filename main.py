import asyncio
import aiohttp
import socket
from fastapi import FastAPI
from contextlib import asynccontextmanager

URLS = [
    "https://forward-n6az.onrender.com/",
    "https://newcodex-az1m.onrender.com/",
    "https://main-2tft.onrender.com/",
    "https://gemini-r0rz.onrender.com/",
    "https://newcodex-p0tx.onrender.com/",
    "https://previous-constance-alexpinaorg-7b7546a0.koyeb.app/",
    "https://stream-eliteflixmedia.koyeb.app/",
    "https://regional-caryl-jahahagwksj-90803a67.koyeb.app/",
    "https://residential-tiffany-streamppl-ca1d6f39.koyeb.app/"
]

# Extract hostnames for port monitoring (assuming port 8080)
PORTS = [(url.split("//")[1].strip("/"), 8080) for url in URLS]

INTERVAL_SECONDS = 5

async def ping_http(session, url):
    try:
        async with session.get(url, timeout=5) as resp:
            print(f"[HTTP] {url} - Status: {resp.status}")
    except Exception as e:
        print(f"[HTTP] {url} - Error: {e}")

async def ping_port(host, port):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        print(f"[PORT] {host}:{port} is OPEN")
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        print(f"[PORT] {host}:{port} is DOWN - {e}")

async def monitor_all():
    async with aiohttp.ClientSession() as session:
        while True:
            http_tasks = [ping_http(session, url) for url in URLS]
            port_tasks = [ping_port(host, port) for host, port in PORTS]
            await asyncio.gather(*http_tasks, *port_tasks)
            await asyncio.sleep(INTERVAL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(monitor_all())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "ok"}
