# Kilifi County ICT Attachee Tracking System
## Backend Setup Guide

---

## Quick Start (Local Network)

### Requirements
- Python 3.8 or newer  
- pip (comes with Python)

### 1. Install dependencies
```bash
pip install flask flask-cors flask-jwt-extended
```

### 2. Start the server

**Linux / Mac:**
```bash
bash start.sh
```

**Windows:**
Double-click `start.bat`  
— or —  
```cmd
python server.py
```

### 3. Open the app
Go to **http://localhost:5000** in any browser.

---

## Sharing with multiple users on the same Wi-Fi / LAN

1. Find your computer's local IP address:
   - **Windows:** Open Command Prompt → type `ipconfig` → look for **IPv4 Address** (e.g. `192.168.1.10`)
   - **Linux/Mac:** Open Terminal → type `ifconfig` or `ip addr` → look for `inet` address

2. Other users on the same network open: `http://192.168.1.10:5000`  
   *(replace with your actual IP)*

---

## Hosting on the Internet (Free options)

### Option A — Railway.app (Recommended, free tier)
1. Create a free account at https://railway.app
2. Install Railway CLI: `npm install -g @railway/cli`  
   or upload via the web UI
3. In the `kilifi-app` folder, run:
   ```bash
   railway login
   railway init
   railway up
   ```
4. Railway gives you a public URL like `https://kilifi-app.up.railway.app`

### Option B — Render.com (Free tier, sleeps after 15 min idle)
1. Create a free account at https://render.com
2. Click **New → Web Service**
3. Upload or connect your GitHub repo containing this folder
4. Set:
   - **Build Command:** `pip install flask flask-cors flask-jwt-extended`
   - **Start Command:** `python server.py`
   - **Environment Variable:** `PORT=10000`
5. Click Deploy — you get a public URL

### Option C — PythonAnywhere (Free, always-on)
1. Create free account at https://www.pythonanywhere.com
2. Upload all files in this folder
3. In **Web** tab → Add new web app → Flask
4. Set source code to your uploaded folder
5. Your app is live at `yourusername.pythonanywhere.com`

---

## Default Logins

| Username | Password    | Role       |
|----------|-------------|------------|
| admin    | Admin@1234  | Admin      |
| linus    | Pass@1234   | Supervisor |
| betty    | Pass@1234   | Supervisor |
| (others) | Pass@1234   | Supervisor |

**Change passwords after first login** via User Management → Delete old user → Add User.

---

## Data Storage
All data is stored in **kilifi.db** (SQLite file) in the same folder as `server.py`.  
- Back up this file regularly  
- Do NOT delete it — it contains all your records

## Security Note
For production use, set a strong JWT secret:
```bash
export JWT_SECRET="your-very-long-random-secret-here"
python server.py
```

---

## Files in this package
```
kilifi-app/
├── server.py      ← Backend API (Python/Flask)
├── index.html     ← Frontend (served by the backend)
├── kilifi.db      ← Database (created on first run)
├── start.sh       ← Start script for Linux/Mac
├── start.bat      ← Start script for Windows
└── README.md      ← This file
```
