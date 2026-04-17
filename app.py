"""
app.py — CronPulse FastAPI Application
Manages dynamic cron jobs via MongoDB + APScheduler.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# ─── Settings ─────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name: str = "cron_jobs_db"
    port: int = int(os.getenv("PORT", "8080"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
templates = Jinja2Templates(directory="templates")

# ─── Globals ──────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()
db_client: Optional[AsyncIOMotorClient] = None
db = None

# ─── Job runner ───────────────────────────────────────────────────────────────

async def run_cron_job(job_id: str, url: str) -> None:
    """Execute a single cron job: GET the URL, log result to DB."""
    started_at = datetime.now(timezone.utc)
    log_entry: dict = {
        "job_id": job_id,
        "url": url,
        "timestamp": started_at,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                body_preview = (await resp.text())[:200]
                log_entry.update({
                    "status": resp.status,
                    "success": 200 <= resp.status < 400,
                    "response_preview": body_preview,
                    "error": None,
                })
                print(f"[CRON] ✓ {url}  →  HTTP {resp.status}")
    except asyncio.TimeoutError:
        log_entry.update({"status": "timeout", "success": False, "error": "Request timed out"})
        print(f"[CRON] ✗ {url}  →  TIMEOUT")
    except Exception as exc:
        log_entry.update({"status": "error", "success": False, "error": str(exc)})
        print(f"[CRON] ✗ {url}  →  ERROR: {exc}")
    finally:
        if db is not None:
            await db.logs.insert_one(log_entry)

# ─── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client, db

    db_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = db_client[settings.database_name]

    # Create indexes for fast queries
    await db.logs.create_index([("job_id", 1), ("timestamp", -1)])
    await db.logs.create_index([("timestamp", -1)])

    # One-time migration of legacy URLs
    legacy_urls = [
        "https://unpleasant-tapir-alexpinaorg-ee539153.koyeb.app/", "https://bot-pl0g.onrender.com/",
        "https://brilliant-celestyn-mustafaorgka-608d1ba4.koyeb.app/", "https://fsb-latest-yymc.onrender.com/",
        "https://gemini-5re4.onrender.com/", "https://late-alameda-streamppl-f38f75e1.koyeb.app/",
        "https://main-diup.onrender.com/", "https://marxist-theodosia-ironblood-b363735f.koyeb.app/",
        "https://mltb-x2pj.onrender.com/", "https://neutral-ralina-alwuds-cc44c37a.koyeb.app/",
        "https://ssr-fuz6.onrender.com", "https://unaware-joanne-eliteflixmedia-976ac949.koyeb.app/",
        "https://worthwhile-gaynor-nternetke-5a83f931.koyeb.app/", "https://cronjob-sxmj.onrender.com",
        "https://native-darryl-jahahagwksj-902a75ed.koyeb.app/", "https://prerss.onrender.com/skymovieshd/latest-updated-movies",
        "https://gofile-spht.onrender.com", "https://gofile-g1dl.onrender.com", "https://regex-k9as.onrender.com",
        "https://namechanged.onrender.com", "https://telegram-stremio-v9ur.onrender.com"
    ]

    print(f"[APP] Checking migration for {len(legacy_urls)} legacy URLs...")
    for url in legacy_urls:
        exists = await db.jobs.find_one({"url": url})
        if not exists:
            job_dict = {
                "name": f"Legacy Sync: {url[:30]}...",
                "url": url,
                "interval_seconds": 300,
                "created_at": datetime.now(timezone.utc),
                "is_legacy": True
            }
            await db.jobs.insert_one(job_dict)
            print(f"[APP] Migrated legacy URL: {url}")

    # Restore persisted jobs into scheduler
    async for job in db.jobs.find():
        job_id = str(job["_id"])
        url = job.get("url")
        interval = job.get("interval_seconds")
        if url and interval:
            _schedule_job(job_id, url, interval)
        else:
            print(f"[APP] WARNING: Skipping job {job_id} due to missing fields")

    scheduler.start()
    print(f"[APP] Scheduler started with {len(scheduler.get_jobs())} job(s).")

    yield

    scheduler.shutdown(wait=False)
    db_client.close()
    print("[APP] Shutdown complete.")

# ─── Scheduler helpers ────────────────────────────────────────────────────────

def _schedule_job(job_id: str, url: str, interval_seconds: int) -> None:
    """Add or replace a job in APScheduler."""
    scheduler.add_job(
        run_cron_job,
        IntervalTrigger(seconds=interval_seconds),
        id=job_id,
        args=[job_id, url],
        replace_existing=True,
    )

def _unschedule_job(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="CronPulse",
    description="Professional cron job manager with per-job execution logs.",
    version="2.0.0",
    lifespan=lifespan,
)

# ─── Pydantic models ──────────────────────────────────────────────────────────

class JobIn(BaseModel):
    url: str = Field(..., description="Target URL to ping")
    name: str = Field(..., min_length=1, max_length=80, description="Human-readable job name")
    interval_seconds: int = Field(..., gt=0, description="Interval in seconds (min 1)")

class JobUpdate(BaseModel):
    url: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    interval_seconds: Optional[int] = Field(None, gt=0)

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
def health_check():
    return {"status": "ok", "jobs": len(scheduler.get_jobs())}

# Jobs CRUD ────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def get_jobs():
    jobs = []
    async for doc in db.jobs.find():
        job_id = str(doc["_id"])
        sched_job = scheduler.get_job(job_id)
        next_run = sched_job.next_run_time.isoformat() if sched_job and sched_job.next_run_time else None

        created_at = doc.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        jobs.append({
            "id": job_id,
            "name": doc.get("name", ""),
            "url": doc.get("url", ""),
            "interval_seconds": doc.get("interval_seconds", 0),
            "created_at": created_at,
            "next_run": next_run,
        })
    return jobs

@app.post("/api/jobs", status_code=201)
async def create_job(job: JobIn):
    now = datetime.now(timezone.utc)
    job_dict = {
        "name": job.name,
        "url": job.url,
        "interval_seconds": job.interval_seconds,
        "created_at": now,
    }
    result = await db.jobs.insert_one(job_dict)
    job_id = str(result.inserted_id)
    _schedule_job(job_id, job.url, job.interval_seconds)
    return {"id": job_id, **job_dict, "created_at": now.isoformat()}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    try:
        obj_id = ObjectId(job_id)
    except Exception as e:
        print(f"[API] Invalid ID format: {job_id} Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    result = await db.jobs.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.logs.delete_many({"job_id": job_id})
    _unschedule_job(job_id)
    return {"status": "deleted"}

@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: str, job_update: JobUpdate):
    try:
        obj_id = ObjectId(job_id)
    except Exception as e:
        print(f"[API] Invalid ID format: {job_id} Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    existing = await db.jobs.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = job_update.model_dump(exclude_unset=True)
    if update_data:
        await db.jobs.update_one({"_id": obj_id}, {"$set": update_data})

    new_url = update_data.get("url", existing.get("url", ""))
    new_interval = update_data.get("interval_seconds", existing.get("interval_seconds", 0))
    if new_url and new_interval > 0:
        _schedule_job(job_id, new_url, new_interval)
    return {"status": "updated"}

# Logs ────────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_all_logs(limit: int = 100):
    logs = []
    async for doc in db.logs.find().sort("timestamp", -1).limit(limit):
        logs.append(_serialize_log(doc))
    return logs

@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, limit: int = 50):
    logs = []
    async for doc in db.logs.find({"job_id": job_id}).sort("timestamp", -1).limit(limit):
        logs.append(_serialize_log(doc))
    return logs

@app.delete("/api/jobs/{job_id}/logs")
async def clear_job_logs(job_id: str):
    result = await db.logs.delete_many({"job_id": job_id})
    return {"deleted": result.deleted_count}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_log(doc: dict) -> dict:
    timestamp = doc.get("timestamp")
    if hasattr(timestamp, "isoformat"):
        timestamp = timestamp.isoformat()

    return {
        "id": str(doc["_id"]),
        "job_id": doc.get("job_id", ""),
        "url": doc.get("url", ""),
        "status": doc.get("status"),
        "success": doc.get("success", False),
        "error": doc.get("error"),
        "response_preview": doc.get("response_preview", ""),
        "timestamp": timestamp,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=settings.port, reload=False)
