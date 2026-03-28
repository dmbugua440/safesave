# SafeSave API Documentation

## Overview

Production-ready REST API for the SafeSave savings application built with FastAPI.

**Base URL:** `http://localhost:8000` (or your domain)
**API Version:** 1.0.0
**Authentication:** Bearer token (JWT)

## Authentication

### Obtaining a Token

**Endpoint:** `POST /login`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Using the Token

Include in all protected endpoints:
```
Authorization: Bearer <access_token>
```

**Token Expiry:** 30 minutes (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)

---

## Public Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Description:** Check API availability and status

**Response:**
```json
{
  "status": "healthy",
  "environment": "production"
}
```

**Status Codes:**
- `200` - API is healthy

---

### 2. User Registration

**Endpoint:** `POST /register`

**Description:** Register a new user account

**Request Body:**
```json
{
  "email": "user@example.com",
  "phone": "+254712345678",
  "id_number": "12345678",
  "deposit_mode": "mpesa",
  "password": "SecurePass123",
  "confirm_password": "SecurePass123"
}
```

**Validation Rules:**
- Email must be valid format
- Phone must be valid (can include country code)
- Password must be at least 8 characters
- Password must contain uppercase letter and digit
- Passwords must match
- ID number must be unique
- Email and phone must be unique

**Response (201 Created):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": "+254712345678",
  "is_vip": false,
  "is_active": true,
  "created_at": "2024-03-28T10:30:00"
}
```

**Error Responses:**
```json
{
  "detail": "Email already registered"
}
```

**Status Codes:**
- `201` - User created successfully
- `400` - Validation error
- `500` - Server error

---

### 3. User Login

**Endpoint:** `POST /login`

**Description:** Authenticate user and obtain JWT token

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
```json
{
  "detail": "Invalid credentials"
}
```

**Status Codes:**
- `200` - Login successful
- `401` - Invalid credentials
- `500` - Server error

---

### 4. Customer Care

**Endpoint:** `GET /customer-care`

**Description:** Get customer support information

**Response:**
```json
{
  "email": "support@safesave.com",
  "phone": "+254712345678",
  "company": "SafeSave Ltd",
  "business_hours": "Mon-Fri 9AM-6PM (EAT)"
}
```

**Status Codes:**
- `200` - Success

---

## Protected Endpoints (Require Authentication)

### 5. Get User Profile

**Endpoint:** `GET /profile`

**Description:** Get current authenticated user's profile

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": "+254712345678",
  "is_vip": false,
  "is_active": true,
  "created_at": "2024-03-28T10:30:00"
}
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `500` - Server error

---

### 6. Create Savings Goal

**Endpoint:** `POST /savings`

**Description:** Create a new savings goal

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "target_amount": 10000,
  "duration_days": 90
}
```

**Validation Rules:**
- target_amount must be > 0 and within MIN_DEPOSIT (100) and MAX_DEPOSIT (1,000,000)
- duration_days must be > 0 and <= 1825 (5 years)
- User can only have one active savings goal at a time
- VIP users must meet minimum deposit requirement (5000 KES)

**Response (201 Created):**
```json
{
  "id": 1,
  "target_amount": 10000,
  "duration_days": 90,
  "start_date": "2024-03-28T10:30:00",
  "end_date": "2024-06-26T10:30:00",
  "message": "Savings goal created successfully"
}
```

**Error Responses:**
```json
{
  "detail": "VIP minimum deposit is 5000 KES"
}
```

**Status Codes:**
- `201` - Savings goal created
- `400` - Validation error
- `401` - Unauthorized
- `500` - Server error

---

### 7. Get Savings Status

**Endpoint:** `GET /savings/status`

**Description:** Get current savings goal progress

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "id": 1,
  "target_amount": 10000,
  "current_amount": 3500,
  "remaining_amount": 6500,
  "progress_percent": 35.0,
  "duration_days": 90,
  "days_remaining": 45,
  "start_date": "2024-03-28T10:30:00",
  "end_date": "2024-06-26T10:30:00",
  "is_vip": false
}
```

**Response (when no active goal):**
```json
{
  "message": "No active savings goal"
}
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `500` - Server error

---

### 8. Initiate Deposit

**Endpoint:** `POST /deposit`

