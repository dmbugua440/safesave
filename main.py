import os
import random
import string
import base64
import logging
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, Enum as SQLEnum, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from passlib.context import CryptContext
from jose import JWTError, jwt
try:
    from pythonjsonlogger.json import JsonFormatter as _JsonFormatter
except ImportError:
    from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatter  # type: ignore

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

PAYHERO_API_KEY = os.getenv("PAYHERO_API_KEY")
PAYHERO_BASE_URL = os.getenv("PAYHERO_BASE_URL", "https://backend.payhero.co.ke/api/v2")
PAYHERO_WEBHOOK_SECRET = os.getenv("PAYHERO_WEBHOOK_SECRET")
PAYHERO_CHANNEL_ID = int(os.getenv("PAYHERO_CHANNEL_ID", "0"))

MIN_DEPOSIT = float(os.getenv("MIN_DEPOSIT", "100"))
MAX_DEPOSIT = float(os.getenv("MAX_DEPOSIT", "1000000"))
VIP_MINIMUM_DEPOSIT = float(os.getenv("VIP_MINIMUM_DEPOSIT", "5000"))

# Email config
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@safesave.com")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
_json_formatter = _JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
_file_handler = logging.FileHandler(os.getenv("LOG_FILE", "logs/safesave.log"))
_file_handler.setFormatter(_json_formatter)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_json_formatter)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[_file_handler, _stream_handler])
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

class SavingsCategory(str, Enum):
    GENERAL = "general"
    SCHOOL_FEES = "school_fees"
    RENT = "rent"
    EMERGENCY = "emergency"
    CAR = "car"
    HOUSE = "house"
    LAND = "land"
    PARTY = "party"

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    id_number = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    deposit_mode = Column(String, default="mpesa")
    password_hash = Column(String)
    is_vip = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True)
    password_reset_token = Column(String, nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Savings(Base):
    __tablename__ = "savings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    name = Column(String, nullable=True)
    category = Column(SQLEnum(SavingsCategory), default=SavingsCategory.GENERAL)
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
    payhero_reference = Column(String, unique=True, index=True, nullable=True)
    external_reference = Column(String, nullable=True, index=True)
    mpesa_receipt = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    description = Column(String)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine, checkfirst=True)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    phone: str
    id_number: str
    full_name: Optional[str] = None
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
    full_name: Optional[str]
    is_vip: bool
    is_active: bool
    is_email_verified: bool
    created_at: datetime

class UserUpdate(BaseModel):
    phone: Optional[str] = None
    full_name: Optional[str] = None
    deposit_mode: Optional[str] = None

class Login(BaseModel):
    email: EmailStr
    password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetConfirm":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

