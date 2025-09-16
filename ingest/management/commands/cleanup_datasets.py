from django.core.management.base import BaseCommand
from django.db.models import Count
from ingest.models import Dataset, Sheet

class Command(BaseCommand):
    help = "Удаляет пустые датасеты (без строк). Можно ограничить диапазон ID."

    def add_arguments(self, parser):
        parser.add_argument("--range", type=str, help="Диапазон ID, напр. 7:69")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--delete-empty-sheets", action="store_true",
                            help="Удалить листы без датасетов (и их ячейки)")

    def handle(self, *args, **opts):
        qs = Dataset.objects.all()
        if opts.get("range"):
            a, b = opts["range"].split(":")
            qs = qs.filter(id__gte=int(a), id__lte=int(b))
        qs = qs.annotate(n=Count("datasetrow")).filter(n=0)

        ids = list(qs.values_list("id", flat=True))
        self.stdout.write(f"Found empty datasets: {ids}")
        if opts["dry_run"]:
            return

        deleted = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted: {deleted}"))

        if opts["delete_empty_sheets"]:
            sheets_deleted = Sheet.objects.filter(dataset__isnull=True).delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted empty sheets: {sheets_deleted}"))
