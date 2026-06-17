# WhatsApp Campaign Dashboard

**Python FastAPI + MongoDB + HTML/CSS/JS**

A central control panel for managing 50+ Android devices that send WhatsApp messages at scale. Features real-time device monitoring, campaign management, anti-block intelligence, and human-like typing simulation.

---

## Features

| Feature | Description |
|---------|-------------|
| **Device Monitoring** | Real-time status, battery level, connectivity, message counts for 50+ devices |
| **Campaign Management** | Create campaigns with text, images, PDFs; assign devices; control status |
| **Task Queue** | View pending tasks, distribution per device, retry failed, clear queue |
| **Tuning Profiles** | Configure typing speed, delays, mistake rates, random pauses |
| **Anti-Block Intelligence** | Randomized typing, campaign mixing per device, human-like behavior |
| **Media Management** | Upload images/PDFs, preview, associate with campaigns |
| **API Keys** | Generate and manage keys for Android agent authentication |
| **Analytics** | Success/failure rates, device performance, delivery timeline |

---

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: MongoDB 7+
- **Frontend**: HTML5 / CSS3 / Vanilla JavaScript
- **Template Engine**: Jinja2
- **File Uploads**: python-multipart + aiofiles

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- MongoDB 7+ (running locally or remote)
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/wa-campaign-dashboard.git
cd wa-campaign-dashboard
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your MongoDB connection string
```

### 5. Start MongoDB

```bash
# If using Docker:
docker run -d --name mongo -p 27017:27017 mongo:7

# Or start your local MongoDB service
sudo systemctl start mongod
```

### 6. Run the Dashboard

```bash
python main.py
```

Open http://localhost:8000 in your browser.

---

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Clone and enter directory
git clone https://github.com/YOUR_USERNAME/wa-campaign-dashboard.git
cd wa-campaign-dashboard

# Start everything
docker-compose up -d

# View logs
docker-compose logs -f dashboard
```

This starts both the dashboard (port 8000) and MongoDB (port 27017).

### Using Docker Only

```bash
# Build the image
docker build -t wa-dashboard .

# Run (assuming MongoDB is available)
docker run -d \
  --name wa-dashboard \
  -p 8000:8000 \
  -e MONGO_URL=mongodb://your-mongo-host:27017 \
  -e DB_NAME=wa_campaign \
  -v $(pwd)/uploads:/app/uploads \
  wa-dashboard
```

---

## Server Deployment (Ubuntu/Debian VPS)

### Step 1: Prepare the Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install MongoDB 7
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

### Step 2: Clone and Setup

```bash
cd /opt
sudo git clone https://github.com/YOUR_USERNAME/wa-campaign-dashboard.git
cd wa-campaign-dashboard

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Set MONGO_URL and PORT
```

### Step 3: Create Systemd Service

```bash
sudo tee /etc/systemd/system/wa-dashboard.service << 'EOF'
[Unit]
Description=WhatsApp Campaign Dashboard
After=network.target mongod.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/wa-campaign-dashboard
Environment=PATH=/opt/wa-campaign-dashboard/venv/bin:/usr/bin
EnvironmentFile=/opt/wa-campaign-dashboard/.env
ExecStart=/opt/wa-campaign-dashboard/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wa-dashboard
sudo systemctl start wa-dashboard
```

### Step 4: Setup Nginx Reverse Proxy (Optional but Recommended)

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/wa-dashboard << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /uploads {
        alias /opt/wa-campaign-dashboard/uploads;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/wa-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 5: SSL with Let's Encrypt (Optional)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## GitHub Integration

### Initial Push

```bash
cd /opt/wa-campaign-dashboard

# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit: WhatsApp Campaign Dashboard"

# Add remote
git remote add origin https://github.com/YOUR_USERNAME/wa-campaign-dashboard.git
git branch -M main
git push -u origin main
```

### Auto-Deploy with GitHub Webhooks

Create a deploy script:

```bash
sudo tee /opt/wa-campaign-dashboard/deploy.sh << 'EOF'
#!/bin/bash
cd /opt/wa-campaign-dashboard
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wa-dashboard
echo "Deployed at $(date)"
EOF

chmod +x /opt/wa-campaign-dashboard/deploy.sh
```

For automatic deployment, set up a GitHub webhook pointing to a small listener, or use a cron-based pull:

```bash
# Add to crontab (checks every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * cd /opt/wa-campaign-dashboard && git fetch origin main && [ \$(git rev-parse HEAD) != \$(git rev-parse origin/main) ] && /opt/wa-campaign-dashboard/deploy.sh >> /var/log/wa-deploy.log 2>&1") | crontab -
```

---

## API Endpoints

### Dashboard API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all devices |
| GET | `/api/devices/stats` | Device statistics |
| PUT | `/api/devices/{id}` | Update device |
| DELETE | `/api/devices/{id}` | Remove device |
| POST | `/api/devices/{id}/command` | Send command to device |
| GET | `/api/campaigns` | List campaigns |
| POST | `/api/campaigns` | Create campaign |
| POST | `/api/campaigns/{id}/start` | Start campaign |
| POST | `/api/campaigns/{id}/pause` | Pause campaign |
| POST | `/api/campaigns/{id}/resume` | Resume campaign |
| POST | `/api/campaigns/{id}/stop` | Stop campaign |
| GET | `/api/tasks` | List tasks |
| POST | `/api/tasks/{id}/retry` | Retry failed task |
| POST | `/api/tasks/retry-all` | Retry all failed |
| DELETE | `/api/tasks/clear` | Clear queue |
| GET | `/api/tuning` | List tuning profiles |
| POST | `/api/tuning` | Create profile |
| GET | `/api/media` | List media files |
| POST | `/api/media/upload` | Upload media |
| GET | `/api/analytics/overview` | Analytics overview |

### Agent API (for Android APK)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agent/health` | Health check |
| POST | `/api/agent/register` | Register device |
| POST | `/api/agent/heartbeat` | Send heartbeat |
| GET | `/api/agent/tasks` | Fetch pending tasks |
| POST | `/api/agent/tasks/complete` | Report task completion |

---

## Project Structure

```
wa-campaign-dashboard/
├── main.py                    # FastAPI entry point
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker build file
├── docker-compose.yml         # Docker Compose config
├── .env.example               # Environment template
├── .gitignore
├── uploads/                   # Uploaded media files
├── app/
│   ├── __init__.py
│   ├── database.py            # MongoDB connection
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py         # Pydantic models
│   ├── api/
│   │   ├── __init__.py
│   │   ├── devices.py         # Device endpoints
│   │   ├── campaigns.py       # Campaign endpoints
│   │   ├── tasks.py           # Task queue endpoints
│   │   ├── tuning.py          # Tuning profile endpoints
│   │   ├── media.py           # Media upload endpoints
│   │   ├── apikeys.py         # API key endpoints
│   │   ├── analytics.py       # Analytics endpoints
│   │   ├── agent.py           # Agent API endpoints
│   │   └── pages.py           # HTML page routes
│   ├── templates/
│   │   ├── base.html          # Base layout template
│   │   └── pages/             # Page templates
│   └── static/
│       ├── css/style.css      # Stylesheet
│       └── js/app.js          # Frontend JavaScript
└── README.md
```

---

## License

MIT License