**Description:** Initiate a deposit via Pay Hero

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "amount": 1000,
  "phone": "+254712345678",
  "description": "Monthly savings"
}
```

**Validation Rules:**
- amount must be > 0 and within MIN_DEPOSIT (100) and MAX_DEPOSIT (1,000,000)
- Deposit + current_amount must not exceed target_amount
- User must have active savings goal
- Phone format will be validated

**Response (201 Created):**
```json
{
  "transaction_id": 123,
  "reference": "SAFE-1-1711606200.123456",
  "amount": 1000,
  "status": "pending",
  "message": "Payment initiated. Please complete the payment on your phone."
}
```

**Error Responses:**
```json
{
  "detail": "Please create a savings goal first"
}
```

**Status Codes:**
- `201` - Payment initiated
- `400` - Validation error or no savings goal
- `401` - Unauthorized
- `500` - Server error

**Flow:**
1. User initiates deposit
2. Transaction record created with PENDING status
3. Pay Hero API called to request payment
4. User receives M-Pesa prompt on phone
5. User completes payment
6. Pay Hero sends webhook callback
7. Backend updates transaction status to COMPLETED
8. User's savings updated

---

### 9. Get Transaction History

**Endpoint:** `GET /transactions?limit=50`

**Description:** Get all transactions for current user

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
- `limit` (optional, default: 50) - Number of transactions to return

**Response (200 OK):**
```json
{
  "total": 5,
  "transactions": [
    {
      "id": 1,
      "amount": 1000,
      "type": "deposit",
      "status": "completed",
      "description": "Monthly savings",
      "created_at": "2024-03-28T10:30:00"
    },
    {
      "id": 2,
      "amount": 500,
      "type": "deposit",
      "status": "failed",
      "description": "Additional deposit",
      "created_at": "2024-03-27T15:20:00"
    }
  ]
}
```

**Transaction Types:**
- `deposit` - Money deposited into savings
- `withdrawal` - Money withdrawn from savings
- `interest` - Interest added to savings
- `refund` - Payment refunded

**Transaction Statuses:**
- `pending` - Transaction in progress
- `completed` - Transaction successful
- `failed` - Transaction failed
- `cancelled` - Transaction cancelled by user
- `refunded` - Transaction refunded

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `500` - Server error

---

### 10. Withdraw Savings

**Endpoint:** `POST /withdraw`

**Description:** Withdraw completed savings

**Headers:**
```
Authorization: Bearer <token>
```

**Conditions for Withdrawal:**
- Target amount reached, OR duration expired
- Active savings goal exists
- Current amount > 0

**Response (200 OK):**
```json
{
  "amount": 10000,
  "status": "completed",
  "message": "Successfully withdrew 10000 KES"
}
```

**Error Responses:**
```json
{
  "detail": "Target not reached ($3500/$10000) and duration not expired (45 days remaining)"
}
```

**Status Codes:**
- `200` - Withdrawal successful
- `400` - Withdrawal conditions not met
- `401` - Unauthorized
- `500` - Server error

---

## Webhooks

### Pay Hero Callback

**Endpoint:** `POST /webhooks/payhero`

**Description:** Receive payment status updates from Pay Hero

**Headers:**
```
Content-Type: application/json
X-Signature: <HMAC_SHA256_signature>
```

**Request Body:**
```json
{
  "transaction_id": "payhero_tx_123",
  "status": "completed",
  "reference": "SAFE-1-1711606200.123456",
  "amount": 1000,
  "phone": "+254712345678",
  "error_message": null
}
```

**Processing:**
1. Verify webhook signature
2. Find transaction by payhero_transaction_id
3. Update transaction status
4. If completed: update savings amount
5. Return acknowledgment

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- `200` - Webhook processed
- `401` - Invalid signature
- `500` - Processing error

**Security:**
- Always verify X-Signature header
- Signature = HMAC-SHA256(payload, webhook_secret)
- Drop unsigned webhooks

---

## Error Codes

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created |
| 400 | Bad Request | Validation or request error |
| 401 | Unauthorized | Missing or invalid token |
| 404 | Not Found | Resource not found |
| 422 | Validation Error | Invalid request format |
| 500 | Server Error | Internal server error |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Rate Limiting

Current limits (recommended):
- `/login` - 5 attempts per 15 minutes
- `/register` - 3 attempts per hour
- `/deposit` - 10 per hour
- Other endpoints - 100 per hour

---

## Data Types

### User Object
```json
{
  "id": "integer",
  "email": "string (email format)",
  "phone": "string (phone number)",
  "is_vip": "boolean",
  "is_active": "boolean",
  "created_at": "ISO 8601 datetime"
}
```

### Transaction Object
```json
{
  "id": "integer",
  "amount": "float",
  "type": "enum: deposit|withdrawal|interest|refund",
  "status": "enum: pending|completed|failed|cancelled|refunded",
  "description": "string",
  "created_at": "ISO 8601 datetime"
}
```

### Savings Goal Object
```json
{
  "id": "integer",
  "target_amount": "float",
  "current_amount": "float",
  "duration_days": "integer",
  "progress_percent": "float",
  "start_date": "ISO 8601 datetime",
  "end_date": "ISO 8601 datetime",
  "days_remaining": "integer"
}
```

---

## Testing

### Using cURL

```bash
# Register
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "phone": "+254712345678",
    "id_number": "12345678",
    "deposit_mode": "mpesa",
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

# Create savings (use token from login)
curl -X POST http://localhost:8000/savings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_amount": 10000,
    "duration_days": 90
  }'

# Get status
curl -X GET http://localhost:8000/savings/status \
  -H "Authorization: Bearer <token>"
```

### Using Postman

1. Open Postman
2. Create new collection "SafeSave API"
3. Import environment from API docs
4. Use provided request templates
5. Set token in Authorization tab

### Using FastAPI Docs

1. Navigate to `http://localhost:8000/docs`
2. Interactive Swagger UI
3. Try endpoints directly
4. See request/response examples

---

## Version History

### v1.0.0 (Current)
- Initial production release
- Full Pay Hero integration
- JWT authentication
- Transaction tracking
- Webhook support
- Comprehensive logging
- CORS support

---

## Support

For API support:
- Check logs at `logs/safesave.log`
- Review error messages in responses
- Verify .env configuration
- Check Pay Hero API status
- Review PRODUCTION_SETUP.md guide

