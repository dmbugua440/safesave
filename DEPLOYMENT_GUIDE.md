# SafeSave Backend - Production Deployment Guide

## Pre-Deployment Checklist

### Code & Dependencies
- [ ] All code committed to git
- [ ] No hardcoded secrets in code
- [ ] requirements.txt up to date
- [ ] Dependencies tested locally
- [ ] Security scan passed (bandit, safety)
- [ ] Tests passing locally
- [ ] API documentation complete

### Configuration
- [ ] .env file created and configured
- [ ] SECRET_KEY is strong (32+ random characters)
- [ ] DEBUG = false
- [ ] ENVIRONMENT = production
- [ ] All Pay Hero credentials configured
- [ ] Webhook URL is accessible and correct
- [ ] Database URL configured
- [ ] Logging configured

### Infrastructure
- [ ] Server/VPS provisioned
- [ ] Python 3.11+ installed
- [ ] PostgreSQL database created
- [ ] Domain name registered
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] Nginx installed and configured
- [ ] Docker and Docker Compose available (optional)

### Security
- [ ] HTTPS/SSL configured
- [ ] Firewall configured (allow 22, 80, 443 only)
- [ ] SSH key authentication enabled
- [ ] Password authentication disabled
- [ ] Database backups automated
- [ ] Log collection set up
- [ ] Monitoring and alerts configured

---

## Step 1: Server Setup

### 1.1 Initial Server Configuration (Ubuntu/Debian)

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl \
    wget \
    certbot \
    python3-certbot-nginx \
    ufw

# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw enable
```

### 1.2 Create Application User

```bash
# Create dedicated user for application
sudo useradd -m -s /bin/bash safesave
sudo usermod -aG sudo safesave

# Switch to application user
su - safesave
```

### 1.3 Set Up PostgreSQL

```bash
# Switch to postgres user
sudo su - postgres

# Create database and user
createdb safesave_db
createuser safesave_user
psql

# In PostgreSQL CLI:
ALTER USER safesave_user WITH ENCRYPTED PASSWORD 'strong_password';
GRANT ALL PRIVILEGES ON DATABASE safesave_db TO safesave_user;
\q

# Exit postgres user
exit
```

---

## Step 2: Application Setup

### 2.1 Clone or Upload Application

```bash
# Navigate to home directory
cd ~

# Option 1: Clone from Git (if using Git)
git clone https://github.com/yourusername/safesave-backend.git
cd safesave-backend

# Option 2: Upload via FTP/SCP
scp -r ./backend user@host:/home/safesave/
cd /home/safesave/backend
```

### 2.2 Create Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

### 2.3 Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env
```

**Essential .env values for production:**

```bash
ENVIRONMENT=production
DEBUG=false

SECRET_KEY=<generate-strong-key>
PAYHERO_API_KEY=<your-key>
PAYHERO_API_SECRET=<your-secret>
PAYHERO_WEBHOOK_SECRET=<your-webhook-secret>

DATABASE_URL=postgresql://safesave_user:password@localhost/safesave_db
FRONTEND_URL=https://yourdomain.com
WEBHOOK_URL=https://yourdomain.com/webhooks/payhero

ENVIRONMENT=production
LOG_LEVEL=INFO
```

### 2.4 Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Verify installation
python -c "import fastapi; print('FastAPI installed')"
```

### 2.5 Initialize Database

```bash
# Import environment variables
export $(cat .env | xargs)

# Test database connection
python -c "
from sqlalchemy import create_engine, text
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    print('Database connected!')
"
```

---

## Step 3: Configure Nginx

### 3.1 Create Nginx Configuration

```bash
# Copy nginx configuration
sudo cp nginx.conf /etc/nginx/nginx.conf

# Edit for your domain
sudo nano /etc/nginx/nginx.conf

# Change:
# server_name yourdomain.com www.yourdomain.com;
```

### 3.2 Generate SSL Certificate

```bash
# Generate Let's Encrypt certificate
sudo certbot certonly --standalone \
  -d yourdomain.com \
  -d www.yourdomain.com \
  -m admin@yourdomain.com \
  --agree-tos \
  --non-interactive

