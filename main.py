import os
import logging
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

import httpx
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
from jose import JWTError, jwt

# Load environment variables
load_dotenv()

# Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./safesave.db")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Pay Hero Configuration
PAYHERO_API_KEY = os.getenv("PAYHERO_API_KEY")
PAYHERO_API_SECRET = os.getenv("PAYHERO_API_SECRET")
PAYHERO_BASE_URL = os.getenv("PAYHERO_BASE_URL", "https://sandbox.payhero.io/api/v2")
PAYHERO_WEBHOOK_SECRET = os.getenv("PAYHERO_WEBHOOK_SECRET")

# Business Configuration
MIN_DEPOSIT = float(os.getenv("MIN_DEPOSIT", "100"))
MAX_DEPOSIT = float(os.getenv("MAX_DEPOSIT", "1000000"))
VIP_MINIMUM_DEPOSIT = float(os.getenv("VIP_MINIMUM_DEPOSIT", "5000"))

# Logging Configuration
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.getenv("LOG_FILE", "logs/safesave.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enums
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

# Database Models
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
    payhero_transaction_id = Column(String, unique=True, index=True, nullable=True)
    payhero_reference = Column(String, nullable=True)
    description = Column(String)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Pydantic Models
class UserCreate(BaseModel):
    email: EmailStr
    phone: str
    id_number: str
    deposit_mode: str = "mpesa"
    password: str = Field(..., min_length=8)
    confirm_password: str

    @validator("password")
    def password_strength(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v

class UserResponse(BaseModel):
    id: int
    email: str
    phone: str
    is_vip: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Login(BaseModel):
    email: EmailStr
    password: str

class SavingsCreate(BaseModel):
    target_amount: float = Field(..., gt=0)
    duration_days: int = Field(..., gt=0, le=1825)  # Max 5 years

    @validator("target_amount")
    def validate_amount(cls, v):
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0)
    phone: str
    description: str = "Savings deposit"

    @validator("amount")
    def validate_amount(cls, v):
        if v < MIN_DEPOSIT or v > MAX_DEPOSIT:
            raise ValueError(f"Amount must be between {MIN_DEPOSIT} and {MAX_DEPOSIT}")
        return v

class TransactionResponse(BaseModel):
    id: int
    amount: float
    currency: str
    transaction_type: TransactionType
    status: TransactionStatus
    created_at: datetime

    class Config:
        from_attributes = True

# Authentication Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return payload
    except JWTError:
        return None

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Current user dependency
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
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
    if email is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user

# Pay Hero API Client
class PayHeroClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.client = httpx.Client()

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def initiate_payment(
        self,
        phone: str,
        amount: float,
        reference: str,
        description: str
    ) -> dict:
        """Initiate a payment request via Pay Hero"""
        try:
            payload = {
                "phone": phone,
                "amount": amount,
                "reference": reference,
                "description": description,
                "callback_url": os.getenv("WEBHOOK_URL", "https://yourdomain.com/webhooks/payhero")
            }
            
            response = self.client.post(
                f"{self.base_url}/mobile/send-money",
                json=payload,
                headers=self._get_headers(),
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                logger.error(f"Pay Hero API error: {response.status_code} - {response.text}")
                return {"error": response.text}
                
        except Exception as e:
            logger.error(f"Pay Hero API exception: {str(e)}")
            return {"error": str(e)}

    def verify_payment(self, transaction_id: str) -> dict:
        """Verify payment status from Pay Hero"""
        try:
            response = self.client.get(
                f"{self.base_url}/mobile/transaction-status/{transaction_id}",
                headers=self._get_headers(),
                timeout=10.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Pay Hero verify error: {response.status_code} - {response.text}")
                return {"error": response.text}
                
        except Exception as e:
            logger.error(f"Pay Hero verify exception: {str(e)}")
            return {"error": str(e)}

pay_hero = PayHeroClient(PAYHERO_API_KEY, PAYHERO_API_SECRET, PAYHERO_BASE_URL)

# FastAPI App
app = FastAPI(
    title="SafeSave API",
    description="Production-ready savings management backend",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check
@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": ENVIRONMENT}

# Authentication Endpoints
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    logger.info(f"Registration attempt for email: {user.email}")
    
    # Check if email exists
    if db.query(User).filter(User.email == user.email).first():
        logger.warning(f"Email already registered: {user.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    # Check if phone exists
    if db.query(User).filter(User.phone == user.phone).first():
        logger.warning(f"Phone already registered: {user.phone}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already registered")
    
    # Check if ID exists
    if db.query(User).filter(User.id_number == user.id_number).first():
        logger.warning(f"ID number already registered: {user.id_number}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID number already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        phone=user.phone,
        id_number=user.id_number,
        deposit_mode=user.deposit_mode,
        password_hash=hashed_password
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"User registered successfully: {user.email}")
        return new_user
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed")

@app.post("/login")
def login(user: Login, db: Session = Depends(get_db)):
    """User login"""
    logger.info(f"Login attempt for email: {user.email}")
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        logger.warning(f"Failed login attempt: {user.email}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    if not db_user.is_active:
        logger.warning(f"Login attempt on inactive account: {user.email}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account inactive")
    
    access_token = create_access_token(data={"sub": db_user.email})
    logger.info(f"Successful login: {user.email}")
    return {"access_token": access_token, "token_type": "bearer"}

# Savings Endpoints
@app.post("/savings", status_code=status.HTTP_201_CREATED)
def create_savings(
    savings: SavingsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a savings goal"""
    logger.info(f"Creating savings goal for user: {current_user.email}")
    
    # Check VIP minimum
    if current_user.is_vip and savings.target_amount < VIP_MINIMUM_DEPOSIT:
        logger.warning(f"VIP minimum not met for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"VIP minimum deposit is {VIP_MINIMUM_DEPOSIT} KES"
        )
    
    # Check existing active savings
    existing = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True
    ).first()
    
    if existing:
        logger.warning(f"User already has active savings goal: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete or close existing savings goal first"
        )
    
    end_date = datetime.utcnow() + timedelta(days=savings.duration_days)
    new_savings = Savings(
        user_id=current_user.id,
        target_amount=savings.target_amount,
        duration_days=savings.duration_days,
        end_date=end_date
    )
    
    try:
        db.add(new_savings)
        db.commit()
        db.refresh(new_savings)
        logger.info(f"Savings goal created successfully for user: {current_user.email}")
        return {
            "id": new_savings.id,
            "target_amount": new_savings.target_amount,
            "duration_days": new_savings.duration_days,
            "start_date": new_savings.start_date,
            "end_date": new_savings.end_date,
            "message": "Savings goal created successfully"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating savings goal: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create savings goal")

@app.get("/savings/status")
def savings_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current savings status"""
    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True
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
        "is_vip": current_user.is_vip
    }

# Transaction Endpoints
@app.post("/deposit", status_code=status.HTTP_201_CREATED)
async def deposit(
    deposit_req: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initiate a deposit via Pay Hero"""
    logger.info(f"Deposit request from user: {current_user.email}, amount: {deposit_req.amount}")
    
    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True
    ).first()
    
    if not savings:
        logger.warning(f"No active savings goal for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please create a savings goal first"
        )
    
    # Check if deposit would exceed target
    if savings.current_amount + deposit_req.amount > savings.target_amount:
        logger.warning(f"Deposit would exceed target for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deposit would exceed target. Remaining: {savings.target_amount - savings.current_amount} KES"
        )
    
    # Create transaction record
    transaction_ref = f"SAFE-{current_user.id}-{datetime.utcnow().timestamp()}"
    transaction = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=deposit_req.amount,
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        payhero_reference=transaction_ref,
        description=deposit_req.description
    )
    
    try:
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        logger.info(f"Transaction created: {transaction.id}")
        
        # Initiate Pay Hero payment
        payment_result = await pay_hero.initiate_payment(
            phone=deposit_req.phone,
            amount=deposit_req.amount,
            reference=transaction_ref,
            description=deposit_req.description
        )
        
        if "error" in payment_result:
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = str(payment_result["error"])
            db.commit()
            logger.error(f"Pay Hero payment failed: {payment_result['error']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment initiation failed: {payment_result['error']}"
            )
        
        # Store Pay Hero transaction ID
        if "transaction_id" in payment_result:
            transaction.payhero_transaction_id = payment_result["transaction_id"]
            db.commit()
        
        logger.info(f"Payment initiated successfully via Pay Hero: {payment_result}")
        return {
            "transaction_id": transaction.id,
            "reference": transaction_ref,
            "amount": deposit_req.amount,
            "status": "pending",
            "message": "Payment initiated. Please complete the payment on your phone."
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Deposit error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Deposit failed")

@app.post("/withdraw")
def withdraw(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Withdraw savings"""
    logger.info(f"Withdrawal request from user: {current_user.email}")
    
    savings = db.query(Savings).filter(
        Savings.user_id == current_user.id,
        Savings.is_active == True
    ).first()
    
    if not savings:
        logger.warning(f"No active savings for withdrawal: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active savings goal"
        )
    
    now = datetime.utcnow()
    
    # Check withdrawal conditions
    target_reached = savings.current_amount >= savings.target_amount
    duration_expired = now >= savings.end_date if savings.end_date else False
    
    if not target_reached and not duration_expired:
        days_remaining = (savings.end_date - now).days if savings.end_date else 0
        logger.warning(f"Withdrawal conditions not met for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target not reached (${savings.current_amount}/${savings.target_amount}) and duration not expired ({days_remaining} days remaining)"
        )
    
    amount = savings.current_amount
    savings.current_amount = 0
    savings.is_active = False
    
    # Create withdrawal transaction
    withdrawal_tx = Transaction(
        user_id=current_user.id,
        savings_id=savings.id,
        amount=amount,
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.COMPLETED,
        description="Savings withdrawal"
    )
    
    try:
        db.add(withdrawal_tx)
        db.commit()
        logger.info(f"Withdrawal successful for user: {current_user.email}, amount: {amount}")
        return {
            "amount": amount,
            "status": "completed",
            "message": f"Successfully withdrew {amount} KES"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Withdrawal error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Withdrawal failed")

@app.get("/transactions")
def get_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
):
    """Get transaction history"""
    transactions = db.query(Transaction).filter(
        Transaction.user_id == current_user.id
    ).order_by(Transaction.created_at.desc()).limit(limit).all()
    
    return {
        "total": len(transactions),
        "transactions": [
            {
                "id": tx.id,
                "amount": tx.amount,
                "type": tx.transaction_type.value,
                "status": tx.status.value,
                "description": tx.description,
                "created_at": tx.created_at
            }
            for tx in transactions
        ]
    }

# Webhook for Pay Hero Callbacks
@app.post("/webhooks/payhero")
def payhero_webhook(
    request_body: dict,
    x_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Handle Pay Hero payment callbacks"""
    logger.info("Received Pay Hero webhook")
    
    # Verify webhook signature
    if x_signature and PAYHERO_WEBHOOK_SECRET:
        payload = json.dumps(request_body, separators=(',', ':'), sort_keys=True)
        expected_signature = hmac.new(
            PAYHERO_WEBHOOK_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if x_signature != expected_signature:
            logger.error(f"Invalid webhook signature")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    
    try:
        # Parse webhook data
        transaction_id = request_body.get("transaction_id")
        status_value = request_body.get("status")  # completed, failed, pending
        reference = request_body.get("reference")
        
        logger.info(f"Webhook: transaction_id={transaction_id}, status={status_value}, reference={reference}")
        
        # Find transaction
        transaction = db.query(Transaction).filter(
            Transaction.payhero_transaction_id == transaction_id
        ).first()
        
        if not transaction:
            logger.warning(f"Transaction not found: {transaction_id}")
            return {"status": "ok", "error": "Transaction not found"}
        
        # Update transaction status
        if status_value == "completed":
            transaction.status = TransactionStatus.COMPLETED
            
            # Update savings amount
            savings = db.query(Savings).filter(Savings.id == transaction.savings_id).first()
            if savings:
                savings.current_amount += transaction.amount
                logger.info(f"Savings updated for user_id={transaction.user_id}, new amount={savings.current_amount}")
        
        elif status_value == "failed":
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = request_body.get("error_message", "Payment failed")
            logger.warning(f"Payment failed: {transaction.error_message}")
        
        elif status_value == "pending":
            transaction.status = TransactionStatus.PENDING
        
        transaction.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Webhook processed successfully: {transaction_id}")
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return {"status": "error", "detail": str(e)}

# User Profile Endpoint
@app.get("/profile", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return current_user

# Customer Care Endpoint
@app.get("/customer-care")
def customer_care():
    """Get customer support information"""
    return {
        "email": os.getenv("CUSTOMER_SUPPORT_EMAIL", "support@safesave.com"),
        "phone": os.getenv("CUSTOMER_SUPPORT_PHONE", "+254712345678"),
        "company": os.getenv("COMPANY_NAME", "SafeSave Ltd"),
        "business_hours": "Mon-Fri 9AM-6PM (EAT)"
    }

# Error Handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    logger.error(f"ValueError: {str(exc)}")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting SafeSave API in {ENVIRONMENT} mode")
    if not PAYHERO_API_KEY or not PAYHERO_API_SECRET:
        logger.warning("Pay Hero credentials not configured. Payments will fail.")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("SafeSave API shutting down")