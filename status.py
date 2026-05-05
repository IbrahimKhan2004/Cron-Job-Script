from datetime import datetime, timezone
from typing import Callable, Optional

from bson import ObjectId
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def _relative_time_from(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds} sec ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def create_status_router(
    db_getter: Callable,
    memory_logs_getter: Callable,
    require_user_fn: Callable,
    admin_id: str,
    templates: Jinja2Templates,
    serialize_log_fn: Callable,
) -> APIRouter:
    router = APIRouter()

    async def _authorized_job(job_id: str, uid: str):
        try:
            obj_id = ObjectId(job_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid job ID")
        db = db_getter()
        job = await db.jobs.find_one({"_id": obj_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if uid != admin_id and job.get("owner_id") != uid:
            raise HTTPException(status_code=403, detail="Access denied")
        return job

    @router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
    async def status_page(job_id: str, request: Request, session_id: Optional[str] = Cookie(default=None)):
        uid = require_user_fn(session_id)
        job = await _authorized_job(job_id, uid)
        return templates.TemplateResponse(request, "status.html", {
            "job_id": job_id,
            "job_name": job.get("name", "Untitled"),
            "job_url": job.get("url", ""),
        })

    @router.get("/api/jobs/{job_id}/status")
    async def job_status(job_id: str, session_id: Optional[str] = Cookie(default=None)):
        uid = require_user_fn(session_id)
        job = await _authorized_job(job_id, uid)

        memory_logs = memory_logs_getter()
        job_logs = list(memory_logs.get(job_id, []))

        total_runs = len(job_logs)
        failed_logs = [l for l in job_logs if l.get("success") is False]
        failed_runs = len(failed_logs)

        last_log = job_logs[0] if job_logs else None
        last_failed = failed_logs[0] if failed_logs else None

        last_entry = serialize_log_fn(last_log) if last_log else None
        last_error = last_failed.get("error") if last_failed else None
        last_ts = last_log.get("timestamp") if last_log else None

        if total_runs == 0:
            status_label = "never"
        elif last_log.get("success") is True:
            status_label = "success"
        elif last_log.get("status") == "timeout":
            status_label = "warning"
        else:
            status_label = "failed"

        success_runs = max(total_runs - failed_runs, 0)
        success_rate = round((success_runs / total_runs) * 100, 2) if total_runs else 0

        return {
            "job": {
                "id": job_id,
                "name": job.get("name", "Untitled"),
                "url": job.get("url", ""),
                "interval_seconds": job.get("interval_seconds", 0),
            },
            "last_run_status": status_label,
            "last_execution_time": last_entry["timestamp"] if last_entry else None,
            "time_since_last_run": _relative_time_from(last_ts),
            "total_runs": total_runs,
            "failed_runs": failed_runs,
            "success_rate": success_rate,
            "last_error_message": last_error,
        }

    @router.get("/api/jobs/{job_id}/status/logs")
    async def job_status_logs(job_id: str, failed_only: bool = False, session_id: Optional[str] = Cookie(default=None)):
        uid = require_user_fn(session_id)
        await _authorized_job(job_id, uid)

        memory_logs = memory_logs_getter()
        job_logs = list(memory_logs.get(job_id, []))

        if failed_only:
            job_logs = [l for l in job_logs if l.get("success") is False]

        logs = [serialize_log_fn(doc) for doc in job_logs[:20]]
        return {"logs": logs, "limit": 20, "failed_only": failed_only}

    return router
