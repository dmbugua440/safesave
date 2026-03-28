# SafeSave Backend Configuration

This directory contains all configuration for the production-ready SafeSave backend API.

## Quick Start

### 1. First Time Setup

```bash
# On Linux/macOS
bash run.sh

# On Windows
run.bat
```

### 2. Configure Pay Hero

Before running, ensure you have:
- Pay Hero API key
- Pay Hero API secret
- Webhook secret key

Update `.env` file with your credentials.

## Files Overview

### Core Application
- `main.py` - FastAPI application with all endpoints
- `requirements.txt` - Python dependencies

### Configuration
- `.env` - Production configuration (DO NOT commit to git)
- `.env.example` - Template for .env file

### Deployment
- `Dockerfile` - Docker image definition
- `docker-compose.yml` - Multi-service orchestration
- `run.sh` - Linux/macOS startup script
- `run.bat` - Windows startup script

### Documentation
- `PRODUCTION_SETUP.md` - Complete production setup guide
- `API_DOCUMENTATION.md` - API endpoints reference
- `SECURITY.md` - Security configuration and best practices
- `DEPLOYMENT_GUIDE.md` - Step-by-step deployment guide

## Database Models

### Users Table
```sql
- id (Integer, Primary Key)
- email (String, Unique)
- phone (String, Unique)
- id_number (String, Unique)
- deposit_mode (String)
- password_hash (String)
- is_vip (Boolean)
- is_active (Boolean)
- created_at (DateTime)
- updated_at (DateTime)
```

### Savings Table
```sql
- id (Integer, Primary Key)
- user_id (Integer, Foreign Key)
- target_amount (Float)
- duration_days (Integer)
- current_amount (Float)
- is_active (Boolean)
- created_at (DateTime)
- updated_at (DateTime)
- end_date (DateTime)
```

### Transactions Table
```sql
- id (Integer, Primary Key)
- user_id (Integer, Foreign Key)
- savings_id (Integer, Foreign Key)
- amount (Float)
- currency (String)
- transaction_type (Enum: deposit, withdrawal, interest, refund)
- status (Enum: pending, completed, failed, cancelled, refunded)
- payhero_transaction_id (String, Unique)
- payhero_reference (String)
- description (String)
- error_message (String)
- created_at (DateTime)
- updated_at (DateTime)
```

## API Endpoints Summary

### Public Endpoints (No Auth Required)
- `GET /health` - Health check
- `POST /register` - User registration
- `POST /login` - User login
- `GET /customer-care` - Support info

### Protected Endpoints (Authorization Header Required)
- `GET /profile` - User profile
- `POST /savings` - Create savings goal
- `GET /savings/status` - Savings progress
- `POST /deposit` - Initiate deposit
- `POST /withdraw` - Withdraw from savings
- `GET /transactions` - Transaction history

### Webhook Endpoints
- `POST /webhooks/payhero` - Pay Hero payment callbacks

## Authentication

All protected endpoints require Bearer token authentication:

```bash
Authorization: Bearer <token>
```

Tokens are obtained from `/login` endpoint.

## Pay Hero Integration Details

### Supported Operations
- Initiate payment (M-Pesa)
- Verify payment status
- Receive payment callbacks

### Payment Status Flow
1. PENDING - Payment initiated, waiting for user action
2. COMPLETED - Payment successful, funds received
3. FAILED - Payment failed
4. CANCELLED - User cancelled payment
5. REFUNDED - Payment refunded

### Webhook Structure
```json
{
  "transaction_id": "string",
  "status": "completed|failed|pending",
  "reference": "SAFE-123-456",
  "error_message": "optional",
  "amount": 1000,
  "phone": "+254712345678"
}
```

## Environment Variables

### Required
- `SECRET_KEY` - JWT secret for token signing
- `PAYHERO_API_KEY` - Pay Hero API key
- `PAYHERO_API_SECRET` - Pay Hero API secret
- `PAYHERO_WEBHOOK_SECRET` - Webhook signature secret

### Optional (with defaults)
- `ENVIRONMENT` - "production" or "development" (default: production)
- `DEBUG` - "true" or "false" (default: false)
- `PORT` - Server port (default: 8000)
- `DATABASE_URL` - Database connection string
- `FRONTEND_URL` - Frontend domain for CORS
- `LOG_LEVEL` - Logging level (default: INFO)

## Logging

Logs are written to:
- Console output
- `logs/safesave.log` - Main application log
- `logs/access.log` - HTTP request access log (Gunicorn)
- `logs/error.log` - Error log (Gunicorn)

View logs:
```bash
tail -f logs/safesave.log
```

## Performance Considerations

- Database connection pooling enabled
- Transaction indexing for fast queries
- Async payment operations
- Response compression
- Webhook signature verification

## Security Features

✅ Implemented:
- JWT token authentication
- Bcrypt password hashing
- Password strength requirements
- CORS configuration
- Webhook signature verification
- SQL injection prevention
- Comprehensive error handling
- Logging and audit trails

⚠️ Recommended:
- HTTPS/SSL everywhere
- Rate limiting on endpoints
- Database encryption at rest
- Regular security audits
- API key rotation
- Database backup strategy

## Monitoring

Set up monitoring for:
1. API response times
2. Error rates
3. Database connection pool
4. Payment failure rates
5. Transaction volumes
6. Webhook failures
7. Authentication failures

## Testing Environments

### Sandbox (Pay Hero)
```
PAYHERO_BASE_URL=https://sandbox.payhero.io/api/v2
```

### Production (Pay Hero)
```
PAYHERO_BASE_URL=https://api.payhero.io/api/v2
```

## Support

For issues or questions:
- Check `logs/safesave.log` for error details
- Review `SECURITY.md` for security questions
- See `PRODUCTION_SETUP.md` for deployment help
- Refer `API_DOCUMENTATION.md` for API usage

## License

Proprietary - SafeSave Limited
