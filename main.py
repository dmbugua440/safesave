from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
from fastapi.security import OAuth2PasswordBearer

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./safesave.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    id_number = Column(String, unique=True)
    deposit_mode = Column(String)  # 'mpesa' or 'other'
    password_hash = Column(String)
    is_vip = Column(Boolean, default=False)

class Savings(Base):
    __tablename__ = "savings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    target_amount = Column(Float)
    duration_days = Column(Integer)
    start_date = Column(DateTime, default=datetime.utcnow)
    current_amount = Column(Float, default=0.0)

Base.metadata.create_all(bind=engine)

# Pydantic models
class UserCreate(BaseModel):
    email: str
    phone: str
    id_number: str
    deposit_mode: str
    password: str
    confirm_password: str

class Login(BaseModel):
    email: str
    password: str

class SavingsCreate(BaseModel):
    target_amount: float
    duration_days: int

class Deposit(BaseModel):
    amount: float

# Auth setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "your-secret-key-here"  # Change this in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

app = FastAPI(title="SafeSave API", description="Backend for SafeSave savings app")

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if user.password != user.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        phone=user.phone,
        id_number=user.id_number,
        deposit_mode=user.deposit_mode,
        password_hash=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully"}

@app.post("/login")
def login(user: Login, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/savings")
def create_savings(savings: SavingsCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.is_vip and savings.target_amount < 5000:
        raise HTTPException(status_code=400, detail="VIP minimum deposit is 5000 KSH")
    new_savings = Savings(
        user_id=current_user.id,
        target_amount=savings.target_amount,
        duration_days=savings.duration_days
    )
    db.add(new_savings)
    db.commit()
    db.refresh(new_savings)
    return {"message": "Savings goal set successfully"}

@app.post("/deposit")
def deposit(deposit: Deposit, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Placeholder for Pay Hero integration
    # In production, integrate with Pay Hero API to process payment
    savings = db.query(Savings).filter(Savings.user_id == current_user.id).first()
    if not savings:
        raise HTTPException(status_code=400, detail="No savings goal set")
    savings.current_amount += deposit.amount
    db.commit()
    return {"message": f"Deposited {deposit.amount} KSH successfully"}

@app.post("/withdraw")
def withdraw(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    savings = db.query(Savings).filter(Savings.user_id == current_user.id).first()
    if not savings:
        raise HTTPException(status_code=400, detail="No savings goal set")
    now = datetime.utcnow()
    end_date = savings.start_date + timedelta(days=savings.duration_days)
    if savings.current_amount < savings.target_amount and now < end_date:
        raise HTTPException(status_code=400, detail="Cannot withdraw: target not reached and duration not ended")
    amount = savings.current_amount
    savings.current_amount = 0
    db.commit()
    return {"message": f"Withdrew {amount} KSH successfully"}

@app.get("/customer-care")
def customer_care():
    return {"email": "your-email@example.com", "phone": "your-phone-number"}

@app.get("/savings/status")
def savings_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    savings = db.query(Savings).filter(Savings.user_id == current_user.id).first()
    if not savings:
        return {"message": "No savings goal set"}
    return {
        "target_amount": savings.target_amount,
        "current_amount": savings.current_amount,
        "duration_days": savings.duration_days,
        "start_date": savings.start_date,
        "is_vip": current_user.is_vip
    }