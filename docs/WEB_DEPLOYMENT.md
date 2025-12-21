# eCan.ai Web Deployment Guide

This guide covers deploying eCan.ai as a web server for multi-user browser-based access.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser Clients                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  User 1  │  │  User 2  │  │  User 3  │  │  User N  │        │
│  │ (React)  │  │ (React)  │  │ (React)  │  │ (React)  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │               │
│       └─────────────┴──────┬──────┴─────────────┘               │
│                            │ WebSocket                          │
└────────────────────────────┼────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                      Nginx (Optional)                           │
│                   - Static file serving                         │
│                   - WebSocket proxy                             │
│                   - SSL termination                             │
└────────────────────────────┼────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                    eCan.ai Backend                              │
│  ┌─────────────────────────┴─────────────────────────────────┐  │
│  │              WebSocket Server (ws_server.py)              │  │
│  │                                                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │ UserContext │  │ UserContext │  │ UserContext │       │  │
│  │  │   (User 1)  │  │   (User 2)  │  │   (User N)  │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │              SessionManager (Singleton)             │ │  │
│  │  │  - Session lifecycle management                     │ │  │
│  │  │  - Connection-to-session mapping                    │ │  │
│  │  │  - Automatic session cleanup                        │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │              IPC Handler Registry                   │ │  │
│  │  │  - Same handlers as desktop mode                    │ │  │
│  │  │  - Context injection via context_bridge             │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Direct Python (Development)

```bash
# Set environment and run
export ECAN_MODE=web
python web_server.py

# Or with custom port
ECAN_WS_PORT=9000 python web_server.py
```

### Option 2: Docker (Recommended for Production)

```bash
# Build the image
docker build -f Dockerfile.web -t ecan-web .

# Run the container
docker run -d -p 8765:8765 --name ecan-web ecan-web

# Check logs
docker logs -f ecan-web
```

### Option 3: Docker Compose (Full Stack)

```bash
# Start all services
docker-compose -f docker-compose.web.yml up -d

# With Nginx (production profile)
docker-compose -f docker-compose.web.yml --profile production up -d
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ECAN_MODE` | `desktop` | Set to `web` for web deployment |
| `ECAN_WS_HOST` | `0.0.0.0` | WebSocket server bind address |
| `ECAN_WS_PORT` | `8765` | WebSocket server port |
| `ECAN_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Frontend Configuration

Create `gui_v2/.env.local`:

```env
# WebSocket server URL
VITE_WS_URL=ws://localhost:8765

# For production with Nginx
# VITE_WS_URL=wss://your-domain.com/ws
```

## AWS Deployment Options

### Option A: EC2 Instance

1. **Launch EC2 Instance**
   - AMI: Amazon Linux 2 or Ubuntu 22.04
   - Instance type: t3.medium or larger
   - Security group: Allow ports 80, 443, 8765

2. **Install Dependencies**
   ```bash
   sudo yum install -y docker docker-compose  # Amazon Linux
   # or
   sudo apt install -y docker.io docker-compose  # Ubuntu
   ```

3. **Deploy**
   ```bash
   git clone <your-repo>
   cd eCan.ai
   docker-compose -f docker-compose.web.yml up -d
   ```

### Option B: ECS Fargate (Serverless Containers)

1. **Create ECR Repository**
   ```bash
   aws ecr create-repository --repository-name ecan-web
   ```

2. **Push Image**
   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker tag ecan-web:latest <account>.dkr.ecr.<region>.amazonaws.com/ecan-web:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/ecan-web:latest
   ```

3. **Create ECS Task Definition** (see `ecs-task-definition.json`)

4. **Create ECS Service with ALB**

### Option C: AWS App Runner (Simplest)

1. **Connect to ECR or GitHub**
2. **Configure**:
   - Port: 8765
   - Environment variables as above
3. **Deploy**

## Frontend Deployment

### Option A: S3 + CloudFront

```bash
# Build frontend
cd gui_v2
npm run build

# Upload to S3
aws s3 sync dist/ s3://your-bucket-name --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

### Option B: AWS Amplify

1. Connect your repository
2. Configure build settings:
   ```yaml
   version: 1
   frontend:
     phases:
       preBuild:
         commands:
           - cd gui_v2
           - npm ci
       build:
         commands:
           - npm run build
     artifacts:
       baseDirectory: gui_v2/dist
       files:
         - '**/*'
   ```

## Session Management

### How Sessions Work

1. **Login**: Frontend calls `login` handler → Backend creates `UserContext` → Returns `session_id`
2. **Requests**: Frontend includes `session_id` in all requests
3. **Context**: Backend uses `session_id` to get correct `UserContext`
4. **Logout**: Frontend calls `logout` → Backend destroys session

### Session Storage

Currently, sessions are stored in memory. For production scaling:

- **Option A (Recommended)**: Sticky sessions with load balancer
- **Option B**: Redis session store (future enhancement)
- **Option C**: Migrate to stateless (Option A architecture)

## Monitoring

### Health Check

```bash
curl http://localhost:8765/health
# Response: {"status": "healthy", "mode": "web", "sessions": 5}
```

### Logs

```bash
# Docker
docker logs -f ecan-web

# Docker Compose
docker-compose -f docker-compose.web.yml logs -f ecan-backend
```

## Security Considerations

1. **Use HTTPS in production** - Configure SSL in Nginx or use AWS ALB
2. **Secure WebSocket** - Use `wss://` instead of `ws://`
3. **Authentication** - Validate tokens on every request
4. **Rate limiting** - Configure in Nginx or use AWS WAF
5. **Session timeout** - Default 24 hours, configurable

## Troubleshooting

### WebSocket Connection Failed

1. Check backend is running: `curl http://localhost:8765/health`
2. Check firewall/security groups allow port 8765
3. Check Nginx WebSocket proxy configuration

### Session Not Found

1. Ensure `session_id` is included in requests
2. Check session hasn't expired (24h default)
3. Verify backend didn't restart (sessions are in-memory)

### Handler Errors

1. Check backend logs for stack traces
2. Verify handlers are loaded: check startup logs
3. Test with simple handler like `ping`

## Migration from Desktop

The web deployment uses the same handlers as desktop mode. Key differences:

| Aspect | Desktop | Web |
|--------|---------|-----|
| Transport | Qt WebChannel | WebSocket |
| Context | `MainWindow` | `UserContext` |
| Users | Single | Multiple |
| State | Global | Per-session |

Handlers using `get_handler_context()` work in both modes automatically.
