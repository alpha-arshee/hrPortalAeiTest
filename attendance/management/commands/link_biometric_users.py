from django.core.management.base import BaseCommand

from attendance.models import BiometricLog


class Command(BaseCommand):
    help = 'Link BiometricLog entries to User by matching employee_id -> User.employee_id'

    def handle(self, *args, **options):
        total = 0
        linked = 0
        skipped = 0

        qs = BiometricLog.objects.filter(user__isnull=True).exclude(employee_id__isnull=True).exclude(employee_id__exact='')
        total = qs.count()

        for log in qs:
            try:
                # Attempt to find a matching user by employee_id
                user = None
                try:
                    from accounts.models import User
                    user = User.objects.filter(employee_id=log.employee_id).first()
                except Exception:
                    user = None

                if user:
                    log.user = user
                    log.save()
                    linked += 1
                else:
                    skipped += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed linking log id={getattr(log, 'id', '?')}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Scanned {total} biometric logs: linked={linked}, skipped={skipped}"))
