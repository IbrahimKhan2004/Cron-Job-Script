# ⏱️ CronMaster - Professional Cron Job Platform

CronMaster is a robust, full-stack cron job management platform designed for reliability and ease of use. It allows you to schedule HTTP pings to any URL at custom intervals, monitor their status in real-time, and view execution history through a professional, responsive dashboard.

## 🚀 Features

-   **Dynamic Scheduling**: Add, delete, and update cron jobs on the fly without restarting the server.
-   **MongoDB Persistence**: All jobs and execution logs are securely stored in MongoDB.
-   **Professional Dashboard**: Modern UI built with Tailwind CSS and DaisyUI.
-   **Dark/Light Mode**: Full support for both dark and light themes with a smooth toggle.
-   **Real-time Logs**: Monitor execution status and response codes as they happen.
-   **Legacy Support**: Fully preserves existing monitoring logic for hardcoded legacy URLs.
-   **High Performance**: Built on FastAPI and Motor (Asynchronous MongoDB driver).

## 🛠️ Tech Stack

-   **Backend**: Python, FastAPI, APScheduler
-   **Database**: MongoDB (via Motor)
-   **Frontend**: HTML5, JavaScript (Fetch API), Tailwind CSS, DaisyUI
-   **Server**: Gunicorn / Uvicorn

## ⚙️ Environment Variables

To run this project, you will need to add the following environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MONGODB_URI` | Your MongoDB connection string | `mongodb://localhost:27017` |
| `PORT` | Port to run the application on | `8080` |

## 💻 Local Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd CronMaster
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**:
    ```bash
    python3 app.py
    ```
    The application will be available at `http://localhost:8080`.

## ☁️ Deployment

### Render / Heroku
This project is pre-configured for deployment on Render or Heroku.
-   The `Procfile` defines the entry point: `web: python3 app.py`.
-   Ensure you set the `MONGODB_URI` in your environment settings.

## Changelog

### v3.1.1 - Managed Jobs Ping/SSL Display Update
- Updated Managed Jobs next-ping text format to show day/hr/min/sec words for clearer countdown readability.
- Updated Managed Jobs auto-refresh behavior so periodic refresh updates ping timing without triggering automatic SSL re-check requests.
- Preserved manual/initial SSL check rendering in Managed Jobs while keeping existing cron execution and scheduler logic unchanged.

### v3.1.0 - Cron Job Status Page
- Added a dedicated per-job status page route (`/jobs/{job_id}/status`) with responsive UI, sticky header, favicon display, and copy URL action.
- Added read-only status APIs for per-job analytics and recent logs:
  - `GET /api/jobs/{job_id}/status`
  - `GET /api/jobs/{job_id}/status/logs?failed_only=true|false`
- Added a new **Status Page** action in each job row three-dot menu for quick navigation.
- Status page now shows last run status, execution timing, total/failed runs, success rate, last error, and latest 20 logs with optional failed-only filtering.
