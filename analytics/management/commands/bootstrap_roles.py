from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

class Command(BaseCommand):
    def handle(self, *args, **opts):
        viewer, _ = Group.objects.get_or_create(name="viewer")
        analyst, _ = Group.objects.get_or_create(name="analyst")
        admin,  _ = Group.objects.get_or_create(name="admin")

        # простая модель: viewer -> read only; analyst -> +управление dashboards; admin -> всё
        # При желании можно тонко раскидать разрешения по моделям Dashboard/ChartConfig.
        self.stdout.write("Groups created/updated.")