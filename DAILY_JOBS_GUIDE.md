# CronPulse Update: Timezone-aware Daily Jobs

## Changes Summary

### 1. NEW MODULE: `time_scheduler.py`
Standalone module for timezone-aware daily scheduling logic.

**Features:**
- `SUPPORTED_TIMEZONES`: UTC, IST (Asia/Kolkata)
- `AVAILABLE_HOURS`: 0-23 (all hours supported)
- `schedule_daily_job()`: Schedule job at specific hour/timezone
- `get_cron_trigger_for_time()`: Generate APScheduler CronTrigger
- `get_next_run_time_for_daily()`: Calculate next execution time

### 2. NEW ENDPOINTS (Non-regressive - existing /api/jobs untouched)

#### Create Daily Job
```
POST /api/daily-jobs
Body: {
  "name": "Ping at 12 AM UTC",
  "url": "https://example.com/ping",
  "hour": 0,
  "timezone": "UTC"  // or "IST"
}
```

#### Get Daily Jobs
```
GET /api/daily-jobs
Returns: List of user's daily jobs with next_run time
```

#### Update Daily Job
```
PATCH /api/daily-jobs/{job_id}
Body: {
  "hour": 11,           // Optional
  "timezone": "IST",    // Optional
  "url": "...",         // Optional
  "name": "..."         // Optional
}
```

#### Delete Daily Job
```
DELETE /api/daily-jobs/{job_id}
```

#### Get Available Hours
```
GET /api/available-hours
Returns: {"hours": [0, 1, 2, ..., 23]}
```

#### Get Supported Timezones
```
GET /api/available-timezones
Returns: {"timezones": ["UTC", "IST"]}
```

### 3. PYDANTIC MODELS (New)

```python
class DailyJobIn(BaseModel):
    url: str
    name: str (1-80 chars)
    hour: int (0-23)
    timezone: str ("UTC" or "IST")

class DailyJobUpdate(BaseModel):
    url: Optional[str]
    name: Optional[str]
    hour: Optional[int]
    timezone: Optional[str]
```

### 4. MODIFICATIONS TO app.py

**Imports:**
- Added: `time_scheduler` module imports
- No removal of existing imports

**Job Runners:**
- Existing `run_cron_job()` → UNCHANGED
- New `run_daily_job()` → Identical logic, tags logs with `job_type: "daily"`

**Helpers:**
- Existing `_schedule_job()`, `_unschedule_job()` → UNCHANGED
- New: `_schedule_daily_job_wrapper()`, `_unschedule_daily_job_wrapper()`

**Lifespan:**
- Now loads BOTH job types on startup:
  - Interval jobs: `{"job_type": {"$ne": "daily"}}`
  - Daily jobs: `{"job_type": "daily"}`
- Existing interval job loading logic preserved

**Database Schema:**
- Jobs can now have `job_type` field: "daily" or omitted (interval)
- All existing jobs remain unchanged

### 5. NEW REQUIREMENT
- `pytz` added to requirements.txt (timezone support)

## Database Structure

```javascript
// Daily job document
{
  _id: ObjectId,
  name: "Noon Daily Check",
  url: "https://api.example.com/heartbeat",
  hour: 12,
  timezone: "IST",
  job_type: "daily",
  created_at: DateTime,
  owner_id: "telegram_id"
}

// Interval job document (unchanged)
{
  _id: ObjectId,
  name: "Every 5 minutes",
  url: "https://example.com",
  interval_seconds: 300,
  created_at: DateTime,
  owner_id: "telegram_id"
  // job_type: omitted (backward compatible)
}
```

## Timeline Example (IST)

If user selects hour=12, timezone="IST":
- Runs daily at 12:00:00 PM IST
- Uses APScheduler CronTrigger with `hour=12, minute=0, second=0` in Asia/Kolkata timezone
- Next run time calculated in IST and converted to UTC for display

## No Breaking Changes ✓

✅ Existing `/api/jobs` endpoints unchanged  
✅ Existing interval-based job logic untouched  
✅ Legacy jobs continue to work  
✅ Database backward compatible  
✅ All existing tests/functionality preserved  

## Testing

1. Create daily job at 12 AM UTC
2. Verify endpoint returns correct timezone
3. Check logs contain daily pings with `job_type: "daily"`
4. Update hour/timezone, verify reschedule works
5. Delete daily job, verify unscheduled