# Certificate path:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

### 3.3 Update Nginx Certificate Paths

```bash
# Update nginx.conf with certificate paths
sudo nano /etc/nginx/nginx.conf

# Verify syntax
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 3.4 Auto-Renew Certificate

```bash
# Test renewal (dry-run)
sudo certbot renew --dry-run

# Certificate auto-renews via systemd timer
# Verify timer
sudo systemctl list-timers snap.certbot.renew.timer
```

---

## Step 4: Create Systemd Service

### 4.1 Create Service File

```bash
# Create service file
sudo nano /etc/systemd/system/safesave.service
```

**Content:**

```ini
[Unit]
Description=SafeSave API Backend
After=network.target postgresql.service

[Service]
Type=notify
User=safesave
WorkingDirectory=/home/safesave/safesave-backend

# Environment
EnvironmentFile=/home/safesave/safesave-backend/.env
Environment="PATH=/home/safesave/safesave-backend/venv/bin"

# Start
ExecStart=/home/safesave/safesave-backend/venv/bin/gunicorn \
    main:app \
    -w 4 \
    -b 127.0.0.1:8000 \
    -k uvicorn.workers.UvicornWorker \
    --access-logfile /var/log/safesave/access.log \
    --error-logfile /var/log/safesave/error.log \
    --log-level info

# Restart
Restart=always
RestartSec=10

# Security
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
NoNewPrivileges=true
ReadWritePaths=/home/safesave/safesave-backend/logs

[Install]
WantedBy=multi-user.target
```

### 4.2 Create Logs Directory

```bash
# Create logs directory
sudo mkdir -p /var/log/safesave
sudo chown safesave:safesave /var/log/safesave
sudo chmod 755 /var/log/safesave
```

### 4.3 Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable safesave.service

# Start service
sudo systemctl start safesave.service

# Check status
sudo systemctl status safesave.service

# View logs
sudo journalctl -u safesave.service -f
```

---

## Step 5: Database Backups

### 5.1 Create Backup Script

```bash
# Create backup script
nano /home/safesave/backup.sh
```

**Content:**

```bash
#!/bin/bash

BACKUP_DIR="/home/safesave/backups"
DB_NAME="safesave_db"
DB_USER="safesave_user"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create backup
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/safesave_$TIMESTAMP.sql.gz"

# Keep only last 30 backups
find "$BACKUP_DIR" -name "safesave_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/safesave_$TIMESTAMP.sql.gz"
```

### 5.2 Make Script Executable

```bash
chmod +x /home/safesave/backup.sh
```

### 5.3 Schedule Daily Backup (Cron)

```bash
# Edit crontab
crontab -e

# Add (daily at 2 AM):
0 2 * * * /home/safesave/backup.sh >> /home/safesave/logs/backup.log 2>&1
```

---

## Step 6: Monitoring & Logging

### 6.1 Configure Log Rotation

```bash
# Create logrotate configuration
sudo nano /etc/logrotate.d/safesave
```

**Content:**

```
/var/log/safesave/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 safesave safesave
    sharedscripts
    postrotate
        systemctl reload safesave.service > /dev/null 2>&1 || true
    endscript
}
```

### 6.2 Set Up Monitoring

```bash
# Install monitoring tools
sudo apt-get install -y htop iotop nethogs

# Monitor running process
htop

# Monitor API health
curl -s http://localhost:8000/health | jq .
```

### 6.3 Set Up Alerts (Optional)

```bash
# Install Uptime Kuma or similar
# Or use cloud provider monitoring
# Example: AWS CloudWatch, Datadog, New Relic
```

---

## Step 7: Verification

### 7.1 Test API

```bash
# Health check
curl -s https://yourdomain.com/health | jq .

# Expected output:
# {
#   "status": "healthy",
#   "environment": "production"
# }

# API docs
curl -s https://yourdomain.com/docs | head -20
```

### 7.2 Test Database Connection

```bash
# SSH into server
ssh user@yourdomain.com

# Check service
sudo systemctl status safesave.service

# Check logs
sudo journalctl -u safesave.service -n 50

# Test database
sudo -u postgres psql -d safesave_db -c "SELECT 1;"
```

