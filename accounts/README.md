
# Accounts app — README

Overview
- The `accounts` app implements authentication, user management, and role-based access for the HRIS project.
- Key roles: `hr_admin` and `employee`. New users must be approved by an HR admin before gaining full access.

Models & core fields
- Custom `User` model extends Django `AbstractUser` and includes:
	- `role` — user role (e.g., `hr_admin`, `employee`).
	- `is_approved` — boolean flag: new users default to `False` and require HR approval.
	- HR-specific fields: `employee_id`, `pf_id`, `grade`, `department`, `hire_date` (see `models.py`).

Authentication flow
- Registration: users sign up via the registration view/form. Submitted data is validated by `forms.py`.
- Account creation: a `User` record is created with `is_approved=False` (unless created by a superuser/HR admin).
- Approval: HR admins approve users via the approval endpoint, which sets `is_approved=True` and may trigger profile creation.
- Login: only users with `is_active=True` and `is_approved=True` are allowed into protected areas. Login attempts are logged for audit.

User data verification
- Email: the app uses the `company_email` (and standard email) fields; forms validate format and uniqueness.
- Data normalization: numeric/decimal fields (e.g., salary) are normalized for MongoDB's `Decimal128` when relevant (see `forms.py` utilities).
- Admin verification: HR admins can inspect and correct user fields; approval is the explicit verification gate before access.

Role-based access control (RBAC)
- Decorators: `decorators.py` contains helpers like `hr_admin_required`, `employee_required`, and `approved_user_required`. Apply these to views to restrict access.
- Dashboard routing: views redirect users to role-specific dashboards based on `role` and `is_approved`.

Forms & validation
- All forms use Bootstrap 5 styling via `forms.py` widget attrs.
- Complex validation (tax, banking, decimal normalization) happens at the form level to avoid reliance on MongoDB schema constraints.

Security & auditing
- Login attempts: successful and failed attempts are recorded with IP and User-Agent for auditing.
- Password management: relies on Django's built-in password hashing and reset flows (views/forms in `accounts/views.py` & templates).

Admin & management
- Superusers and HR admins can manage users through the Django admin and the provided HR views.
- Migrations are present under `migrations/` and reflect schema evolution; because the project uses `djongo`, migrations behave differently than relational DBs—refer to MONGODB_SETUP.md.

Testing notes
- Tests referencing `accounts` features live in project-level test files (see `test_registration.py`, `test_employee_dashboard.py`). Use the provided test scripts to quickly exercise registration and approval flows.

Extending and integration
- To add a new role, extend the `role` choices in the `User` model and update decorators/views accordingly.
- For integrations (e.g., single sign-on, external identity providers), replace or augment the registration/login views while preserving the `is_approved` gating logic.

Files of interest
- `models.py` — custom `User` model and related profile models.
- `forms.py` — registration, normalization, and validation logic.
- `views.py` — registration, login, approval, and profile endpoints.
- `decorators.py` — role/approval decorators for view protection.
- `urls.py` — route list for accounts endpoints.

Quick start (developer)
1. Ensure MongoDB is running (see MONGODB_SETUP.md).
2. Run Django server: `python manage.py runserver`.
3. Register a new user via the registration page and approve it from an HR admin account.

Contact
- For questions about the `accounts` implementation, see the main project README or contact the repository maintainer.

