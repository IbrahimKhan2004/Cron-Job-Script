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
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from status import create_status_router

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

# ─── Timezones ────────────────────────────────────────────────────────────────
SUPPORTED_TIMEZONES = {"UTC": "UTC", "IST": "Asia/Kolkata"}

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

    async for job in db.jobs.find():
        job_id = str(job["_id"])
        url = job.get("url")
        interval_seconds = job.get("interval_seconds")
        hour = job.get("hour")
        minute = job.get("minute")
        second = job.get("second")
        timezone = job.get("timezone")
        day_of_week = job.get("day_of_week")
        
        # Schedule based on what fields are present
        if url:
            _schedule_job_unified(job_id, url, interval_seconds, hour, minute, second, timezone, day_of_week)
        else:
            print(f"[APP] WARNING: Skipping job {job_id} due to missing URL")

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

def _schedule_job_unified(job_id: str, url: str, interval_seconds: Optional[int], 
                          hour: Optional[int], minute: Optional[int], second: Optional[int], 
                          timezone: Optional[str], day_of_week: Optional[str] = None) -> None:
    """Schedule job as either interval-based or time-based, based on what's provided."""
    if interval_seconds and interval_seconds > 0:
        # Interval-based: use existing logic
        _schedule_job(job_id, url, interval_seconds)
    elif hour is not None and timezone and timezone in SUPPORTED_TIMEZONES:
        # Time-based: daily at specific time in specific timezone
        tz = pytz.timezone(SUPPORTED_TIMEZONES[timezone])
        m = minute if minute is not None else 0
        s = second if second is not None else 0
        trigger = CronTrigger(hour=hour, minute=m, second=s, timezone=tz,
                              day_of_week=day_of_week if day_of_week else None)
        scheduler.add_job(run_cron_job, trigger, id=job_id, args=[job_id, url], replace_existing=True)
    else:
        print(f"[APP] WARNING: Job {job_id} has invalid schedule config")

def _unschedule_job(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

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
    # Interval-based: interval_seconds (e.g., 300 for every 5 min)
    interval_seconds: Optional[int] = Field(None, gt=0)
    # Time-based: hour (0-23) + minute (0-59) + second (0-59) + timezone
    hour: Optional[int] = Field(None, ge=0, le=23, description="0-23 for daily at specific time")
    minute: Optional[int] = Field(None, ge=0, le=59, description="0-59")
    second: Optional[int] = Field(None, ge=0, le=59, description="0-59")
    timezone: Optional[str] = Field(None, description="'UTC' or 'IST' for time-based jobs")
    # Optional day-of-week filter (e.g. "mon,wed,fri" or None = every day)
    day_of_week: Optional[str] = Field(None, description="Comma-separated APScheduler day names, e.g. 'mon,wed,fri'. None = every day.")

class JobUpdate(BaseModel):
    url: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    interval_seconds: Optional[int] = Field(None, gt=0)
    hour: Optional[int] = Field(None, ge=0, le=23)
    minute: Optional[int] = Field(None, ge=0, le=59)
    second: Optional[int] = Field(None, ge=0, le=59)
    timezone: Optional[str] = None
    day_of_week: Optional[str] = None

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
            "hour": doc.get("hour"),
            "minute": doc.get("minute"),
            "second": doc.get("second"),
            "timezone": doc.get("timezone"),
            "day_of_week": doc.get("day_of_week"),
        })
    return jobs

@app.post("/api/jobs", status_code=201)
async def create_job(job: JobIn, session_id: Optional[str] = Cookie(default=None)):
    uid = require_user(session_id)
    
    # Validation: must have EITHER interval_seconds OR (hour + timezone)
    has_interval = job.interval_seconds and job.interval_seconds > 0
    has_time = job.hour is not None and job.timezone
    
    if not (has_interval or has_time):
        raise HTTPException(status_code=400, 
                          detail="Provide either interval_seconds OR (hour + timezone)")
    
    if has_time and job.timezone not in SUPPORTED_TIMEZONES:
        raise HTTPException(status_code=400, 
                          detail=f"Unsupported timezone. Use: {list(SUPPORTED_TIMEZONES.keys())}")
    
    # If both provided, reject (user must choose one)
    if has_interval and has_time:
        raise HTTPException(status_code=400, 
                          detail="Provide EITHER interval_seconds OR (hour + timezone), not both")
    
    now = datetime.now(timezone.utc)
    job_dict = {
        "name": job.name,
        "url": job.url,
        "created_at": now,
        "owner_id": uid,
    }
    
    # Add schedule fields based on type
    if has_interval:
        job_dict["interval_seconds"] = job.interval_seconds
    else:
        job_dict["hour"] = job.hour
        job_dict["minute"] = job.minute if job.minute is not None else 0
        job_dict["second"] = job.second if job.second is not None else 0
        job_dict["timezone"] = job.timezone
        if job.day_of_week:
            job_dict["day_of_week"] = job.day_of_week
    
    result = await db.jobs.insert_one(job_dict)
    job_id = str(result.inserted_id)
    
    # Schedule it
    _schedule_job_unified(job_id, job.url, job.interval_seconds, job.hour, job.minute, job.second, job.timezone, job.day_of_week)
    
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
    
    # Validation: prevent having both interval and time fields
    if "interval_seconds" in update_data and update_data["interval_seconds"] and \
       ("hour" in update_data and update_data["hour"] is not None):
        raise HTTPException(status_code=400, 
                          detail="Cannot have both interval_seconds and hour+timezone")
    
    if "timezone" in update_data and update_data["timezone"] not in SUPPORTED_TIMEZONES:
        raise HTTPException(status_code=400, 
                          detail=f"Unsupported timezone. Use: {list(SUPPORTED_TIMEZONES.keys())}")
    
    if update_data:
        await db.jobs.update_one({"_id": obj_id}, {"$set": update_data})
    
    # Determine current schedule config
    final_interval = update_data.get("interval_seconds", existing.get("interval_seconds"))
    final_hour = update_data.get("hour", existing.get("hour"))
    final_minute = update_data.get("minute", existing.get("minute"))
    final_second = update_data.get("second", existing.get("second"))
    final_tz = update_data.get("timezone", existing.get("timezone"))
    final_url = update_data.get("url", existing.get("url", ""))
    final_dow = update_data.get("day_of_week", existing.get("day_of_week"))
    
    # Reschedule if URL or schedule changed
    if final_url:
        _schedule_job_unified(job_id, final_url, final_interval, final_hour, final_minute, final_second, final_tz, final_dow)
    
    return {"status": "updated"}

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

@app.get("/api/available-hours")
async def get_available_hours(session_id: Optional[str] = Cookie(default=None)):
    """Get list of available hours (0-23) for daily scheduled jobs."""
    require_user(session_id)
    return {"hours": AVAILABLE_HOURS}

@app.get("/api/available-timezones")
async def get_available_timezones(session_id: Optional[str] = Cookie(default=None)):
    """Get list of supported timezones for daily scheduled jobs."""
    require_user(session_id)
    return {"timezones": list(SUPPORTED_TIMEZONES.keys())}

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
