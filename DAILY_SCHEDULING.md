# CronPulse: Daily Scheduling Feature

## Overview
One unified job creation form supporting both **interval-based** (every X minutes/hours) and **time-based** (daily at specific time) scheduling.

## Features

### 1. Create Job Form (Sidebar)
- **Schedule Type Toggle**: Choose between "Every X Minutes/Hours" or "Daily at Specific Time"
- **Interval Mode** (Default):
  - Number input + Unit selector (seconds, minutes, hours, days)
  - Example: "5 minutes" = every 5 minutes
- **Daily Mode**:
  - Hour selector: 00-23
  - Minute selector: 0-59 (with common shortcuts: 00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
  - Second selector: 0-59 (with common shortcuts: 00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
  - Timezone selector: **UTC** or **IST** (Asia/Kolkata)
  - Example: "12:05:30 IST" = Every day at 12:05:30 PM India Standard Time

### 2. Jobs Table Display
- **Schedule Column** shows:
  - Interval jobs: `5m`, `2h`, `1d` (in blue badge)
  - Daily jobs: `12:05:30 IST` (in green badge)
- **Next Ping** shows relative time (e.g., "in 2 hours")
- **SSL** column shows certificate expiry status
- **Actions**: Edit, View Logs, Delete

### 3. Edit Modal
- Automatically detects job type (interval or daily)
- Shows relevant fields based on job type
- Can modify name, URL, and schedule parameters
- Cannot convert interval → daily or vice versa (edit only changes values)

## Database Schema

```javascript
// Interval-based job
{
  _id: ObjectId,
  name: "Keep Alive",
  url: "https://example.com/ping",
  interval_seconds: 300,        // 5 minutes
  created_at: DateTime,
  owner_id: "telegram_id"
}

// Daily-based job
{
  _id: ObjectId,
  name: "Noon Check",
  url: "https://api.example.com/heartbeat",
  hour: 12,                     // 0-23
  minute: 5,                    // 0-59
  second: 30,                   // 0-59
  timezone: "IST",              // "UTC" or "IST"
  created_at: DateTime,
  owner_id: "telegram_id"
}
```

## API Endpoints

### Create Job
```bash
POST /api/jobs
Content-Type: application/json

# Interval mode
{
  "name": "Keep Alive",
  "url": "https://example.com/ping",
  "interval_seconds": 300
}

# Daily mode
{
  "name": "Noon Check",
  "url": "https://api.example.com/heartbeat",
  "hour": 12,
  "minute": 5,
  "second": 30,
  "timezone": "IST"
}
```

### Update Job
```bash
PATCH /api/jobs/{job_id}
Content-Type: application/json

# Update interval job
{
  "name": "New Name",
  "url": "https://newurl.com",
  "interval_seconds": 600
}

# Update daily job
{
  "hour": 14,
  "minute": 30,
  "second": 0,
  "timezone": "UTC"
}
```

### Get Jobs
```bash
GET /api/jobs

Response:
{
  "id": "...",
  "name": "Noon Check",
  "url": "https://...",
  "hour": 12,              // null for interval jobs
  "minute": 5,             // null for interval jobs
  "second": 30,            // null for interval jobs
  "timezone": "IST",       // null for interval jobs
  "interval_seconds": null, // null for daily jobs
  "next_run": "2024-04-18T14:05:30+05:30",
  "created_at": "2024-04-10T12:00:00Z",
  "owner_id": "..."
}
```

## Backend Implementation

### Scheduler Unification
**File**: `app.py`

- **Single function** `_schedule_job_unified()` handles both types
- Uses APScheduler's `IntervalTrigger` for interval jobs
- Uses APScheduler's `CronTrigger` with timezone for daily jobs
- Supports **UTC** and **IST** timezones via `pytz`

```python
def _schedule_job_unified(job_id, url, interval_seconds, hour, minute, second, timezone):
    if interval_seconds:
        # Use IntervalTrigger
        _schedule_job(job_id, url, interval_seconds)
    elif hour is not None:
        # Use CronTrigger with timezone
        tz = pytz.timezone(SUPPORTED_TIMEZONES[timezone])
        trigger = CronTrigger(hour=hour, minute=m, second=s, timezone=tz)
        scheduler.add_job(run_cron_job, trigger, id=job_id, args=[job_id, url])
```

### Startup (Lifespan)
- Automatically loads ALL jobs from MongoDB on app start
- Reschedules both interval and daily jobs
- No job loss on restart

## Frontend Implementation

### HTML Form
**File**: `templates/index.html`

```html
<select id="scheduleType" onchange="toggleScheduleMode()">
  <option value="interval">Every X Minutes/Hours</option>
  <option value="daily">Daily at Specific Time</option>
</select>

<!-- Two divs toggle visibility based on selection -->
<div id="intervalMode"> ... </div>
<div id="dailyMode"> ... </div>
```

### JavaScript Functions
- `toggleScheduleMode()` - Shows/hides form fields
- `createJob()` - Builds correct JSON based on mode
- `saveEdit()` - Detects job type and updates accordingly
- `fmtTime(hour, minute, second, tz)` - Formats time for display

## Timezone Examples

### UTC Example
- User selects: Hour=14, Minute=30, Second=0, Timezone=UTC
- Job runs at: **14:30:00 UTC** daily (2:30 PM UTC)
- Display: `14:30:00 UTC`

### IST Example
- User selects: Hour=12, Minute=5, Second=30, Timezone=IST
- Job runs at: **12:05:30 IST** daily (12:05:30 PM India Standard Time)
- Display: `12:05:30 IST`
- In UTC: ~6:35:30 AM UTC (IST is UTC+5:30)

## Execution Logs

All executions logged with:
- Job ID
- URL pinged
- HTTP status
- Success/failure
- Timestamp (UTC)
- Error message (if any)

Example log entry:
```javascript
{
  _id: ObjectId,
  job_id: "...",
  url: "https://api.example.com/heartbeat",
  timestamp: "2024-04-18T06:35:30.123Z",
  status: 200,
  success: true,
  response_preview: "OK",
  error: null
}
```

## Non-Breaking Changes ✓

✅ Existing interval jobs work exactly as before  
✅ Old jobs without hour/minute/second fields continue to run  
✅ No database migration required  
✅ Backward compatible with legacy data  
✅ All existing endpoints unchanged  

## Common Use Cases

### Keep App Alive Every 5 Minutes
- Schedule Type: "Every X Minutes/Hours"
- Interval: 5 minutes
- URL: `https://myapp.render.com/health`

### Daily Database Backup at 2 AM UTC
- Schedule Type: "Daily at Specific Time"
- Hour: 2, Minute: 0, Second: 0
- Timezone: UTC
- URL: `https://backup.example.com/db-backup`

### Daily Report at 9 AM IST
- Schedule Type: "Daily at Specific Time"
- Hour: 9, Minute: 0, Second: 0
- Timezone: IST
- URL: `https://reports.example.com/daily`

### Precise Daily Check at 12:05:30 AM IST
- Schedule Type: "Daily at Specific Time"
- Hour: 0, Minute: 5, Second: 30
- Timezone: IST
- URL: `https://api.example.com/precise-check`

## Troubleshooting

### Job not running at expected time?
1. Check timezone setting (UTC vs IST)
2. Verify hour/minute/second values
3. Check server logs for scheduling errors
4. Restart app to reload jobs from DB

### Different time than expected?
- IST is UTC+5:30
- If job set to 12:00 IST, it runs at 06:30 UTC
- Check "Next Ping" column for actual next execution time

### Need to change from interval to daily?
- Delete old job
- Create new daily job with desired time
- Cannot convert existing job type
