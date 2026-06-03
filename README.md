# Django Two-Level Authentication System

A Django-based authentication system with two user roles: HR-Admin and Employee, using MongoDB as the database.

## ✅ **SYSTEM STATUS: FULLY OPERATIONAL**

The application is successfully running with:
- **Django 4.1.13** (compatible version)
- **MongoDB** with djongo ORM
- **Two-level authentication** (HR-Admin/Employee)
- **Responsive web interface**

## 🚀 **Quick Start**

1. **Access the application**: http://127.0.0.1:8000/
2. **Admin Login**: Use superuser account (harsh)
3. **Employee Registration**: Register at /register/ 
4. **HR Approval**: Login as HR admin to approve employees

## Features

### Two-Level Authentication
- **HR-Admin**: Complete system management
- **Employee**: Limited profile access

### MongoDB Integration
- **Database**: djongo ORM for MongoDB
- **Scalability**: NoSQL document storage
- **Performance**: Optimized connection pooling

### Role-Based Access Control
- **Dashboard**: Role-specific interfaces
- **Permissions**: Decorator-based access control
- **Workflow**: Employee approval system

### User Management
- **Registration**: Self-service employee signup
- **Approval**: HR-controlled account activation
- **Profiles**: Comprehensive employee data
- **Security**: Login attempt tracking

### HTML Templates
- **Responsive**: Bootstrap 5 design
- **Modern**: Clean, professional interface
- **Interactive**: Dynamic user interactions

## Installation

1. **Prerequisites**:
   ```bash
   # MongoDB must be running
   net start MongoDB
   ```

2. **Environment Setup**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Database Setup**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Run Server**:
   ```bash
   python manage.py runserver
   ```

## Project Structure

```
aeihhr
├── aeihhr # Main project
├── accounts/            # Authentication app
├── templates/           # HTML templates  
├── static/              # Static files
├── media/               # Uploaded files
├── requirements.txt     # Dependencies
└── test_*.py           # Test scripts
```

## Technical Details

### Database Configuration
- **Engine**: djongo (MongoDB ORM)
- **Database**: aeihhr
- **Connection**: Optimized pooling
- **Schema**: Flexible document structure

### Security Features
- **Authentication**: Django's built-in system
- **Authorization**: Role-based permissions
- **Tracking**: Login attempt monitoring
- **Validation**: Form and model validation

### API Endpoints
- `/` - Home page
- `/register/` - Employee registration
- `/login/` - User authentication
- `/dashboard/` - Role-based dashboards
- `/admin/` - Django admin interface

## Troubleshooting

### Common Issues

1. **MongoDB Connection**:
   ```bash
   # Test connection
   python test_mongodb.py
   ```

2. **Database Errors**:
   ```bash
   # Reset migrations if needed
   python manage.py makemigrations --empty accounts
   ```

3. **Package Conflicts**:
   ```bash
   # Reinstall compatible versions
   pip install -r requirements.txt --force-reinstall
   ```

## User Roles

### HR-Admin
- ✅ Manage employee accounts
- ✅ Approve/reject registrations  
- ✅ View analytics and reports
- ✅ Department management
- ✅ Full system access

### Employee
- ✅ Personal profile management
- ✅ View own dashboard
- ✅ Update personal information
- ✅ Limited system access

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the MIT License.