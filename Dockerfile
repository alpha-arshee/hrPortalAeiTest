FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# install python deps

# copy requirement files and install
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt -r requirements-prod.txt

# copy project
COPY . /app

RUN adduser --disabled-password --gecos '' appuser || true

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=aei_hr.settings

# ensure entrypoint is executable and use it
RUN /bin/sh -c 'chmod +x /app/entrypoint.sh' || true
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "aei_hr.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
