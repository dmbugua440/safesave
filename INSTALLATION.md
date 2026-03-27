# SafeSave Installation Instructions

Since automatic Python installation is encountering issues, please follow these manual steps:

## Step 1: Install Python 3.11
1. Visit: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
2. Run the installer
3. **IMPORTANT**: Check the box "Add Python to PATH" before clicking "Install"
4. Complete the installation

## Step 2: Verify Installation
After installation, run these commands in PowerShell:
```
python --version
pip --version
```

## Step 3: Setup SafeSave Backend
Once Python is installed, run:
```
cd c:\Users\OPEN GATE FOUNDATION\Desktop\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Step 4: Test the API
The server will run at: http://localhost:8000
API docs available at: http://localhost:8000/docs

## Features Implemented
- User Registration & Login
- Savings Goal Management
- Deposit System (placeholder for Pay Hero integration)
- Withdrawal System (with target & duration validation)
- VIP Account Support (minimum 5000 KSH deposits)
- Customer Care Endpoint

## Next Steps
1. Update customer care email/phone in main.py (lines ~170)
2. Integrate Pay Hero API for payment processing
3. Create a mobile frontend using React Native or Flutter
