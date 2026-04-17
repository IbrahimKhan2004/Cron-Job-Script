"""
app.py — CronPulse FastAPI Application
Manages dynamic cron jobs via MongoDB + APScheduler.
"""

import asyncio
import os
import ssl
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from status import create_status_router
from time_scheduler import (
    schedule_daily_job,
    unschedule_daily_job,
    get_next_run_time_for_daily,
    SUPPORTED_TIMEZONES,
    AVAILABLE_HOURS,
)

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

# ─── Auth Config ──────────────────────────────────────────────────────────────
VALID_USERS = {"5141337943", "6766653359"}
ADMIN_ID = "5141337943"

# ─── Globals ──────────────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler()
db_client: Optional[AsyncIOMotorClient] = None
db = None

# ─── Job runner ───────────────────────────────────────────────────────────────

async def run_cron_job(job_id: str, url: str) -> None:
    started_at = datetime.now(timezone.utc)
    log_entry: dict = {"job_id": job_id, "url": url, "timestamp": started_at}
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

async def run_daily_job(job_id: str, url: str) -> None:
    """Run a daily scheduled job (same as cron but tagged separately)."""
    started_at = datetime.now(timezone.utc)
    log_entry: dict = {"job_id": job_id, "url": url, "timestamp": started_at, "job_type": "daily"}
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
                print(f"[DAILY] ✓ {url}  →  HTTP {resp.status}")
    except asyncio.TimeoutError:
        log_entry.update({"status": "timeout", "success": False, "error": "Request timed out"})
        print(f"[DAILY] ✗ {url}  →  TIMEOUT")
    except Exception as exc:
        log_entry.update({"status": "error", "success": False, "error": str(exc)})
        print(f"[DAILY] ✗ {url}  →  ERROR: {exc}")
    finally:
        if db is not None:
            await db.logs.insert_one(log_entry)

# ─── SSL Checker ──────────────────────────────────────────────────────────────

async def check_ssl(hostname: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        loop = asyncio.get_event_loop()
        def _get_cert():
            with ctx.wrap_socket(socket.create_connection((hostname, 443), timeout=10), server_hostname=hostname) as conn:
                return conn.getpeercert()
        cert = await loop.run_in_executor(None, _get_cert)
        expire_str = cert.get("notAfter", "")
        expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)

        diff = expire_dt - datetime.now(timezone.utc)
        days_left = diff.days
        hours_left = diff.seconds // 3600
        minutes_left = (diff.seconds % 3600) // 60
        seconds_left = diff.seconds % 60

        return {
            "valid": True,
            "expires": expire_dt.isoformat(),
            "days_left": days_left,
            "hours_left": hours_left,
            "minutes_left": minutes_left,
            "seconds_left": seconds_left,
            "error": None
        }
    except ssl.SSLCertVerificationError as e:
        return {"valid": False, "expires": None, "days_left": None, "error": f"SSL verification failed: {e}"}
    except Exception as e:
        return {"valid": False, "expires": None, "days_left": None, "error": str(e)}

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client, db

    db_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = db_client[settings.database_name]

    await db.logs.create_index([("job_id", 1), ("timestamp", -1)])
    await db.logs.create_index([("timestamp", -1)])

    # Load interval-based jobs (existing)
    async for job in db.jobs.find({"job_type": {"$ne": "daily"}}):
        job_id = str(job["_id"])
        url = job.get("url")
        interval = job.get("interval_seconds")
        if url and interval:
            _schedule_job(job_id, url, interval)
        else:
            print(f"[APP] WARNING: Skipping job {job_id} due to missing fields")

    # Load daily jobs (new)
    async for job in db.jobs.find({"job_type": "daily"}):
        job_id = str(job["_id"])
        url = job.get("url")
        hour = job.get("hour")
        tz = job.get("timezone", "UTC")
        if url and hour is not None:
            _schedule_daily_job_wrapper(job_id, url, hour, tz)
        else:
            print(f"[APP] WARNING: Skipping daily job {job_id} due to missing fields")

    scheduler.start()
    print(f"[APP] Scheduler started with {len(scheduler.get_jobs())} job(s).")
    yield
    scheduler.shutdown(wait=False)
    db_client.close()
    print("[APP] Shutdown complete.")

# ─── Scheduler helpers ────────────────────────────────────────────────────────

def _schedule_job(job_id: str, url: str, interval_seconds: int) -> None:
    scheduler.add_job(run_cron_job, IntervalTrigger(seconds=interval_seconds),
                      id=job_id, args=[job_id, url], replace_existing=True)

