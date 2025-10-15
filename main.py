import asyncio
import aiohttp
import socket
from fastapi import FastAPI
from contextlib import asynccontextmanager

URLS = [
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
