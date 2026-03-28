# SafeSave Backend API

A production-ready savings management backend built with FastAPI and Python, designed for the Kenyan market with M-Pesa payments via PayHero.

**Live API:** https://safesave-81bf.onrender.com  
**Docs:** https://safesave-81bf.onrender.com/docs

---

## Features

- JWT authentication with email verification and password reset
- Multiple savings goals per user with categories
- M-Pesa deposits via PayHero STK Push
- M-Pesa withdrawals back to user phone
- Automatic email notifications on deposit and goal completion
- Admin dashboard (list users, transactions, suspend/activate accounts)
- Transaction reconciliation for pending payments
- Maintenance mode, health check, and metrics endpoints
- Structured JSON logging
- Docker + Nginx + PostgreSQL deployment ready

## Tech Stack

- FastAPI + Python 3.11
- SQLAlchemy ORM (SQLite dev / PostgreSQL production)
- Alembic migrations
- JWT (python-jose) + bcrypt passwords
- PayHero API (M-Pesa STK Push + withdrawals)
- Gunicorn + Uvicorn workers
- Docker + Docker Compose + Nginx

---

## Quick Start

```bash
git clone https://github.com/dmbugua440/safesave.git
cd safesave
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp .env.example .env         # fill in your values
python -m alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000/docs for interactive API docs.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | SQLite (dev) or PostgreSQL (production) |
| `PAYHERO_API_KEY` | Basic auth token from PayHero dashboard |
| `PAYHERO_CHANNEL_ID` | Your PayHero payment channel ID |
| `PAYHERO_BASE_URL` | `https://backend.payhero.co.ke/api/v2` |
| `WEBHOOK_URL` | Public URL for PayHero callbacks e.g. `https://yourdomain.com/webhooks/payhero` |
| `SMTP_USERNAME` | Gmail address for sending emails |
| `SMTP_PASSWORD` | Gmail app password |
| `FRONTEND_URL` | Frontend URL for email links |

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register new user (sends verification email) |
| GET | `/verify-email?token=` | Verify email address |
| POST | `/login` | Login, returns JWT token |
| POST | `/forgot-password` | Request password reset email |
| POST | `/reset-password` | Reset password with token |

### Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/profile` | Get current user profile |
| PATCH | `/profile` | Update phone, name, deposit mode |
| DELETE | `/profile` | Deactivate account |

### Savings
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/savings` | Create a savings goal |
| GET | `/savings` | List all savings goals |
| GET | `/savings/{id}` | Get specific savings goal |
| GET | `/savings/status` | Get first active goal (backwards compat) |

Savings categories: `general`, `school_fees`, `rent`, `emergency`, `car`, `house`, `land`, `party`

### Payments
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/deposit` | Initiate M-Pesa STK Push deposit |
| POST | `/withdraw` | Withdraw savings to M-Pesa |
| GET | `/transactions` | Transaction history (filter by `savings_id`) |

### Webhooks
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhooks/payhero` | PayHero payment callback |

### Admin (VIP users only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/users` | List all users |
| GET | `/admin/transactions` | List all transactions |
| PATCH | `/admin/users/{id}/suspend` | Suspend a user |
| PATCH | `/admin/users/{id}/activate` | Activate a user |
| POST | `/admin/reconcile` | Reconcile pending transactions |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Operational metrics |
| GET | `/customer-care` | Support contact info |

---

## Deposit Flow

1. User calls `POST /deposit` with `savings_id`, `amount`, `phone`
2. Backend creates a PENDING transaction and calls PayHero `POST /payments`
3. User receives M-Pesa STK Push prompt on their phone
4. User enters M-Pesa PIN
5. PayHero sends callback to `/webhooks/payhero`
6. Backend updates transaction to COMPLETED and adds amount to savings
7. User receives email confirmation

## Withdrawal Flow

1. User calls `POST /withdraw` with `savings_id` and `phone`
2. Backend checks target reached or duration expired
3. Backend calls PayHero withdrawal API to send funds to user's M-Pesa
4. Savings goal is closed

---

## Running Tests

```bash
pytest tests/ -v
```

27 tests covering all endpoints including full webhook flow.

---

## Deployment (Render)

1. Push repo to GitHub
2. Go to Render → New → Blueprint
3. Connect `dmbugua440/safesave` — Render reads `render.yaml` automatically
4. Add secret env vars: `PAYHERO_API_KEY`, `PAYHERO_API_SECRET`, `PAYHERO_CHANNEL_ID`
5. Deploy

Or deploy manually with Docker:

```bash
docker-compose up --build
```

---

## License

Commercial — All rights reserved  
© SafeSave Ltd
