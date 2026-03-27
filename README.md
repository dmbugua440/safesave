# SafeSave Backend API

A secure savings management application backend built with FastAPI and Python.

## Features

- **User Authentication**: Registration and login with JWT tokens
- **Savings Goals**: Create and manage savings targets with duration
- **Deposits**: Make deposits toward savings goals
- **Withdrawals**: Withdraw funds when target is reached or duration expires
- **VIP Accounts**: Special account tier with minimum deposit requirements (5000 KSH)
- **Customer Care**: Contact information for support
- **Secure Passwords**: Bcrypt hashing for password security

## Tech Stack

- **Framework**: FastAPI
- **Database**: SQLite (with SQLAlchemy ORM)
- **Authentication**: JWT (python-jose)
- **Server**: Uvicorn
- **Language**: Python 3.11

## Installation

### Prerequisites
- Python 3.11 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone https://github.com/dmbugua440/safesave.git
cd safesave
```

2. Create virtual environment (optional but recommended):
```bash
python -m venv venv
venv\Scripts\activate  # On Windows
source venv/bin/activate  # On macOS/Linux
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the server:
```bash
py -3.11 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /register` - Create new user account
- `POST /login` - Login and get JWT token

### Savings
- `POST /savings` - Create savings goal
- `GET /savings/status` - Check savings progress
- `POST /deposit` - Make deposit
- `POST /withdraw` - Withdraw funds

### Support
- `GET /customer-care` - Get support contact information

## Environment Configuration

Edit the following in `main.py` for production:
- `SECRET_KEY` (line 19) - Use strong random key
- Customer care email/phone (line 170-171)
- Database URL (line 7)

## Payment Integration

Currently using placeholder for Pay Hero payment processing.
To integrate Pay Hero:
1. Get API credentials from Pay Hero
2. Update the `/deposit` endpoint in `main.py`
3. Implement actual payment flow

## Development

The server runs with auto-reload enabled (`--reload` flag), so changes to src files will automatically reload the server.

## Next Steps

- Implement Pay Hero payment gateway integration
- Create mobile frontend (Android/iOS)
- Add user profile management
- Add savings history/audit logs
- Implement withdrawal request processing
- Add SMS/Email notifications

## License

Commercial - All rights reserved

## Author

SafeSave Development Team
