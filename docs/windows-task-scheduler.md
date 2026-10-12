# Windows Task Scheduler Setup Guide

This guide describes how to configure Windows Task Scheduler to automatically run the **Daily Job Finder Automation** once per day.

---

## 1. Quick Overview

- **Runner Script**: `scripts\run_daily_job_finder.bat`
- **Working Directory**: Project root folder (e.g., `C:\Users\<username>\job-finder-automation`)
- **Execution Frequency**: Once per day (recommended: 08:00 AM or 09:00 AM)
- **Log Location**: `data\logs\job_finder_YYYYMMDD_HHMMSS.log`
- **Excel Report Location**: `data\exports\job_leads_YYYYMMDD_HHMMSS.xlsx`

The batch script operates independently of your current directory, detects your virtual environment (`venv` or `.venv`), acquires a process lock to prevent duplicate runs, exports results to Excel, updates the SQLite database, and automatically retains the last 30 days of logs.

---

## 2. Step-by-Step Manual Setup (GUI)

### Step 1: Open Task Scheduler
1. Press `Win + R` on your keyboard.
2. Type `taskschd.msc` and press **Enter**.
3. In the right-hand **Actions** pane, click **Create Task...** (do **not** choose *Create Basic Task* for full control over settings).

---

### Step 2: "General" Tab
- **Name**: `Daily Job Finder Automation`
- **Description**: `Automated daily discovery of relevant job openings and Excel export.`
- **Security options**:
  - Select **Run only when user is logged on** (recommended for personal use; does not require saving your Windows password).
  - *Alternative*: If you want it to run when your screen is locked/logged off, select **Run whether user is logged on or not**. Windows will prompt you once for your account password.
  - Leave **Run with highest privileges** unchecked (administrator rights are not required).
  - **Configure for**: `Windows 10` or `Windows 11`.

---

### Step 3: "Triggers" Tab
1. Click **New...**
2. **Begin the task**: `On a schedule`
3. **Settings**: Select **Daily**
4. **Start**: Set your preferred daily time (e.g., `09:00:00 AM`), recur every `1` days.
5. **Advanced settings**:
   - Check **Stop task if it runs longer than**: `1 hour` (normal execution takes 15–60 seconds).
   - Check **Enabled**.
6. Click **OK**.

---

### Step 4: "Actions" Tab
1. Click **New...**
2. **Action**: `Start a program`
3. **Program/script**: Click **Browse...** and navigate to your project's runner script:
   ```text
   C:\Users\<YourUsername>\job-finder-automation\scripts\run_daily_job_finder.bat
   ```
4. **Start in (optional)**: Enter the full path to your project root (without quotes):
   ```text
   C:\Users\<YourUsername>\job-finder-automation
   ```
   *(Although `run_daily_job_finder.bat` automatically resolves the project root, providing "Start in" is best practice in Task Scheduler).*
5. Click **OK**.

---

### Step 5: "Conditions" Tab
Configure based on your machine habits:
- **Power**:
  - **Start the task only if the computer is on AC power**: Uncheck this if you use a laptop on battery.
  - **Stop if the computer switches to battery power**: Uncheck.
  - **Wake the computer to run this task**: (Optional) Check this if you want Windows to wake from sleep mode at scheduled time.
- **Network**:
  - **Start only if the following network connection is available**: Check **Any connection** (required for fetching job postings from APIs).

---

### Step 6: "Settings" Tab
- Check **Allow task to be run on demand** (lets you right-click and click "Run" anytime).
- Check **Run task as soon as possible after a scheduled start is missed** (crucial: if your laptop was powered off at 9:00 AM, the task will run immediately when you turn it on).
- Check **If the task fails, restart every**: `10 minutes`, **Attempt to restart up to**: `3 times`.
- Check **Stop the task if it runs longer than**: `1 hour`.
- Check **If the running task does not end when requested, force it to stop**.
- **If the task is already running, then the following rule applies**: `Do not start a new instance` (aligns with the project's internal process lock).

Click **OK** to save the task.

---

## 3. Verifying the Scheduled Task

### Test Run from Task Scheduler
1. In Task Scheduler, click **Task Scheduler Library** in the left sidebar.
2. Find **Daily Job Finder Automation** in the list.
3. Right-click the task and select **Run**.
4. Wait 30–60 seconds, then press `F5` to refresh the list.
5. Verify:
   - **Last Run Result**: `The operation completed successfully. (0x0)`
   - Open `data\logs\` and check that a new timestamped log file was created.
   - Open `data\exports\` and check that a new Excel report was generated.

---

## 4. Manual Testing via Command Prompt or PowerShell

You can manually test the runner at any time without Task Scheduler:

```cmd
cd /d C:\Users\<YourUsername>\job-finder-automation
scripts\run_daily_job_finder.bat
```

Or from any other folder:
```cmd
C:\Users\<YourUsername>\job-finder-automation\scripts\run_daily_job_finder.bat
```

Check the exit code:
- **Windows Command Prompt**: `echo %ERRORLEVEL%`
- **PowerShell**: `echo $LASTEXITCODE`

### Exit Codes:
| Code | Meaning | Description |
|:---:|:---|:---|
| `0` | **Success** | Pipeline completed successfully (or with handled source warnings such as Naukri 403). |
| `1` | **Pipeline Failure** | Internal unhandled pipeline error. See log traceback. |
| `2` | **Runner / Environment Error** | Python executable, `app/main.py`, or directories missing. |
| `3` | **Run in Progress** | Another instance is currently executing (`job_finder.lock` active). |

---

## 5. Troubleshooting & Maintenance

### Task Missed or Failed
- Open `data\logs\` and inspect the latest log file.
- Verify internet connectivity.
- Verify that your Python virtual environment (`venv\Scripts\python.exe`) still exists.

### Stale Lock Recovery
If your computer suddenly shut down or lost power during a run, a lock file might remain at `data\job_finder.lock`.
- The system automatically detects dead PIDs and clears stale locks.
- If necessary, you can safely delete `data\job_finder.lock` manually.

### Disabling or Removing the Scheduled Task
- To pause automation: Open Task Scheduler, right-click **Daily Job Finder Automation**, and select **Disable**.
- To delete automation: Right-click and select **Delete**.
