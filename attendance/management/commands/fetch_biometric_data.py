from django.core.management.base import BaseCommand
from attendance.models import BiometricLog
import requests
from datetime import datetime
from django.conf import settings
import os
try:
    from decouple import config
except Exception:
    config = None

class Command(BaseCommand):
    help = "Fetch biometric logs from dummy API and store them in MongoDB"

    def handle(self, *args, **kwargs):
        # Determine base URL and token
        base_url = os.getenv('EASYTIME_BASE_URL') or (config('EASYTIME_BASE_URL', default=None) if config else None) or 'http://122.169.35.8:8081'
        base_url = base_url.rstrip('/')

        # Use HTTP Basic Auth with credentials from env/.env
        API_URL = f"{base_url}/iclock/api/transactions/"

        username = os.getenv('EASYTIME_USERNAME') or (config('EASYTIME_USERNAME', default=None) if config else None)
        password = os.getenv('EASYTIME_PASSWORD') or (config('EASYTIME_PASSWORD', default=None) if config else None)

        if not (username and password):
            self.stdout.write(self.style.ERROR('EASYTIME_USERNAME and EASYTIME_PASSWORD must be set for Basic Auth'))
            return

        # Support paginated responses using `next` link
        next_url = API_URL
        count = 0
        while next_url:
            try:
                resp = requests.get(next_url, auth=(username, password), timeout=20)
                resp.raise_for_status()
                payload = resp.json()
                page_data = payload.get('data') or payload.get('results') or payload
                # If the payload is the pagination object, extract the list
                if isinstance(page_data, dict):
                    page_data = page_data.get('data') or page_data.get('results') or []
                # normalize next link
                next_url = payload.get('next') or payload.get('next_page') or None
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error fetching API page {next_url}: {e}"))
                return

            for entry in page_data:
                try:
                    # Map EasyTimePro fields to expected fields
                    # emp_code -> employee_id
                    employee_id = entry.get('employee_id') or entry.get('emp_code') or entry.get('emp')
                    # punch_time format: "YYYY-MM-DD HH:MM:SS"
                    punch_time_raw = entry.get('punch_time') or entry.get('upload_time')
                    if not punch_time_raw:
                        self.stdout.write(self.style.WARNING(f"Skipping record without punch_time: {entry}"))
                        continue
                    try:
                        dt = datetime.strptime(punch_time_raw.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        # fallback to ISO format
                        try:
                            dt = datetime.fromisoformat(punch_time_raw)
                        except Exception:
                            self.stdout.write(self.style.WARNING(f"Unable to parse punch_time: {punch_time_raw}"))
                            continue
                    punch_date = dt.date()
                    punch_time = dt.time().isoformat()
                    # status: try punch_state, purpose, or is_attendance
                    status = entry.get('punch_state') or entry.get('purpose') or entry.get('is_attendance') or entry.get('work_code')
                    # Ensure only one biometric record per employee per day per status (IN/OUT).
                    # The API returns an IN and an OUT punch; we allow one record per status per day.
                    # Default behavior: skip if a record for this employee, date & status already exists.
                    # To overwrite, set BIOMETRIC_OVERWRITE_DAILY = True in Django settings.
                    existing = BiometricLog.objects.filter(employee_id=employee_id, punch_date=punch_date, status=status).first()
                    overwrite = getattr(settings, 'BIOMETRIC_OVERWRITE_DAILY', False)

                    if existing and not overwrite:
                        # skip this record to keep only the first/previous one for the day+status
                        self.stdout.write(self.style.NOTICE(f"Skipping {employee_id} on {punch_date} status={status} (already exists)"))
                        continue

                    if existing and overwrite:
                        existing.punch_time = punch_time
                        existing.first_name = entry.get('first_name')
                        existing.department = entry.get('department')
                        existing.status = status
                        existing.device_id = entry.get('terminal_sn') or entry.get('terminal')
                        existing.device_serial_no = entry.get('terminal_alias')
                        existing.save()
                    else:
                        BiometricLog.objects.create(
                            employee_id=employee_id,
                            punch_date=punch_date,
                            punch_time=punch_time,
                            first_name=entry.get('first_name') or entry.get('emp_code'),
                            department=entry.get('department') or entry.get('company'),
                            status=status,
                            device_id=entry.get('terminal_sn') or entry.get('terminal'),
                            device_serial_no=entry.get('terminal_alias'),
                        )
                        count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"⚠️ Error on record: {e}"))

        self.stdout.write(self.style.SUCCESS(f"✅ Synced {count} new records from biometric API"))
