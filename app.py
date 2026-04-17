import asyncio
import aiohttp
import socket
import os
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from bson import ObjectId
from typing import List, Optional
from datetime import datetime

class Settings(BaseSettings):
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name: str = "cron_jobs_db"

settings = Settings()
templates = Jinja2Templates(directory="templates")

# Existing URLS for non-regression
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
    "https://namechanged.onrender.com",
    "https://telegram-stremio-v9ur.onrender.com",
]

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

# New Scheduler Logic
scheduler = AsyncIOScheduler()
db_client = None
db = None

async def run_cron_job(url: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                print(f"[CRON] {url} - Status: {resp.status}")
                # Log execution to DB
                await db.logs.insert_one({
                    "url": url,
                    "status": resp.status,
                    "timestamp": datetime.utcnow()
                })
        except Exception as e:
            print(f"[CRON] {url} - Error: {e}")
            await db.logs.insert_one({
                "url": url,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow()
            })

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client, db
    # Legacy monitor
    legacy_task = asyncio.create_task(monitor_all())

    # DB & Scheduler
    db_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = db_client[settings.database_name]

    # Load jobs
    cursor = db.jobs.find()
    async for job in cursor:
        scheduler.add_job(
            run_cron_job,
            IntervalTrigger(minutes=job['interval']),
            id=str(job['_id']),
            args=[job['url']],
            replace_existing=True
        )

    scheduler.start()
    yield
    scheduler.shutdown()
    db_client.close()
    legacy_task.cancel()

app = FastAPI(lifespan=lifespan)

# API Models
class JobIn(BaseModel):
    url: str
    interval: int = Field(gt=0, description="Interval in minutes")

class JobUpdate(BaseModel):
    url: Optional[str] = None
    interval: Optional[int] = Field(None, gt=0)

# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/jobs")
async def get_jobs():
    cursor = db.jobs.find()
    jobs = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        jobs.append(doc)
    return jobs

@app.post("/api/jobs")
async def create_job(job: JobIn):
    job_dict = job.dict()
    result = await db.jobs.insert_one(job_dict)
    job_id = str(result.inserted_id)

    scheduler.add_job(
        run_cron_job,
        IntervalTrigger(minutes=job.interval),
        id=job_id,
        args=[job.url]
    )
    return {"id": job_id, **job_dict}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    result = await db.jobs.delete_one({"_id": ObjectId(job_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        scheduler.remove_job(job_id)
    except:
        pass
    return {"status": "deleted"}

@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: str, job_update: JobUpdate):
    existing = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = job_update.dict(exclude_unset=True)
    await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": update_data})

    # Update scheduler
    new_url = update_data.get("url", existing["url"])
    new_interval = update_data.get("interval", existing["interval"])

    try:
        scheduler.reschedule_job(
            job_id,
            trigger=IntervalTrigger(minutes=new_interval)
        )
        scheduler.modify_job(job_id, args=[new_url])
    except:
        # If job was not in scheduler for some reason, add it
        scheduler.add_job(
            run_cron_job,
            IntervalTrigger(minutes=new_interval),
            id=job_id,
            args=[new_url]
        )

    return {"status": "updated"}

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    cursor = db.logs.find().sort("timestamp", -1).limit(limit)
    logs = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        doc["timestamp"] = doc["timestamp"].isoformat()
        logs.append(doc)
    return logs

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
