import os
import base64
import logging
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, Enum as SQLEnum, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from contextlib import asynccontextmanager
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from passlib.context import CryptContext
from jose import JWTError, jwt
try:
    from pythonjsonlogger.json import JsonFormatter as _JsonFormatter
except ImportError:
    from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatter  # type: ignore

# Load environment variables
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./safesave.db")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# PayHero Configuration — uses Basic auth token directly
PAYHERO_API_KEY = os.getenv("PAYHERO_API_KEY")          # This IS the Basic auth token
PAYHERO_API_SECRET = os.getenv("PAYHERO_API_SECRET")    # kept for reference / fallback
PAYHERO_BASE_URL = os.getenv("PAYHERO_BASE_URL", "https://backend.payhero.co.ke/api/v2")
PAYHERO_WEBHOOK_SECRET = os.getenv("PAYHERO_WEBHOOK_SECRET")
PAYHERO_CHANNEL_ID = int(os.getenv("PAYHERO_CHANNEL_ID", "0"))

# Business Configuration
MIN_DEPOSIT = float(os.getenv("MIN_DEPOSIT", "100"))
MAX_DEPOSIT = float(os.getenv("MAX_DEPOSIT", "1000000"))
VIP_MINIMUM_DEPOSIT = float(os.getenv("VIP_MINIMUM_DEPOSIT", "5000"))

# ---------------------------------------------------------------------------
# Logging — structured JSON
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
_json_formatter = _JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
_file_handler = logging.FileHandler(os.getenv("LOG_FILE", "logs/safesave.log"))
_file_handler.setFormatter(_json_formatter)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_json_formatter)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    handlers=[_file_handler, _stream_handler],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    INTEREST = "interest"
    REFUND = "refund"

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    id_number = Column(String, unique=True, index=True)
    deposit_mode = Column(String, default="mpesa")
    password_hash = Column(String)
    is_vip = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Savings(Base):
    __tablename__ = "savings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    target_amount = Column(Float)
    duration_days = Column(Integer)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    current_amount = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    savings_id = Column(Integer, index=True)
    amount = Column(Float)
    currency = Column(String, default="KES")
    transaction_type = Column(SQLEnum(TransactionType), default=TransactionType.DEPOSIT)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    payhero_reference = Column(String, unique=True, index=True, nullable=True)  # reference returned by PayHero
    external_reference = Column(String, nullable=True, index=True)              # our reference sent to PayHero
    mpesa_receipt = Column(String, nullable=True)
    description = Column(String)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine, checkfirst=True)

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    phone: str
    id_number: str
    deposit_mode: str = "mpesa"
    password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    phone: str
    is_vip: bool
    is_active: bool
    created_at: datetime

class Login(BaseModel):
    email: EmailStr
    password: str