### 7.3 Test Pay Hero Webhook

```bash
# Configure webhook in Pay Hero dashboard to:
# https://yourdomain.com/webhooks/payhero

# Monitor logs during test payment
sudo tail -f /var/log/safesave/access.log
```

---

## Step 8: Post-Deployment

### 8.1 Update DNS

```bash
# Point your domain to server IP:
# yourdomain.com A record -> server.ip.address
# www.yourdomain.com CNAME -> yourdomain.com

# Test DNS resolution
nslookup yourdomain.com
```

### 8.2 Test HTTPS

```bash
# Verify SSL certificate
curl -vI https://yourdomain.com

# Check certificate rating
# https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
```

### 8.3 Set Up Monitoring Dashboard

- CloudFlare Analytics
- Google Cloud Monitoring
- AWS CloudWatch
- Grafana + Prometheus

### 8.4 Configure Email Alerts

```bash
# Set up payment failure alerts
# Order error alerts
# Authentication failure alerts
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u safesave.service -n 100

# Check port in use
sudo lsof -i :8000

# Verify venv
source /home/safesave/safesave-backend/venv/bin/activate
python -c "import fastapi"
```

### Database Connection Failed

```bash
# Test connection
psql -U safesave_user -d safesave_db -c "SELECT 1;"

# Check PostgreSQL status
sudo systemctl status postgresql

# Check credentials in .env
grep DATABASE_URL /home/safesave/safesave-backend/.env
```

### Nginx Not Working

```bash
# Test syntax
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Check logs
sudo tail -f /var/log/nginx/error.log
```

### SSL Certificate Issues

```bash
# Renew certificate
sudo certbot renew --force-renewal

# Check certificate expiration
echo | openssl s_client -servername yourdomain.com -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## Maintenance Tasks

### Weekly
- Check disk space: `df -h`
- Monitor logs for errors
- Verify backups completed

### Monthly
- Update system dependencies
- Review and rotate logs
- Test backup restoration
- Check certificate expiration

### Quarterly
- Update OS packages
- Update Python dependencies
- Security audit
- Performance review
- Disaster recovery test

### Annually
- Full security assessment
- Capacity planning
- Dependency audit
- Documentation update

---

## Rollback Procedure

If deployment fails:

```bash
# Stop current service
sudo systemctl stop safesave.service

# Restore previous backup
cd /home/safesave
git checkout previous_commit

# Restore database
pg_restore -U safesave_user safesave_db < backups/safesave_BACKUP_DATE.sql

# Restart service
sudo systemctl start safesave.service

# Verify
curl https://yourdomain.com/health
```

---

## Production Performance Tuning

### 1. Gunicorn Workers

```bash
# Calculate optimal workers
WORKERS=$((2 * $(nproc) + 1))
echo $WORKERS

# Update systemd service with WORKERS value
```

### 2. Database Connection Pool

```python
# In main.py (already configured)
# Adjust pool_size and max_overflow if needed
```

### 3. Nginx Optimization

```nginx
# Already optimized in nginx.conf:
# - Connection pooling
# - Gzip compression
# - Buffer optimization
# - Rate limiting
```

### 4. System Tuning

```bash
# Increase file descriptors
sudo sysctl -w fs.file-max=2097152

# Optimize TCP
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=4096
```

---

## Success Indicators

✅ Application Started
```bash
$ systemctl status safesave.service
● safesave.service - SafeSave API Backend
   Active: active (running)
```

✅ Health Check Passing
```bash
$ curl https://yourdomain.com/health
{"status":"healthy","environment":"production"}
```

✅ API Accessible
```bash
$ curl https://yourdomain.com/docs
# Returns Swagger UI page
```

✅ Database Connected
```bash
$ logs show successful queries
```

✅ SSL Certificate Valid
```bash
$ SSL Labs Grade A or A+
```

---

**Congratulations!** Your SafeSave Backend is now in production. 🎉

For support, refer to:
- PRODUCTION_SETUP.md
- Security.md
- API_DOCUMENTATION.md