def _unschedule_job(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

def _schedule_daily_job_wrapper(job_id: str, url: str, hour: int, tz_name: str) -> None:
    """Wrapper to schedule daily job using time_scheduler module."""
    schedule_daily_job(scheduler, job_id, run_daily_job, hour, tz_name, [job_id, url])

def _unschedule_daily_job_wrapper(job_id: str) -> None:
    """Wrapper to unschedule daily job."""
    unschedule_daily_job(scheduler, job_id)

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="CronPulse", version="3.0.0", lifespan=lifespan)

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def get_current_user(session_id: Optional[str] = Cookie(default=None)) -> Optional[str]:
    return session_id if session_id in VALID_USERS else None

def require_user(session_id: Optional[str] = Cookie(default=None)) -> str:
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ─── Pydantic models ──────────────────────────────────────────────────────────

class JobIn(BaseModel):
    url: str = Field(..., description="Target URL to ping")
    name: str = Field(..., min_length=1, max_length=80)
    interval_seconds: int = Field(..., gt=0)

class JobUpdate(BaseModel):
    url: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    interval_seconds: Optional[int] = Field(None, gt=0)

class DailyJobIn(BaseModel):
    """Create a daily job at specific hour in specific timezone."""
    url: str = Field(..., description="Target URL to ping")
    name: str = Field(..., min_length=1, max_length=80)
    hour: int = Field(..., ge=0, le=23, description="0-23, hour of day")
    timezone: str = Field(..., description="'UTC' or 'IST'")

class DailyJobUpdate(BaseModel):
    """Update a daily job."""
    url: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    hour: Optional[int] = Field(None, ge=0, le=23)
    timezone: Optional[str] = None

class LoginIn(BaseModel):
    user_id: str

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@app.post("/api/auth/login")
async def login(body: LoginIn, response: Response):
    uid = body.user_id.strip()
    if uid not in VALID_USERS:
        raise HTTPException(status_code=403, detail="Invalid User ID")
    response.set_cookie("session_id", uid, httponly=True, samesite="lax", max_age=86400 * 30)
    return {"ok": True, "is_admin": uid == ADMIN_ID}

@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("session_id")
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, response: Response, session_id: Optional[str] = Cookie(default=None)):
    if not get_current_user(session_id):
        return RedirectResponse("/login")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
def health_check():
    return {"status": "ok", "jobs": len(scheduler.get_jobs())}

@app.get("/api/ssl")
async def check_ssl_endpoint(hostname: str, session_id: Optional[str] = Cookie(default=None)):
    require_user(session_id)
    hostname = hostname.replace("https://", "").replace("http://", "").split("/")[0]
    return await check_ssl(hostname)

@app.get("/api/me")
async def get_me(session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    return {"user_id": uid, "is_admin": uid == ADMIN_ID}

# Jobs CRUD ────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def get_jobs(session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    query = {} if uid == ADMIN_ID else {"owner_id": uid}
    jobs = []
    async for doc in db.jobs.find(query):
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
            "owner_id": doc.get("owner_id", ADMIN_ID),
            "is_legacy": doc.get("is_legacy", False),
        })
    return jobs

