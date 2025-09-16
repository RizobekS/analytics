# analytics/views_export.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse
from ingest.models import DatasetRow
import csv, io

class DatasetExportCSV(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, dataset_id: int):
        # Собираем колонки из первых 500 строк
        sample = DatasetRow.objects.filter(dataset_id=dataset_id).values_list('data', flat=True)[:500]
        cols, seen = [], set()
        for d in sample:
            if isinstance(d, dict):
                for k in d.keys():
                    if k not in seen: seen.add(k); cols.append(k)

        rows = DatasetRow.objects.filter(dataset_id=dataset_id).values_list('data', flat=True).iterator()

        class Echo:  # потоковая запись
            def write(self, value): return value

        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer, delimiter=';', quoting=csv.QUOTE_MINIMAL)

        def rowgen():
            yield writer.writerow(cols)
            for d in rows:
                d = d or {}
                yield writer.writerow([d.get(c, '') for c in cols])

        resp = StreamingHttpResponse(rowgen(), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="dataset_{dataset_id}.csv"'
        return resp
