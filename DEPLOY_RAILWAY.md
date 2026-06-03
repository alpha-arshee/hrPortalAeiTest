Railway deployment guide for HR Portal (Django + MongoDB)

Prerequisites
- A Railway account (https://railway.app)
- Git repository for this project

Overview
- This project includes a `Dockerfile` and `Procfile`. Railway can build using the Dockerfile.
- You must set environment variables on Railway (SECRET_KEY, MONGODB_HOST, ALLOWED_HOSTS, EMAIL_*).

Steps
1. Push your code to a Git repo (GitHub/GitLab). Railway needs a connected repo or you can deploy via Docker image.

2. Create a new Railway project and connect your Git repository.

3. Add a new service and choose "Deploy from GitHub" (or Docker). If Railway detects the Dockerfile it will use it.

4. Environment variables (Railway > Variables): set at minimum
   - `SECRET_KEY` — set a strong secret
   - `DEBUG`=False
   - `ALLOWED_HOSTS`=your-domain.com,railway.app (comma-separated)
   - `MONGODB_HOST` — the MongoDB Atlas connection string (mongodb+srv://... or host:port)
   - `DB_NAME` — database name
   - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`
   - Optional security flags: `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`

5. Railway and MongoDB
- If you use MongoDB Atlas, configure network access (allow Railway IPs or 0.0.0.0/0 for testing) and create a DB user. Use that URI in `MONGODB_HOST`.
- Alternatively, add Railway's MongoDB plugin (add-on) and use the provided connection string.

6. Build & Deploy
- Railway will build the Docker image. If you need to trigger a manual deploy, click "Deploy" in the Railway UI.

7. Post-deploy
- Run any one-off commands via Railway's console (Migrations and collectstatic are run by `entrypoint.sh`, but you can run manually):
  - `python manage.py migrate --noinput`
  - `python manage.py collectstatic --noinput`

8. Static files and media
- Static files are collected into `/app/staticfiles` using WhiteNoise (served by Gunicorn). This works for small apps, but for production scale use S3/Cloud Storage for `MEDIA` and static assets.

9. Logs and scaling
- View build logs and runtime logs in Railway dashboard. Add more Gunicorn workers via the `CMD` or environment if needed.

Security & backups
- Do not commit secrets to Git. Use Railway environment variables.
- Configure backups for MongoDB (Atlas provides this) and consider storing media in persistent storage.

Troubleshooting
- Build fails due to `requirements.txt` encoding: ensure `requirements.txt` is UTF-8 without BOM. If your `requirements.txt` looks corrupted, regenerate it in your virtualenv:
  ```bash
  pip freeze > requirements.txt
  ```

That's it — tell me if you want me to add a GitHub Actions workflow to automatically build and push Docker images to a registry that Railway can pull from, or I can create a `railway.json` if you prefer the Railway CLI route.
