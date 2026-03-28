# SafeSave Backend - Production Setup Guide

## Overview
This is a production-ready FastAPI backend for the SafeSave savings application with full Pay Hero payment integration.

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 13+ (recommended for production instead of SQLite)
- Pay Hero account with API credentials
- Domain name for webhook configuration
- SSL certificate

## Initial Setup

### 1. Environment Configuration

Copy the example environment file and update with your values:

```bash
cp .env.example .env
```

Edit `.env` and update all required values:

```bash
# CRITICAL - Change these before production
SECRET_KEY=<generate-a-strong-random-key>
PAYHERO_API_KEY=<your-payhero-api-key>
PAYHERO_API_SECRET=<your-payhero-api-secret>
PAYHERO_WEBHOOK_SECRET=<your-webhook-secret>

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost/safesave_db

# Server
ENVIRONMENT=production
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Frontend
FRONTEND_URL=https://yourdomain.com

# Webhooks
WEBHOOK_URL=https://yourdomain.com/webhooks/payhero

# Support
CUSTOMER_SUPPORT_EMAIL=support@yourdomain.com
CUSTOMER_SUPPORT_PHONE=+254712345678
```

### 2. Generate Secure Secret Key

```python
import secrets
print(secrets.token_urlsafe(32))
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Database Setup

**For SQLite (Development/Testing):**
```bash
# Database automatically created on first run
```

**For PostgreSQL (Production - Recommended):**

```bash
# Create database
createdb safesave_db

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@localhost/safesave_db

# Run migrations if using Alembic
alembic upgrade head
```

### 5. Run Application

**Development:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production with Gunicorn:**
```bash
gunicorn main:app -w 4 -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker
```

API will be available at `http://localhost:8000`
API Documentation: `http://localhost:8000/docs`

## API Endpoints

### Authentication
- `POST /register` - Register new user
- `POST /login` - Login and get token
- `GET /profile` - Get user profile (requires token)

### Savings
- `POST /savings` - Create savings goal
- `GET /savings/status` - Get savings progress

### Transactions
- `POST /deposit` - Initiate deposit via Pay Hero
- `POST /withdraw` - Withdraw completed savings
- `GET /transactions` - Get transaction history

### Webhooks
- `POST /webhooks/payhero` - Pay Hero payment callbacks

### Utilities
- `GET /health` - Health check
- `GET /customer-care` - Support information

## Pay Hero Integration

### Payment Flow

1. User initiates deposit request
2. Backend creates transaction record (PENDING)
3. Backend calls Pay Hero API
4. Pay Hero sends payment prompt to user's phone
5. User completes payment
6. Pay Hero sends webhook callback
7. Backend verifies and updates transaction (COMPLETED/FAILED)
8. User's savings updated with deposit amount

### Webhook Configuration

In Pay Hero dashboard:
1. Go to Webhook Settings
2. Set webhook URL: `https://yourdomain.com/webhooks/payhero`
3. Verify webhook secret in your `.env` file

## Security Best Practices

✅ **Implemented:**
- JWT token authentication
- Bcrypt password hashing
- Password strength validation (min 8 chars, uppercase, digit)
- SQL injection prevention (SQLAlchemy ORM)
- CORS configuration
- Webhook signature verification
- Comprehensive logging
- Error handling with generic messages

⚠️ **Additional Recommendations:**

1. **Use HTTPS everywhere**
   ```bash
   # Install SSL certificate (Let's Encrypt recommended)
   # Use reverse proxy (Nginx/Apache)
   ```

2. **Database Security**
   - Use strong passwords
   - Restrict database access to server only
   - Regular backups
   - Use PostgreSQL instead of SQLite

3. **Rate Limiting**
   - Add rate limiting middleware for endpoints
   - Prevent brute force attacks on login

4. **API Keys**
   - Rotate Pay Hero credentials regularly
   - Use separate keys for sandbox/production
   - Never commit `.env` file to git

5. **Monitoring**
   - Set up log aggregation (ELK stack, CloudWatch)
   - Monitor error rates and performance
   - Set up alerts for critical errors

## Logging

Logs are stored in `logs/safesave.log`

View logs:
```bash
tail -f logs/safesave.log
```

Change log level in `.env`:
```
LOG_LEVEL=DEBUG   # For development
LOG_LEVEL=INFO    # For production
LOG_LEVEL=ERROR   # For critical only
```

## Database Migrations

Using Alembic for schema management:

```bash
# Initialize Alembic (if not done)
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Docker Deployment

See `Dockerfile` and `docker-compose.yml` for containerized deployment.

```bash
# Build image
docker build -t safesave-backend .

# Run container
docker run -p 8000:8000 --env-file .env safesave-backend

# Or use docker-compose
docker-compose up -d
```

## Nginx Configuration

Example reverse proxy configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /path/to/certificate.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Testing

Test the API with provided scripts or tools like Postman/curl:

```bash
# Health check
curl http://localhost:8000/health

# Register user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "phone": "+254712345678",
    "id_number": "12345678",
    "deposit_mode": "mpesa",
    "password": "SecurePass123",
    "confirm_password": "SecurePass123"
  }'

# Login
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'

# Get API docs
# Open browser: http://localhost:8000/docs
```

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000
# Kill process
kill -9 <PID>
```

### Database Connection Error
- Verify DATABASE_URL in .env
- Check PostgreSQL is running
- Verify database exists

### Pay Hero Payment Fails
- Verify API credentials in .env
- Check webhook URL is accessible
- Review logs in `logs/safesave.log`

### CORS Issues
- Verify FRONTEND_URL in .env
- Check allowed origins in main.py
- Ensure credentials are properly configured

## Performance Optimization

1. **Database Indexing** - Already configured on key fields
2. **Connection Pooling** - SQLAlchemy handles automatically
3. **Response Caching** - Implement with Redis for read-heavy endpoints
4. **Async Operations** - Pay Hero calls use async
5. **Database Optimization** - Use PostgreSQL indexes, regular VACUUM

## Scaling Considerations

1. **Horizontal Scaling** - Use load balancer (HAProxy, AWS ELB)
2. **Database** - Migrate to managed PostgreSQL (AWS RDS, Azure Database)
3. **Queue System** - Add Celery for async tasks
4. **Cache** - Implement Redis for session management
5. **Monitoring** - Use APM tools (New Relic, DataDog)

## Support & Maintenance

- Monitor logs daily
- Regular security updates
- Database backups (daily minimum)
- API response times and error rates
- User authentication failures
- Payment failures and retries

## Production Checklist

- [ ] SECRET_KEY is strong and unique
- [ ] Pay Hero credentials configured
- [ ] Database backup strategy in place
- [ ] HTTPS certificate installed
- [ ] Webhook URL accessible and correct
- [ ] Environment set to "production"
- [ ] DEBUG set to "false"
- [ ] Logging configured and monitored
- [ ] CORS origins correctly specified
- [ ] Rate limiting implemented
- [ ] Error monitoring set up
- [ ] Database optimized with indexes
- [ ] Regular backups automated

## License

Proprietary - SafeSave Limited