class SavingsCreate(BaseModel):
    target_amount: float = Field(..., gt=0)
    duration_days: int = Field(..., gt=0, le=1825)  # Max 5 years

    @field_validator("target_amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0)
    phone: str
    description: str = "Savings deposit"

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: float
    currency: str
    transaction_type: TransactionType
    status: TransactionStatus
    created_at: datetime

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload if payload.get("sub") else None
    except JWTError:
        return None

# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Current user dependency
# ---------------------------------------------------------------------------
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    email: str = payload.get("sub")
    if not email:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user

# ---------------------------------------------------------------------------
# PayHero API Client — corrected per official docs
# Endpoint:  POST /payments  (STK push)
# Auth:      Authorization: Basic <token>   (PAYHERO_API_KEY IS the Basic token)
# Payload:   amount, phone_number, channel_id, provider, external_reference, callback_url
# Response:  { success, status, reference, CheckoutRequestID }
#
# Transaction status: GET /transaction-status?reference=<reference>
# Response:  { status: "SUCCESS"|"FAILED"|"QUEUED", reference, ... }
#
# Webhook callback payload (sent to callback_url):
# { status: true/false, response: { ExternalReference, Status, MpesaReceiptNumber,
#   Amount, Phone, ResultCode, ResultDesc, CheckoutRequestID } }
# ---------------------------------------------------------------------------
class PayHeroClient:
    def __init__(self, api_key: str, base_url: str, channel_id: int):
        self.api_key = api_key          # This is the full Basic auth token
        self.base_url = base_url
        self.channel_id = channel_id

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def initiate_payment(
        self,
        phone: str,
        amount: float,
        external_reference: str,
        description: str,
    ) -> dict:
        """Initiate M-Pesa STK Push via PayHero POST /payments"""
        payload = {
            "amount": int(amount),          # PayHero expects integer
            "phone_number": phone,
            "channel_id": self.channel_id,
            "provider": "m-pesa",
            "external_reference": external_reference,
            "customer_name": description,
            "callback_url": os.getenv("WEBHOOK_URL", "https://yourdomain.com/webhooks/payhero"),
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"{self.base_url}/payments",
                    json=payload,
                    headers=self._get_headers(),
                )
            logger.info("PayHero STK push response", extra={"status_code": response.status_code, "body": response.text[:300]})
            if response.status_code in (200, 201):
                return response.json()
            logger.error("PayHero API error", extra={"status_code": response.status_code, "body": response.text})
            return {"error": response.text, "status_code": response.status_code}
        except Exception as exc:
            logger.error("PayHero API exception", extra={"error": str(exc)})
            return {"error": str(exc)}

    def verify_payment(self, reference: str) -> dict:
        """Check transaction status via GET /transaction-status?reference=<ref>"""
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    f"{self.base_url}/transaction-status",
                    params={"reference": reference},
                    headers=self._get_headers(),
                )
            if response.status_code == 200:
                return response.json()
            logger.error("PayHero verify error", extra={"status_code": response.status_code, "body": response.text})
            return {"error": response.text}
        except Exception as exc:
            logger.error("PayHero verify exception", extra={"error": str(exc)})
            return {"error": str(exc)}


pay_hero = PayHeroClient(PAYHERO_API_KEY, PAYHERO_BASE_URL, PAYHERO_CHANNEL_ID)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app_: FastAPI):
    logger.info("SafeSave API starting", extra={"environment": ENVIRONMENT, "debug": DEBUG})
    if not SECRET_KEY:
        logger.error("SECRET_KEY is not set — JWT will fail. Set SECRET_KEY in .env")
    if not PAYHERO_API_KEY:
        logger.warning("PAYHERO_API_KEY not configured — payments will fail")
    if PAYHERO_CHANNEL_ID == 0:
        logger.warning("PAYHERO_CHANNEL_ID is 0 — set correct channel ID in .env")
    if MAINTENANCE_MODE:
        logger.warning("MAINTENANCE MODE is ON — all endpoints except /health and /metrics are blocked")
    yield
    logger.info("SafeSave API shutting down")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SafeSave API",
    description="Production-ready savings management backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Maintenance mode middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    if MAINTENANCE_MODE and request.url.path not in ("/health", "/metrics"):
        return JSONResponse(
            status_code=503,
            content={"detail": "Service temporarily unavailable for maintenance. Please try again later."},
        )
    return await call_next(request)

# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if db_ok else "degraded",
        "environment": ENVIRONMENT,
        "database": "ok" if db_ok else "error",
        "maintenance_mode": MAINTENANCE_MODE,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    """Basic operational metrics"""
    total_users = db.query(User).count()
    active_savings = db.query(Savings).filter(Savings.is_active == True).count()
    pending_tx = db.query(Transaction).filter(Transaction.status == TransactionStatus.PENDING).count()
    completed_tx = db.query(Transaction).filter(Transaction.status == TransactionStatus.COMPLETED).count()
    failed_tx = db.query(Transaction).filter(Transaction.status == TransactionStatus.FAILED).count()
    return {
        "total_users": total_users,
        "active_savings_goals": active_savings,
        "transactions": {
            "pending": pending_tx,
            "completed": completed_tx,
            "failed": failed_tx,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    logger.info("Registration attempt", extra={"email": user.email})

    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.phone == user.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    if db.query(User).filter(User.id_number == user.id_number).first():
        raise HTTPException(status_code=400, detail="ID number already registered")

    new_user = User(
        email=user.email,
        phone=user.phone,
        id_number=user.id_number,
        deposit_mode=user.deposit_mode,
        password_hash=get_password_hash(user.password),
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info("User registered", extra={"email": user.email})
        return new_user
    except Exception as exc:
        db.rollback()
        logger.error("Registration error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/login")
def login(user: Login, db: Session = Depends(get_db)):
    """User login"""
    logger.info("Login attempt", extra={"email": user.email})
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        logger.warning("Failed login", extra={"email": user.email})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not db_user.is_active:
        raise HTTPException(status_code=401, detail="Account inactive")
    token = create_access_token(data={"sub": db_user.email})
    logger.info("Login successful", extra={"email": user.email})
    return {"access_token": token, "token_type": "bearer"}

# ---------------------------------------------------------------------------
# Savings Endpoints
# ---------------------------------------------------------------------------
@app.post("/savings", status_code=status.HTTP_201_CREATED)
def create_savings(
    savings: SavingsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a savings goal"""
    logger.info("Creating savings goal", extra={"email": current_user.email})

    if current_user.is_vip and savings.target_amount < VIP_MINIMUM_DEPOSIT:
        raise HTTPException(status_code=400, detail=f"VIP minimum deposit is {VIP_MINIMUM_DEPOSIT} KES")

    existing = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Complete or close existing savings goal first")

    end_date = datetime.utcnow() + timedelta(days=savings.duration_days)
    new_savings = Savings(
        user_id=current_user.id,
        target_amount=savings.target_amount,
        duration_days=savings.duration_days,
        end_date=end_date,
    )
    try:
        db.add(new_savings)
        db.commit()
        db.refresh(new_savings)
        logger.info("Savings goal created", extra={"email": current_user.email, "savings_id": new_savings.id})
        return {
            "id": new_savings.id,
            "target_amount": new_savings.target_amount,
            "duration_days": new_savings.duration_days,
            "start_date": new_savings.start_date,
            "end_date": new_savings.end_date,
            "message": "Savings goal created successfully",
        }
    except Exception as exc:
        db.rollback()
        logger.error("Error creating savings goal", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Failed to create savings goal")

@app.get("/savings/status")
def savings_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current savings status"""
    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True,
    ).first()
    if not savings:
        return {"message": "No active savings goal"}

    progress_percent = (savings.current_amount / savings.target_amount * 100) if savings.target_amount > 0 else 0
    days_remaining = (savings.end_date - datetime.utcnow()).days if savings.end_date else 0

    return {
        "id": savings.id,
        "target_amount": savings.target_amount,
        "current_amount": savings.current_amount,
        "remaining_amount": savings.target_amount - savings.current_amount,
        "progress_percent": round(progress_percent, 2),
        "duration_days": savings.duration_days,
        "days_remaining": max(0, days_remaining),
        "start_date": savings.start_date,
        "end_date": savings.end_date,
        "is_vip": current_user.is_vip,
    }

# ---------------------------------------------------------------------------
# Deposit Endpoint
# ---------------------------------------------------------------------------
@app.post("/deposit", status_code=status.HTTP_201_CREATED)
def deposit(
    deposit_req: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate a deposit via PayHero STK Push"""
    logger.info("Deposit request", extra={"email": current_user.email, "amount": deposit_req.amount})

    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True,
    ).first()
    if not savings:
        raise HTTPException(status_code=400, detail="Please create a savings goal first")

    if savings.current_amount + deposit_req.amount > savings.target_amount:
        remaining = savings.target_amount - savings.current_amount
        raise HTTPException(status_code=400, detail=f"Deposit would exceed target. Remaining: {remaining} KES")

    # Our unique reference sent to PayHero as external_reference
    external_ref = f"SAFE-{current_user.id}-{int(datetime.utcnow().timestamp())}"

    transaction = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=deposit_req.amount,
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        external_reference=external_ref,
        description=deposit_req.description,
    )
    try:
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create transaction record", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Deposit failed")

    # Initiate PayHero STK push (sync — PayHeroClient uses httpx.Client)
    payment_result = pay_hero.initiate_payment(
        phone=deposit_req.phone,
        amount=deposit_req.amount,
        external_reference=external_ref,
        description=deposit_req.description,
    )

    if "error" in payment_result:
        transaction.status = TransactionStatus.FAILED
        transaction.error_message = str(payment_result["error"])
        db.commit()
        logger.error("PayHero payment failed", extra={"error": payment_result["error"]})
        raise HTTPException(status_code=400, detail=f"Payment initiation failed: {payment_result['error']}")

    # Store the PayHero reference (UUID returned in response.reference)
    payhero_ref = payment_result.get("reference")
    if payhero_ref:
        transaction.payhero_reference = payhero_ref
        db.commit()

    logger.info("STK push initiated", extra={"external_ref": external_ref, "payhero_ref": payhero_ref})
    return {
        "transaction_id": transaction.id,
        "external_reference": external_ref,
        "payhero_reference": payhero_ref,
        "amount": deposit_req.amount,
        "status": "pending",
        "message": "Payment initiated. Please complete the M-Pesa prompt on your phone.",
    }

# ---------------------------------------------------------------------------
# Withdraw Endpoint
# ---------------------------------------------------------------------------
@app.post("/withdraw")
def withdraw(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Withdraw savings"""
    logger.info("Withdrawal request", extra={"email": current_user.email})

    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True,
    ).first()
    if not savings:
        raise HTTPException(status_code=400, detail="No active savings goal")

    now = datetime.utcnow()
    target_reached = savings.current_amount >= savings.target_amount
    duration_expired = now >= savings.end_date if savings.end_date else False

    if not target_reached and not duration_expired:
        days_remaining = (savings.end_date - now).days if savings.end_date else 0
        raise HTTPException(
            status_code=400,
            detail=f"Target not reached ({savings.current_amount}/{savings.target_amount}) and duration not expired ({days_remaining} days remaining)",
        )

    amount = savings.current_amount
    savings.current_amount = 0
    savings.is_active = False

    withdrawal_tx = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=amount,
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.COMPLETED,
        description="Savings withdrawal",
    )
    try:
        db.add(withdrawal_tx)
        db.commit()
        logger.info("Withdrawal successful", extra={"email": current_user.email, "amount": amount})
        return {"amount": amount, "status": "completed", "message": f"Successfully withdrew {amount} KES"}
    except Exception as exc:
        db.rollback()
        logger.error("Withdrawal error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Withdrawal failed")

# ---------------------------------------------------------------------------
# Transactions Endpoint
# ---------------------------------------------------------------------------
@app.get("/transactions")
def get_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Get transaction history"""
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(transactions),
        "transactions": [
            {
                "id": tx.id,
                "amount": tx.amount,
                "type": tx.transaction_type.value,
                "status": tx.status.value,
                "description": tx.description,
                "external_reference": tx.external_reference,
                "payhero_reference": tx.payhero_reference,
                "mpesa_receipt": tx.mpesa_receipt,
                "created_at": tx.created_at,
            }
            for tx in transactions
        ],
    }

# ---------------------------------------------------------------------------
# PayHero Webhook
# Callback payload structure (from PayHero docs):
# {
#   "status": true,
#   "response": {
#     "ExternalReference": "INV-009",       <- our external_reference
#     "Status": "Success",                  <- "Success" | "Failed"
#     "MpesaReceiptNumber": "SAE3YULR0Y",
#     "Amount": 10,
#     "Phone": "+254...",
#     "ResultCode": 0,
#     "ResultDesc": "...",
#     "CheckoutRequestID": "ws_CO_..."
#   }
# }
# ---------------------------------------------------------------------------
@app.post("/webhooks/payhero")
async def payhero_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle PayHero payment callbacks"""
    raw_body = await request.body()
    logger.info("PayHero webhook received", extra={"size": len(raw_body)})

    # Signature verification — PayHero sends X-Signature header
    x_signature = request.headers.get("x-signature") or request.headers.get("X-Signature")
    if PAYHERO_WEBHOOK_SECRET and x_signature:
        expected = hmac.new(
            PAYHERO_WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(x_signature, expected):
            logger.error("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        request_body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("Invalid webhook JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        # PayHero wraps the real data inside "response"
        response_data = request_body.get("response", {})
        overall_status = request_body.get("status", False)  # bool

        external_reference = response_data.get("ExternalReference")
        pay_status = response_data.get("Status", "")          # "Success" | "Failed"
        mpesa_receipt = response_data.get("MpesaReceiptNumber")
        result_code = response_data.get("ResultCode")
        result_desc = response_data.get("ResultDesc", "")

        logger.info(
            "Webhook data",
            extra={
                "external_reference": external_reference,
                "status": pay_status,
                "overall_status": overall_status,
                "result_code": result_code,
            },
        )

        # Find transaction by our external_reference
        transaction = db.query(Transaction).filter(
            Transaction.external_reference == external_reference
        ).first()

        if not transaction:
            logger.warning("Transaction not found for webhook", extra={"external_reference": external_reference})
            return {"status": "ok", "note": "Transaction not found"}

        if pay_status.lower() == "success" and result_code == 0:
            transaction.status = TransactionStatus.COMPLETED
            transaction.mpesa_receipt = mpesa_receipt

            savings = db.query(Savings).filter(Savings.id == transaction.savings_id).first()
            if savings:
                savings.current_amount += transaction.amount
                logger.info(
                    "Savings updated",
                    extra={"user_id": transaction.user_id, "new_amount": savings.current_amount},
                )
        elif pay_status.lower() == "failed" or (result_code is not None and result_code != 0):
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = result_desc or "Payment failed"
            logger.warning("Payment failed via webhook", extra={"reason": result_desc})
        else:
            # Still pending / queued
            transaction.status = TransactionStatus.PENDING

        transaction.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Webhook processed", extra={"external_reference": external_reference})
        return {"status": "ok"}

    except Exception as exc:
        logger.error("Webhook processing error", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}

# ---------------------------------------------------------------------------
# Profile & Customer Care
# ---------------------------------------------------------------------------
@app.get("/profile", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return current_user

@app.get("/customer-care")
def customer_care():
    """Get customer support information"""
    return {
        "email": os.getenv("CUSTOMER_SUPPORT_EMAIL", "support@safesave.com"),
        "phone": os.getenv("CUSTOMER_SUPPORT_PHONE", "+254712345678"),
        "company": os.getenv("COMPANY_NAME", "SafeSave Ltd"),
        "business_hours": "Mon-Fri 9AM-6PM (EAT)",
    }

# ---------------------------------------------------------------------------
# Transaction Reconciliation — manual trigger endpoint
# Checks all PENDING deposit transactions against PayHero and updates them
# ---------------------------------------------------------------------------
@app.post("/admin/reconcile")
def reconcile_pending_transactions(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Reconcile pending transactions against PayHero.
    Requires the Authorization header with a valid admin token.
    """
    # Reuse standard auth — only authenticated users can trigger this
    credentials_exception = HTTPException(status_code=401, detail="Unauthorized")
    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception
    payload = verify_token(authorization.split(" ")[1])
    if not payload:
        raise credentials_exception

    cutoff = datetime.utcnow() - timedelta(minutes=5)   # only check tx older than 5 min
    pending = (
        db.query(Transaction)
        .filter(
            Transaction.status == TransactionStatus.PENDING,
            Transaction.transaction_type == TransactionType.DEPOSIT,
            Transaction.created_at < cutoff,
            Transaction.external_reference.isnot(None),
        )
        .all()
    )

    updated = 0
    for tx in pending:
        result = pay_hero.verify_payment(tx.payhero_reference or tx.external_reference)
        if "error" in result:
            continue
        ph_status = result.get("status", "").upper()
        if ph_status == "SUCCESS":
            tx.status = TransactionStatus.COMPLETED
            savings = db.query(Savings).filter(Savings.id == tx.savings_id).first()
            if savings and tx.status != TransactionStatus.COMPLETED:
                savings.current_amount += tx.amount
            updated += 1
        elif ph_status == "FAILED":
            tx.status = TransactionStatus.FAILED
            tx.error_message = "Reconciliation: payment failed"
            updated += 1
        tx.updated_at = datetime.utcnow()

    db.commit()
    logger.info("Reconciliation complete", extra={"checked": len(pending), "updated": updated})
    return {"checked": len(pending), "updated": updated}

# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.error("ValueError", extra={"error": str(exc)})
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"error": str(exc), "path": str(request.url)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
