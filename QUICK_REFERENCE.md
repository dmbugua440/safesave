# SafeSave Backend - Quick Reference

## 🚀 Startup Commands

```bash
# Windows
run.bat

# Linux/macOS
bash run.sh

# Docker (Recommended for Production)
docker-compose up -d

# Manual with Gunicorn
gunicorn main:app -w 4 -b 0.0.0.0:8000
```

## 📍 Important URLs

```
http://localhost:8000          # API base URL
http://localhost:8000/docs     # Interactive API docs (Swagger)
http://localhost:8000/health   # Health check
https://yourdomain.com         # Production URL
```

## 🔑 .env Critical Variables

```bash
# MUST change these
SECRET_KEY=<generate-random-32-chars>
PAYHERO_API_KEY=<your-api-key>
PAYHERO_API_SECRET=<your-api-secret>
PAYHERO_WEBHOOK_SECRET=<your-webhook-secret>

# MUST set for production
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://user:pass@host/db
FRONTEND_URL=https://yourdomain.com
WEBHOOK_URL=https://yourdomain.com/webhooks/payhero
```

## 📚 Documentation Map

| Topic | File |
|-------|------|
| Start Here | IMPLEMENTATION_SUMMARY.md |
| API Reference | API_DOCUMENTATION.md |
| Setup & Config | PRODUCTION_SETUP.md |
| Deploy to Server | DEPLOYMENT_GUIDE.md |
| Security | SECURITY.md |
| File Overview | CONFIG.md |

## 🔌 API Endpoints Cheat Sheet

### Public (No Auth)
```
POST   /register              # Create account
POST   /login                 # Get token
GET    /health                # Check status
GET    /customer-care         # Support info
```

### Protected (Require Token)
```
GET    /profile               # User info
POST   /savings               # Create savings goal
GET    /savings/status        # Savings progress
POST   /deposit               # Start payment
POST   /withdraw              # Withdraw funds
GET    /transactions          # Payment history
```

### Webhooks
```
POST   /webhooks/payhero      # Pay Hero callbacks
```

## 🔐 Common Configurations

### Development
```bash
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite:///./safesave.db
PAYHERO_BASE_URL=https://sandbox.payhero.io/api/v2
```

### Production
```bash
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://user:pass@host/db
PAYHERO_BASE_URL=https://api.payhero.io/api/v2
```

## 🧪 Testing Commands

```bash
# Health check
curl http://localhost:8000/health

# Register user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "phone": "+254712345678",
    "id_number": "12345678",
    "password": "TestPass123",
    "confirm_password": "TestPass123"
  }'

# Login
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123"
  }'

# Create savings (substitute TOKEN from login)
curl -X POST http://localhost:8000/savings \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_amount": 10000,
    "duration_days": 90
  }'

# Get savings status
curl -X GET http://localhost:8000/savings/status \
  -H "Authorization: Bearer TOKEN"
```

## 📋 Files Structure

```
backend/
├── main.py                    # Application code (900+ lines)
├── requirements.txt           # Dependencies
├── .env                       # Configuration (DO NOT COMMIT)
├── .env.example               # Configuration template
├── .gitignore                 # Git ignore rules
│
├── Dockerfile                 # Docker image
├── docker-compose.yml         # Multi-service setup
├── nginx.conf                 # Reverse proxy config
│
├── run.sh                     # Linux/macOS startup
├── run.bat                    # Windows startup
│
├── IMPLEMENTATION_SUMMARY.md  # This project summary
├── API_DOCUMENTATION.md       # Complete API reference
├── PRODUCTION_SETUP.md        # Setup guide
├── DEPLOYMENT_GUIDE.md        # Deployment steps
├── SECURITY.md                # Security guide
├── CONFIG.md                  # Configuration guide
├── README.md                  # Project info
└── INSTALLATION.md            # Installation steps
```

## 🆘 Troubleshooting Quick Fixes

### Port 8000 Already in Use
```bash
# Find process
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Database Connection Error
```bash
# Verify .env
grep DATABASE_URL .env