@app.post("/api/jobs", status_code=201)
async def create_job(job: JobIn, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    now = datetime.now(timezone.utc)
    job_dict = {"name": job.name, "url": job.url, "interval_seconds": job.interval_seconds,
                "created_at": now, "owner_id": uid}
    result = await db.jobs.insert_one(job_dict)
    job_id = str(result.inserted_id)
    _schedule_job(job_id, job.url, job.interval_seconds)
    job_dict.pop("_id", None)
    return {"id": job_id, **job_dict, "created_at": now.isoformat()}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    doc = await db.jobs.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if uid != ADMIN_ID and doc.get("owner_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.jobs.delete_one({"_id": obj_id})
    await db.logs.delete_many({"job_id": job_id})
    _unschedule_job(job_id)
    return {"status": "deleted"}

@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: str, job_update: JobUpdate, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    existing = await db.jobs.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    if uid != ADMIN_ID and existing.get("owner_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    update_data = job_update.model_dump(exclude_unset=True)
    if update_data:
        await db.jobs.update_one({"_id": obj_id}, {"$set": update_data})
    new_url = update_data.get("url", existing.get("url", ""))
    new_interval = update_data.get("interval_seconds", existing.get("interval_seconds", 0))
    if new_url and new_interval > 0:
        _schedule_job(job_id, new_url, new_interval)
    return {"status": "updated"}

# ─── Daily Jobs (Timezone-aware) ──────────────────────────────────────────────

@app.post("/api/daily-jobs", status_code=201)
async def create_daily_job(job: DailyJobIn, session_id: Optional[str] = Cookie(default=None)):
    """Create a daily job at specific hour in specific timezone."""
    uid = require_user(session_id)
    
    # Validate timezone
    if job.timezone not in SUPPORTED_TIMEZONES:
        raise HTTPException(status_code=400, detail=f"Unsupported timezone. Use: {list(SUPPORTED_TIMEZONES.keys())}")
    
    now = datetime.now(timezone.utc)
    job_dict = {
        "name": job.name,
        "url": job.url,
        "hour": job.hour,
        "timezone": job.timezone,
        "created_at": now,
        "owner_id": uid,
        "job_type": "daily",
    }
    result = await db.jobs.insert_one(job_dict)
    job_id = str(result.inserted_id)
    
    # Schedule the daily job
    _schedule_daily_job_wrapper(job_id, job.url, job.hour, job.timezone)
    
    return {"id": job_id, **job_dict, "created_at": now.isoformat()}

@app.get("/api/daily-jobs")
async def get_daily_jobs(session_id: Optional[str] = Cookie(default=None)):
    """Get all daily jobs for user."""
    uid = require_user(session_id)
    query = {"job_type": "daily"}
    if uid != ADMIN_ID:
        query["owner_id"] = uid
    
    jobs = []
    async for doc in db.jobs.find(query):
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
            "hour": doc.get("hour"),
            "timezone": doc.get("timezone", "UTC"),
            "created_at": created_at,
            "next_run": next_run,
            "owner_id": doc.get("owner_id"),
        })
    return jobs

@app.patch("/api/daily-jobs/{job_id}")
async def update_daily_job(job_id: str, job_update: DailyJobUpdate, session_id: Optional[str] = Cookie(default=None)):
    """Update a daily job."""
    uid = require_user(session_id)
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    existing = await db.jobs.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    if uid != ADMIN_ID and existing.get("owner_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    if existing.get("job_type") != "daily":
        raise HTTPException(status_code=400, detail="This is not a daily job")
    
    update_data = job_update.model_dump(exclude_unset=True)
    
    # Validate timezone if provided
    if "timezone" in update_data and update_data["timezone"] not in SUPPORTED_TIMEZONES:
        raise HTTPException(status_code=400, detail=f"Unsupported timezone. Use: {list(SUPPORTED_TIMEZONES.keys())}")
    
    if update_data:
        await db.jobs.update_one({"_id": obj_id}, {"$set": update_data})
    
    new_url = update_data.get("url", existing.get("url", ""))
    new_hour = update_data.get("hour", existing.get("hour"))
    new_tz = update_data.get("timezone", existing.get("timezone", "UTC"))
    
    if new_url and new_hour is not None:
        _schedule_daily_job_wrapper(job_id, new_url, new_hour, new_tz)
    
    return {"status": "updated"}

@app.delete("/api/daily-jobs/{job_id}")
async def delete_daily_job(job_id: str, session_id: Optional[str] = Cookie(default=None)):
    """Delete a daily job."""
    uid = require_user(session_id)
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    doc = await db.jobs.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if uid != ADMIN_ID and doc.get("owner_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    if doc.get("job_type") != "daily":
        raise HTTPException(status_code=400, detail="This is not a daily job")
    
    await db.jobs.delete_one({"_id": obj_id})
    await db.logs.delete_many({"job_id": job_id})
    _unschedule_daily_job_wrapper(job_id)
    
    return {"status": "deleted"}

@app.get("/api/available-hours")
async def get_available_hours(session_id: Optional[str] = Cookie(default=None)):
    """Get list of available hours (0-23) for daily jobs."""
    require_user(session_id)
    return {"hours": AVAILABLE_HOURS}

@app.get("/api/available-timezones")
async def get_available_timezones(session_id: Optional[str] = Cookie(default=None)):
    """Get list of supported timezones."""
    require_user(session_id)
    return {"timezones": list(SUPPORTED_TIMEZONES.keys())}

# Logs ────────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_all_logs(limit: int = 100, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    if uid == ADMIN_ID:
        cursor = db.logs.find().sort("timestamp", -1).limit(limit)
    else:
        owned = [str(doc["_id"]) async for doc in db.jobs.find({"owner_id": uid})]
        cursor = db.logs.find({"job_id": {"$in": owned}}).sort("timestamp", -1).limit(limit)
    logs = []
    async for doc in cursor:
        logs.append(_serialize_log(doc))
    return logs

@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, limit: int = 50, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    if uid != ADMIN_ID:
        try:
            doc = await db.jobs.find_one({"_id": ObjectId(job_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID")
        if not doc or doc.get("owner_id") != uid:
            raise HTTPException(status_code=403, detail="Access denied")
    logs = []
    async for doc in db.logs.find({"job_id": job_id}).sort("timestamp", -1).limit(limit):
        logs.append(_serialize_log(doc))
    return logs

@app.delete("/api/jobs/{job_id}/logs")
async def clear_job_logs(job_id: str, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    if uid != ADMIN_ID:
        try:
            doc = await db.jobs.find_one({"_id": ObjectId(job_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID")
        if not doc or doc.get("owner_id") != uid:
            raise HTTPException(status_code=403, detail="Access denied")
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

def _get_db():
    return db

app.include_router(create_status_router(_get_db, require_user, ADMIN_ID, templates, _serialize_log))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=settings.port, reload=False)
