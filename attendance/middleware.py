# attendance/middleware.py
import threading
import logging
from datetime import time as dtime
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command
from attendance.models import BiometricSyncStatus

logger = logging.getLogger(__name__)


class BiometricDailySyncMiddleware:
    """
    Fires fetch_biometric_data once per day, on the first request that
    arrives at/after RUN_BIOMETRIC_AFTER_TIME. No external scheduler needed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_trigger_sync()
        return self.get_response(request)

    def _maybe_trigger_sync(self):
        if not getattr(settings, 'RUN_BIOMETRIC_ON_LOGIN', False):
            return

        now = timezone.localtime()
        trigger_time = getattr(settings, 'RUN_BIOMETRIC_AFTER_TIME', dtime(13, 0))
        if now.time() < trigger_time:
            return

        try:
            BiometricSyncStatus.objects.get_or_create(id=1)
            # Atomic compare-and-swap: only the request that actually
            # changes last_run_date "wins" and gets to trigger the job.
            claimed = BiometricSyncStatus.objects.filter(
                id=1
            ).exclude(last_run_date=now.date()).update(last_run_date=now.date())

            if claimed:
                threading.Thread(target=self._run_fetch, daemon=True).start()
        except Exception:
            logger.exception('Biometric daily sync check failed')

    @staticmethod
    def _run_fetch():
        try:
            call_command('fetch_biometric_data')
        except Exception:
            logger.exception('fetch_biometric_data failed during scheduled trigger')