# MongoDB Setup Instructions

## Prerequisites
1. Install MongoDB Community Server from: https://www.mongodb.com/try/download/community
2. Make sure MongoDB service is running

## Windows MongoDB Setup

### 1. Download and Install MongoDB
- Download MongoDB Community Server from the official website
- Run the installer and follow the installation wizard
- Choose "Complete" installation type
- Install MongoDB as a Windows Service

### 2. Start MongoDB Service
```powershell
# Start MongoDB service
net start MongoDB

# Or using Services.msc
# Open Services -> Find MongoDB -> Start
```

### 3. Verify MongoDB Installation
```powershell
# Connect to MongoDB shell
mongosh

# Or older versions:
mongo
```

### 4. Create Database and User (Optional)
```javascript
// In MongoDB shell
use aei_db

// Create a user with read/write permissions
db.createUser({
  user: "auth_user",
  pwd: "your_password_here",
  roles: [
    {
      role: "readWrite",
      db: "aei_db"
    }
  ]
})
```

## Environment Configuration

Update your `.env` file with MongoDB credentials:

```env
DB_NAME=aei_db
DB_HOST=mongodb://localhost:27017
DB_USER=auth_user
DB_PASSWORD=your_password_here
DB_AUTH_SOURCE=aei_db
DB_AUTH_MECHANISM=SCRAM-SHA-1
```

## Testing Connection

Run the test script to verify MongoDB connection:
```powershell
python test_mongodb.py
```