class SavingsCreate(BaseModel):
    name: Optional[str] = None
    category: SavingsCategory = SavingsCategory.GENERAL
    target_amount: float = Field(..., gt=0)
    duration_days: int = Field(..., gt=0, le=1825)

    @field_validator("target_amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class DepositRequest(BaseModel):
    savings_id: Optional[int] = None   # if None, uses the first active goal
    amount: float = Field(..., gt=0)
    phone: str
    description: str = "Savings deposit"

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class WithdrawRequest(BaseModel):
    savings_id: int
    phone: str  # M-Pesa phone to receive funds

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

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

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

def generate_token(length: int = 32) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    exc = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    if not authorization or not authorization.startswith("Bearer "):
        raise exc
    payload = verify_token(authorization.split(" ")[1])
    if not payload:
        raise exc
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise exc
    return user

def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------
def send_email(to: str, subject: str, body: str) -> bool:
    """Send email via SMTP. Returns True on success, False on failure."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("Email not configured — skipping send", extra={"to": to, "subject": subject})
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USERNAME
        msg["To"] = to
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, to, msg.as_string())
        logger.info("Email sent", extra={"to": to, "subject": subject})
        return True
    except Exception as exc:
        logger.error("Email send failed", extra={"to": to, "error": str(exc)})
        return False

def send_verification_email(user_email: str, token: str):
    verify_url = f"{FRONTEND_URL}/verify-email?token={token}"
    body = f"""
    <h2>Welcome to SafeSave!</h2>
    <p>Please verify your email address by clicking the link below:</p>
    <a href="{verify_url}" style="background:#6c63ff;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;">Verify Email</a>
    <p>This link expires in 24 hours.</p>
    <p>If you did not create a SafeSave account, ignore this email.</p>
    """
    send_email(user_email, "Verify your SafeSave email", body)

def send_password_reset_email(user_email: str, token: str):
    reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
    body = f"""
    <h2>SafeSave Password Reset</h2>
    <p>Click the link below to reset your password:</p>
    <a href="{reset_url}" style="background:#6c63ff;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;">Reset Password</a>
    <p>This link expires in 1 hour. If you did not request a reset, ignore this email.</p>
    """
    send_email(user_email, "Reset your SafeSave password", body)

def send_deposit_success_email(user_email: str, full_name: str, amount: float, mpesa_receipt: str, savings_name: str):
    body = f"""
    <h2>Deposit Successful 🎉</h2>
    <p>Hi {full_name or 'there'},</p>
    <p>Your deposit of <strong>KES {amount:,.0f}</strong> to your <strong>{savings_name}</strong> savings goal was successful.</p>
    <p><strong>M-Pesa Receipt:</strong> {mpesa_receipt}</p>
    <p>Keep saving — you're one step closer to your goal!</p>
    <p>— The SafeSave Team</p>
    """
    send_email(user_email, "Deposit Confirmed — SafeSave", body)

def send_goal_reached_email(user_email: str, full_name: str, savings_name: str, amount: float):
    body = f"""
    <h2>Congratulations! 🏆 You've reached your savings goal!</h2>
    <p>Hi {full_name or 'there'},</p>
    <p>Amazing news — you have successfully saved <strong>KES {amount:,.0f}</strong> for your <strong>{savings_name}</strong> goal!</p>
    <p>You can now withdraw your funds from the SafeSave app.</p>
    <p>Well done for staying committed. We're proud of you!</p>
    <p>— The SafeSave Team</p>
    """
    send_email(user_email, "🏆 Savings Goal Reached — SafeSave", body)

# ---------------------------------------------------------------------------
# PayHero Client
# ---------------------------------------------------------------------------
class PayHeroClient:
    def __init__(self, api_key: str, base_url: str, channel_id: int):
        self.api_key = api_key
        self.base_url = base_url
        self.channel_id = channel_id

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def initiate_payment(self, phone: str, amount: float, external_reference: str, description: str) -> dict:
        payload = {
            "amount": int(amount),
            "phone_number": phone,
            "channel_id": self.channel_id,
            "provider": "m-pesa",
            "external_reference": external_reference,
            "customer_name": description,
            "callback_url": os.getenv("WEBHOOK_URL", "https://safesave-81bf.onrender.com/webhooks/payhero"),
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(f"{self.base_url}/payments", json=payload, headers=self._get_headers())
            logger.info("PayHero STK push", extra={"status_code": response.status_code})
            if response.status_code in (200, 201):
                return response.json()
            return {"error": response.text, "status_code": response.status_code}
        except Exception as exc:
            logger.error("PayHero exception", extra={"error": str(exc)})
            return {"error": str(exc)}

    def withdraw_to_mpesa(self, phone: str, amount: float, external_reference: str, description: str) -> dict:
        """Send money from PayHero wallet to M-Pesa"""
        payload = {
            "amount": int(amount),
            "phone_number": phone,
            "channel_id": self.channel_id,
            "provider": "m-pesa",
            "external_reference": external_reference,
            "description": description,
            "callback_url": os.getenv("WEBHOOK_URL", "https://safesave-81bf.onrender.com/webhooks/payhero"),
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(f"{self.base_url}/withdraw", json=payload, headers=self._get_headers())
            logger.info("PayHero withdrawal", extra={"status_code": response.status_code})
            if response.status_code in (200, 201):
                return response.json()
            return {"error": response.text, "status_code": response.status_code}
        except Exception as exc:
            logger.error("PayHero withdrawal exception", extra={"error": str(exc)})
            return {"error": str(exc)}

    def verify_payment(self, reference: str) -> dict:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(f"{self.base_url}/transaction-status", params={"reference": reference}, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            return {"error": response.text}
        except Exception as exc:
            return {"error": str(exc)}

pay_hero = PayHeroClient(PAYHERO_API_KEY, PAYHERO_BASE_URL, PAYHERO_CHANNEL_ID)

# ---------------------------------------------------------------------------
# Lifespan & App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app_: FastAPI):
    logger.info("SafeSave API starting", extra={"environment": ENVIRONMENT})
    if not SECRET_KEY:
        logger.error("SECRET_KEY not set — JWT will fail")
    if not PAYHERO_API_KEY:
        logger.warning("PAYHERO_API_KEY not configured")
    if PAYHERO_CHANNEL_ID == 0:
        logger.warning("PAYHERO_CHANNEL_ID is 0")
    if MAINTENANCE_MODE:
        logger.warning("MAINTENANCE MODE ON")
    yield
    logger.info("SafeSave API shutting down")

app = FastAPI(
    title="SafeSave API",
    description="Secure savings management backend — Kenya",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    if MAINTENANCE_MODE and request.url.path not in ("/health", "/metrics"):
        return JSONResponse(status_code=503, content={"detail": "Service under maintenance. Please try again later."})
    return await call_next(request)

# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
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

@app.get("/metrics", tags=["System"])
def metrics(db: Session = Depends(get_db)):
    return {
        "total_users": db.query(User).count(),
        "active_savings_goals": db.query(Savings).filter(Savings.is_active == True).count(),
        "transactions": {
            "pending": db.query(Transaction).filter(Transaction.status == TransactionStatus.PENDING).count(),
            "completed": db.query(Transaction).filter(Transaction.status == TransactionStatus.COMPLETED).count(),
            "failed": db.query(Transaction).filter(Transaction.status == TransactionStatus.FAILED).count(),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/register", response_model=UserResponse, status_code=201, tags=["Auth"])
def register(user: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Register a new user. Sends email verification link."""
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.phone == user.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    if db.query(User).filter(User.id_number == user.id_number).first():
        raise HTTPException(status_code=400, detail="ID number already registered")

    verification_token = generate_token()
    new_user = User(
        email=user.email,
        phone=user.phone,
        id_number=user.id_number,
        full_name=user.full_name,
        deposit_mode=user.deposit_mode,
        password_hash=get_password_hash(user.password),
        email_verification_token=verification_token,
        is_email_verified=False,
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        background_tasks.add_task(send_verification_email, user.email, verification_token)
        logger.info("User registered", extra={"email": user.email})
        return new_user
    except Exception as exc:
        db.rollback()
        logger.error("Registration error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Registration failed")

@app.get("/verify-email", tags=["Auth"])
def verify_email(token: str, db: Session = Depends(get_db)):
    """Verify email address using token from email link."""
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user.is_email_verified = True
    user.email_verification_token = None
    db.commit()
    return {"message": "Email verified successfully. You can now log in."}

@app.post("/login", tags=["Auth"])
def login(user: Login, db: Session = Depends(get_db)):
    """Login and receive JWT token."""
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not db_user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")
    token = create_access_token(data={"sub": db_user.email})
    logger.info("Login successful", extra={"email": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/forgot-password", tags=["Auth"])
def forgot_password(req: PasswordResetRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Request a password reset email."""
    user = db.query(User).filter(User.email == req.email).first()
    if user:
        token = generate_token()
        user.password_reset_token = token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, token)
    # Always return 200 to avoid email enumeration
    return {"message": "If that email exists, a reset link has been sent."}

@app.post("/reset-password", tags=["Auth"])
def reset_password(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Reset password using token from email."""
    user = db.query(User).filter(User.password_reset_token == req.token).first()
    if not user or not user.password_reset_expires or datetime.utcnow() > user.password_reset_expires:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.password_hash = get_password_hash(req.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()
    return {"message": "Password reset successfully. You can now log in."}

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@app.get("/profile", response_model=UserResponse, tags=["Profile"])
def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user

@app.patch("/profile", response_model=UserResponse, tags=["Profile"])
def update_profile(updates: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update profile — phone, full name, deposit mode."""
    if updates.phone and updates.phone != current_user.phone:
        if db.query(User).filter(User.phone == updates.phone, User.id != current_user.id).first():
            raise HTTPException(status_code=400, detail="Phone number already in use")
        current_user.phone = updates.phone
    if updates.full_name is not None:
        current_user.full_name = updates.full_name
    if updates.deposit_mode is not None:
        current_user.deposit_mode = updates.deposit_mode
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return current_user

@app.delete("/profile", tags=["Profile"])
def deactivate_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deactivate account. User can no longer log in."""
    current_user.is_active = False
    current_user.updated_at = datetime.utcnow()
    db.commit()
    logger.info("Account deactivated", extra={"email": current_user.email})
    return {"message": "Account deactivated successfully."}

# ---------------------------------------------------------------------------
# Savings — multiple goals supported
# ---------------------------------------------------------------------------
@app.post("/savings", status_code=201, tags=["Savings"])
def create_savings(
    savings: SavingsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new savings goal. Multiple active goals allowed."""
    if current_user.is_vip and savings.target_amount < VIP_MINIMUM_DEPOSIT:
        raise HTTPException(status_code=400, detail=f"VIP minimum deposit is {VIP_MINIMUM_DEPOSIT} KES")

    end_date = datetime.utcnow() + timedelta(days=savings.duration_days)
    new_savings = Savings(
        user_id=current_user.id,
        name=savings.name or savings.category.value.replace("_", " ").title(),
        category=savings.category,
        target_amount=savings.target_amount,
        duration_days=savings.duration_days,
        end_date=end_date,
    )
    try:
        db.add(new_savings)
        db.commit()
        db.refresh(new_savings)
        logger.info("Savings goal created", extra={"email": current_user.email, "id": new_savings.id})
        return {
            "id": new_savings.id,
            "name": new_savings.name,
            "category": new_savings.category,
            "target_amount": new_savings.target_amount,
            "duration_days": new_savings.duration_days,
            "start_date": new_savings.start_date,
            "end_date": new_savings.end_date,
            "message": "Savings goal created successfully",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create savings goal")

@app.get("/savings", tags=["Savings"])
def list_savings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all savings goals for the current user."""
    goals = db.query(Savings).filter(Savings.user_id == current_user.id).order_by(Savings.created_at.desc()).all()
    return {
        "total": len(goals),
        "goals": [
            {
                "id": g.id,
                "name": g.name,
                "category": g.category,
                "target_amount": g.target_amount,
                "current_amount": g.current_amount,
                "remaining_amount": g.target_amount - g.current_amount,
                "progress_percent": round(g.current_amount / g.target_amount * 100, 2) if g.target_amount > 0 else 0,
                "duration_days": g.duration_days,
                "days_remaining": max(0, (g.end_date - datetime.utcnow()).days) if g.end_date else 0,
                "start_date": g.start_date,
                "end_date": g.end_date,
                "is_active": g.is_active,
            }
            for g in goals
        ],
    }

# kept for backwards compatibility — MUST be defined before /savings/{savings_id}
@app.get("/savings/status", tags=["Savings"])
def savings_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get first active savings goal status (backwards compat)."""
    g = db.query(Savings).filter(Savings.user_id == current_user.id, Savings.is_active == True).first()
    if not g:
        return {"message": "No active savings goal"}
    return {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "target_amount": g.target_amount,
        "current_amount": g.current_amount,
        "remaining_amount": g.target_amount - g.current_amount,
        "progress_percent": round(g.current_amount / g.target_amount * 100, 2) if g.target_amount > 0 else 0,
        "duration_days": g.duration_days,
        "days_remaining": max(0, (g.end_date - datetime.utcnow()).days) if g.end_date else 0,
        "start_date": g.start_date,
        "end_date": g.end_date,
        "is_vip": current_user.is_vip,
    }


@app.get("/savings/{savings_id}", tags=["Savings"])
def get_savings(savings_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get a specific savings goal."""
    g = db.query(Savings).filter(Savings.id == savings_id, Savings.user_id == current_user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "target_amount": g.target_amount,
        "current_amount": g.current_amount,
        "remaining_amount": g.target_amount - g.current_amount,
        "progress_percent": round(g.current_amount / g.target_amount * 100, 2) if g.target_amount > 0 else 0,
        "duration_days": g.duration_days,
        "days_remaining": max(0, (g.end_date - datetime.utcnow()).days) if g.end_date else 0,
        "start_date": g.start_date,
        "end_date": g.end_date,
        "is_active": g.is_active,
        "is_vip": current_user.is_vip,
    }

# ---------------------------------------------------------------------------
# Deposit — user can specify which savings goal and which phone
# ---------------------------------------------------------------------------
@app.post("/deposit", status_code=201, tags=["Payments"])
def deposit(
    deposit_req: DepositRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate M-Pesa STK Push deposit to a savings goal."""
    # Find the target savings goal
    if deposit_req.savings_id:
        savings = db.query(Savings).filter(
            Savings.id == deposit_req.savings_id,
            Savings.user_id == current_user.id,
            Savings.is_active == True,
        ).first()
        if not savings:
            raise HTTPException(status_code=404, detail="Savings goal not found")
    else:
        savings = db.query(Savings).filter(
            Savings.user_id == current_user.id,
            Savings.is_active == True,
        ).first()
        if not savings:
            raise HTTPException(status_code=400, detail="Please create a savings goal first")

    if savings.current_amount + deposit_req.amount > savings.target_amount:
        remaining = savings.target_amount - savings.current_amount
        raise HTTPException(status_code=400, detail=f"Deposit would exceed target. Remaining: {remaining:.0f} KES")

    external_ref = f"SAFE-{current_user.id}-{int(datetime.utcnow().timestamp())}"
    transaction = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=deposit_req.amount,
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        external_reference=external_ref,
        phone=deposit_req.phone,
        description=deposit_req.description,
    )
    try:
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Deposit failed")

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
        raise HTTPException(status_code=400, detail=f"Payment initiation failed: {payment_result['error']}")

    payhero_ref = payment_result.get("reference")
    if payhero_ref:
        transaction.payhero_reference = payhero_ref
        db.commit()

    logger.info("STK push initiated", extra={"external_ref": external_ref, "payhero_ref": payhero_ref})
    return {
        "transaction_id": transaction.id,
        "external_reference": external_ref,
        "payhero_reference": payhero_ref,
        "savings_id": savings.id,
        "savings_name": savings.name,
        "amount": deposit_req.amount,
        "status": "pending",
        "message": "Payment initiated. Please complete the M-Pesa prompt on your phone.",
    }

# ---------------------------------------------------------------------------
# Withdraw — sends funds back to M-Pesa
# ---------------------------------------------------------------------------
@app.post("/withdraw", tags=["Payments"])
def withdraw(
    req: WithdrawRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Withdraw savings back to M-Pesa when target is reached or duration expired."""
    savings = db.query(Savings).filter(
        Savings.id == req.savings_id,
        Savings.user_id == current_user.id,
        Savings.is_active == True,
    ).first()
    if not savings:
        raise HTTPException(status_code=404, detail="Active savings goal not found")

    now = datetime.utcnow()
    target_reached = savings.current_amount >= savings.target_amount
    duration_expired = now >= savings.end_date if savings.end_date else False

    if not target_reached and not duration_expired:
        days_remaining = max(0, (savings.end_date - now).days) if savings.end_date else 0
        raise HTTPException(
            status_code=400,
            detail=f"Target not reached ({savings.current_amount:.0f}/{savings.target_amount:.0f} KES) and duration not expired ({days_remaining} days remaining)",
        )

    amount = savings.current_amount
    external_ref = f"WDRAW-{current_user.id}-{int(now.timestamp())}"

    # Initiate PayHero withdrawal to M-Pesa
    withdrawal_result = pay_hero.withdraw_to_mpesa(
        phone=req.phone,
        amount=amount,
        external_reference=external_ref,
        description=f"SafeSave withdrawal — {savings.name}",
    )

    savings.current_amount = 0
    savings.is_active = False

    withdrawal_tx = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=amount,
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.COMPLETED if "error" not in withdrawal_result else TransactionStatus.FAILED,
        external_reference=external_ref,
        phone=req.phone,
        description=f"Withdrawal — {savings.name}",
        error_message=str(withdrawal_result.get("error")) if "error" in withdrawal_result else None,
    )
    try:
        db.add(withdrawal_tx)
        db.commit()
        logger.info("Withdrawal processed", extra={"email": current_user.email, "amount": amount})
        return {
            "amount": amount,
            "phone": req.phone,
            "status": "completed" if "error" not in withdrawal_result else "failed",
            "message": f"KES {amount:.0f} is being sent to {req.phone} via M-Pesa.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Withdrawal failed")

# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
@app.get("/transactions", tags=["Payments"])
def get_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    savings_id: Optional[int] = None,
):
    """Get transaction history. Optionally filter by savings_id."""
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if savings_id:
        query = query.filter(Transaction.savings_id == savings_id)
    transactions = query.order_by(Transaction.created_at.desc()).limit(limit).all()
    return {
        "total": len(transactions),
        "transactions": [
            {
                "id": tx.id,
                "savings_id": tx.savings_id,
                "amount": tx.amount,
                "type": tx.transaction_type.value,
                "status": tx.status.value,
                "description": tx.description,
                "phone": tx.phone,
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
# ---------------------------------------------------------------------------
@app.post("/webhooks/payhero", tags=["Webhooks"])
async def payhero_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Handle PayHero payment callbacks."""
    raw_body = await request.body()
    x_signature = request.headers.get("x-signature") or request.headers.get("X-Signature")
    if PAYHERO_WEBHOOK_SECRET and x_signature:
        expected = hmac.new(PAYHERO_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(x_signature, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        request_body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        response_data = request_body.get("response", {})
        external_reference = response_data.get("ExternalReference")
        pay_status = response_data.get("Status", "")
        mpesa_receipt = response_data.get("MpesaReceiptNumber")
        result_code = response_data.get("ResultCode")
        result_desc = response_data.get("ResultDesc", "")
        amount = response_data.get("Amount", 0)

        transaction = db.query(Transaction).filter(Transaction.external_reference == external_reference).first()
        if not transaction:
            logger.warning("Webhook: transaction not found", extra={"external_reference": external_reference})
            return {"status": "ok", "note": "Transaction not found"}

        if pay_status.lower() == "success" and result_code == 0:
            transaction.status = TransactionStatus.COMPLETED
            transaction.mpesa_receipt = mpesa_receipt

            savings = db.query(Savings).filter(Savings.id == transaction.savings_id).first()
            if savings:
                savings.current_amount += transaction.amount
                logger.info("Savings updated", extra={"user_id": transaction.user_id, "new_amount": savings.current_amount})

                # Notify user of successful deposit
                user = db.query(User).filter(User.id == transaction.user_id).first()
                if user:
                    background_tasks.add_task(
                        send_deposit_success_email,
                        user.email,
                        user.full_name or "",
                        transaction.amount,
                        mpesa_receipt or "N/A",
                        savings.name or "Savings",
                    )
                    # Check if goal reached
                    if savings.current_amount >= savings.target_amount:
                        background_tasks.add_task(
                            send_goal_reached_email,
                            user.email,
                            user.full_name or "",
                            savings.name or "Savings",
                            savings.current_amount,
                        )
                        logger.info("Savings goal reached", extra={"user_id": user.id, "savings_id": savings.id})

        elif pay_status.lower() == "failed" or (result_code is not None and result_code != 0):
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = result_desc or "Payment failed"
        else:
            transaction.status = TransactionStatus.PENDING

        transaction.updated_at = datetime.utcnow()
        db.commit()
        return {"status": "ok"}

    except Exception as exc:
        logger.error("Webhook error", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}

# ---------------------------------------------------------------------------
# Customer Care
# ---------------------------------------------------------------------------
@app.get("/customer-care", tags=["Support"])
def customer_care():
    return {
        "email": os.getenv("CUSTOMER_SUPPORT_EMAIL", "support@safesave.com"),
        "phone": os.getenv("CUSTOMER_SUPPORT_PHONE", "+254712345678"),
        "company": os.getenv("COMPANY_NAME", "SafeSave Ltd"),
        "business_hours": "Mon-Fri 9AM-6PM (EAT)",
    }

# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
@app.get("/admin/users", tags=["Admin"])
def admin_list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """List all users. VIP/admin only."""
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    users = db.query(User).offset(skip).limit(limit).all()
    return {
        "total": db.query(User).count(),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "phone": u.phone,
                "full_name": u.full_name,
                "is_vip": u.is_vip,
                "is_active": u.is_active,
                "is_email_verified": u.is_email_verified,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }

@app.get("/admin/transactions", tags=["Admin"])
def admin_list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """List all transactions. VIP/admin only."""
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    txns = db.query(Transaction).order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": db.query(Transaction).count(),
        "transactions": [
            {
                "id": tx.id,
                "user_id": tx.user_id,
                "savings_id": tx.savings_id,
                "amount": tx.amount,
                "type": tx.transaction_type.value,
                "status": tx.status.value,
                "mpesa_receipt": tx.mpesa_receipt,
                "external_reference": tx.external_reference,
                "created_at": tx.created_at,
            }
            for tx in txns
        ],
    }

@app.patch("/admin/users/{user_id}/suspend", tags=["Admin"])
def admin_suspend_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Suspend a user account. VIP/admin only."""
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"message": f"User {user.email} suspended"}

@app.patch("/admin/users/{user_id}/activate", tags=["Admin"])
def admin_activate_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Activate a suspended user account. VIP/admin only."""
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"message": f"User {user.email} activated"}

@app.post("/admin/reconcile", tags=["Admin"])
def reconcile_pending_transactions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Reconcile pending transactions against PayHero."""
    if not current_user.is_vip:
        raise HTTPException(status_code=403, detail="Admin access required")
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    pending = db.query(Transaction).filter(
        Transaction.status == TransactionStatus.PENDING,
        Transaction.transaction_type == TransactionType.DEPOSIT,
        Transaction.created_at < cutoff,
        Transaction.external_reference.isnot(None),
    ).all()
    updated = 0
    for tx in pending:
        result = pay_hero.verify_payment(tx.payhero_reference or tx.external_reference)
        if "error" in result:
            continue
        ph_status = result.get("status", "").upper()
        if ph_status == "SUCCESS":
            tx.status = TransactionStatus.COMPLETED
            updated += 1
        elif ph_status == "FAILED":
            tx.status = TransactionStatus.FAILED
            updated += 1
        tx.updated_at = datetime.utcnow()
    db.commit()
    return {"checked": len(pending), "updated": updated}

# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"error": str(exc), "path": str(request.url)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