# Test PostgreSQL
psql -U user -d database -c "SELECT 1;"
```

### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Check Python version
python --version  # Should be 3.11+
```

### Permission Denied on run.sh
```bash
chmod +x run.sh
./run.sh
```

## 🔄 Deployment Checklist

- [ ] .env created with all secrets
- [ ] Database configured and tested
- [ ] SECRET_KEY is strong (32+ chars)
- [ ] DEBUG = false
- [ ] ENVIRONMENT = production
- [ ] HTTPS/SSL certificate ready
- [ ] Pay Hero credentials configured
- [ ] Webhook URL accessible
- [ ] Dependencies installed
- [ ] Logs directory exists
- [ ] Database backups automated
- [ ] Nginx/reverse proxy configured

## 💾 Database Commands

```bash
# PostgreSQL
psql -U safesave_user -d safesave_db

# Backup
pg_dump -U safesave_user safesave_db > backup.sql

# Restore
pg_restore -U safesave_user safesave_db < backup.sql

# SQLite (for development)
sqlite3 safesave.db ".schema"
```

## 📊 Monitoring Commands

```bash
# View logs
tail -f logs/safesave.log

# View specific error
grep ERROR logs/safesave.log

# Count requests
wc -l logs/access.log

# Monitor in real-time
watch -n 1 'tail logs/safesave.log'
```

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Rebuild image
docker-compose build --no-cache

# Execute command in container
docker-compose exec backend python -c "import fastapi"

# Remove old containers
docker-compose rm -f
```

## 🔧 Performance Tuning

### Gunicorn Workers (in systemd service)
```ini
# For 4 CPU cores: use 9 workers (2*4 + 1)
ExecStart=gunicorn main:app -w 9
```

### Database Connection Pool
```python
# In main.py (already optimized)
# pool_size=20 (default)
# max_overflow=10 (default)
```

### Nginx Buffer Sizes
```nginx
# Already optimized in nginx.conf
proxy_buffer_size 4k;
proxy_buffers 8 4k;
```

## 🔐 Secret Generation

```python
# Generate SECRET_KEY
import secrets
print(secrets.token_urlsafe(32))

# Generate webhook secret
import secrets
print(secrets.token_hex(32))
```

## 📞 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Port 8000 in use | `lsof -i :8000` → kill process |
| No database | Check DATABASE_URL in .env |
| Imports fail | `pip install -r requirements.txt` |
| .env not found | `cp .env.example .env` |
| Permission denied | `chmod +x run.sh` |
| SSL error | Verify certificate path in nginx.conf |

## 🚀 Production Deployment

**5-Step Quick Deploy:**

```bash
# 1. Configure
cp .env.example .env
# Edit .env with your values

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup database
# Create PostgreSQL database

# 4. Deploy
docker-compose up -d

# 5. Verify
curl https://yourdomain.com/health
```

## 📈 API Usage Example

```bash
#!/bin/bash

# Register
REGISTER=$(curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "phone": "+254712345678",
    "id_number": "12345678",
    "password": "SecurePass123",
    "confirm_password": "SecurePass123"
  }')

echo "Registration: $REGISTER"

# Login
LOGIN=$(curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }')

TOKEN=$(echo $LOGIN | jq -r '.access_token')
echo "Token: $TOKEN"

# Create savings
curl -s -X POST http://localhost:8000/savings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_amount": 10000,
    "duration_days": 90
  }' | jq .
```

## 🎓 Key Concepts

**JWT Token**
- Short-lived (30 min default)
- Use in Authorization header: `Bearer <token>`
- Obtained from `/login` endpoint

**Transaction Status**
- PENDING: Awaiting payment confirmation
- COMPLETED: Payment successful
- FAILED: Payment failed
- REFUNDED: Payment refunded

**Webhook**
- Called by Pay Hero when payment completes
- Must verify signature (HMAC-SHA256)
- Updates transaction and savings automatically

---

**Version:** 1.0.0
**Last Updated:** March 28, 2024
**Status:** Production Ready ✅
