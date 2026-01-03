# eCan.ai Ubuntu Server Deployment Guide

This guide covers deploying eCan.ai as a headless web server on Ubuntu Linux.

## Overview

eCan.ai can run in two modes:
- **Desktop Mode** - Full GUI with PySide6 (Windows/macOS)
- **Web Mode** - Headless server with WebSocket API (Ubuntu/Linux servers)

This guide focuses on **Web Mode** deployment.

## Prerequisites

### System Requirements
- Ubuntu 20.04 LTS or newer (22.04 LTS recommended)
- Python 3.10+ (Python 3.12+ recommended)
- 4GB+ RAM (8GB+ recommended for AI workloads)
- 20GB+ disk space

### Required System Packages
```bash
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    libpq-dev \
    gcc \
    libffi-dev \
    tesseract-ocr \
    poppler-utils \
    git
```

## Quick Start

### 1. Clone the Repository
```bash
git clone <your-repo-url> eCan.ai
cd eCan.ai
```

### 2. Run the Deployment Script
```bash
# Make script executable
chmod +x scripts/deploy-ubuntu.sh

# Run setup (installs everything)
./scripts/deploy-ubuntu.sh setup

# Configure your API keys
nano .env.web

# Start the server
./scripts/deploy-ubuntu.sh start
```

### 3. Verify Installation
```bash
# Check status
./scripts/deploy-ubuntu.sh status

# Test health endpoint
curl http://localhost:8765/health
```

## Manual Installation

If you prefer manual setup:

### 1. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements-web.txt
```

### 3. Install Playwright Browsers (Optional)
```bash
playwright install chromium --with-deps
```

### 4. Configure Environment
```bash
# Create environment file
cat > .env.web << EOF
ECAN_MODE=web
ECAN_WS_HOST=0.0.0.0
ECAN_WS_PORT=8765
ECAN_LOG_LEVEL=INFO

# API Keys (add your own)
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
EOF
```

### 5. Start the Server
```bash
source venv/bin/activate
export ECAN_MODE=web
python -m uvicorn web_server:app --host 0.0.0.0 --port 8765
```

## Deployment Script Commands

The `scripts/deploy-ubuntu.sh` script provides these commands:

| Command | Description |
|---------|-------------|
| `setup` | Install dependencies and configure environment |
| `start` | Start the web server in background |
| `stop` | Stop the web server |
| `restart` | Restart the web server |
| `status` | Check server status and health |
| `logs` | View server logs (tail -f) |
| `help` | Show help message |

### Examples
```bash
# First-time setup
./scripts/deploy-ubuntu.sh setup

# Start server
./scripts/deploy-ubuntu.sh start

# Start on custom port
ECAN_WS_PORT=9000 ./scripts/deploy-ubuntu.sh start

# Check status
./scripts/deploy-ubuntu.sh status

# View logs
./scripts/deploy-ubuntu.sh logs

# Restart after code changes
./scripts/deploy-ubuntu.sh restart
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ECAN_MODE` | `web` | Must be `web` for headless mode |
| `ECAN_WS_HOST` | `0.0.0.0` | WebSocket bind address |
| `ECAN_WS_PORT` | `8765` | WebSocket port |
| `ECAN_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `ECAN_VENV_PATH` | `./venv` | Virtual environment path |

### API Keys

Add your LLM provider API keys to `.env.web`:
```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
GOOGLE_API_KEY=...

# Alibaba DashScope (Qwen)
DASHSCOPE_API_KEY=...
```

## Docker Deployment

For containerized deployment, use the provided Docker files:

```bash
# Build and start with Docker Compose
docker-compose -f docker-compose.web.yml up -d

# View logs
docker-compose -f docker-compose.web.yml logs -f

# Stop
docker-compose -f docker-compose.web.yml down
```

### Docker Environment
The `docker-compose.web.yml` file sets up:
- eCan.ai backend service
- Nginx reverse proxy (optional)
- Proper environment variables

## Reverse Proxy Setup (Nginx)

For production, use Nginx as a reverse proxy:

```nginx
# /etc/nginx/sites-available/ecan
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket timeout
        proxy_read_timeout 86400;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/ecan /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Systemd Service (Production)

For production, create a systemd service:

```bash
# /etc/systemd/system/ecan-web.service
[Unit]
Description=eCan.ai Web Server
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/eCan.ai
Environment="ECAN_MODE=web"
Environment="ECAN_WS_HOST=127.0.0.1"
Environment="ECAN_WS_PORT=8765"
EnvironmentFile=/opt/eCan.ai/.env.web
ExecStart=/opt/eCan.ai/venv/bin/python -m uvicorn web_server:app --host 127.0.0.1 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ecan-web
sudo systemctl start ecan-web
sudo systemctl status ecan-web
```

## API Endpoints

Once running, the server exposes:

| Endpoint | Description |
|----------|-------------|
| `ws://host:port/ws` | WebSocket connection for IPC |
| `http://host:port/health` | Health check endpoint |
| `http://host:port/api/...` | REST API endpoints |

## Troubleshooting

### Server Won't Start
```bash
# Check logs
./scripts/deploy-ubuntu.sh logs

# Or directly
tail -f runlogs/web_server.log
```

### Port Already in Use
```bash
# Find process using port
sudo lsof -i :8765

# Kill if needed
sudo kill -9 <PID>
```

### Permission Denied
```bash
# Ensure script is executable
chmod +x scripts/deploy-ubuntu.sh

# Check file ownership
ls -la scripts/
```

### Missing Dependencies
```bash
# Reinstall dependencies
source venv/bin/activate
pip install -r requirements-web.txt --force-reinstall
```

### Python Version Issues
```bash
# Check Python version
python3 --version

# Install Python 3.12 if needed (Ubuntu 22.04+)
sudo apt install python3.12 python3.12-venv
```

## Limitations in Web Mode

Some features are not available in headless mode:

| Feature | Desktop | Web Mode |
|---------|---------|----------|
| File dialogs | ✅ | ❌ (use file paths) |
| Screen capture | ✅ | ❌ |
| Desktop automation | ✅ | ❌ |
| Native notifications | ✅ | ❌ |

For file operations in web mode, pass file paths directly instead of using dialogs.

## Security Recommendations

1. **Firewall**: Only expose necessary ports
   ```bash
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # HTTP (if using Nginx)
   sudo ufw allow 443/tcp  # HTTPS
   sudo ufw enable
   ```

2. **API Keys**: Never commit `.env.web` to version control

3. **HTTPS**: Use Let's Encrypt for SSL
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

4. **Updates**: Keep system and dependencies updated
   ```bash
   sudo apt update && sudo apt upgrade
   pip install -r requirements-web.txt --upgrade
   ```

## Support

For issues specific to Ubuntu deployment, check:
- Server logs: `runlogs/web_server.log`
- System logs: `journalctl -u ecan-web` (if using systemd)
- GitHub Issues: [link to your repo]

---

*Last updated: January 2026*
