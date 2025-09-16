# analytics/views_table_preview.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ingest.models import DatasetRow

class DatasetPreview(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id: int):
        limit = int(request.query_params.get("limit", 50))
        rows = (DatasetRow.objects
                .filter(dataset_id=dataset_id)
                .order_by("id")
                .values_list("data", flat=True)[:limit])

        # соберём пул колонок (первые 500 строк)
        sample = (DatasetRow.objects
                  .filter(dataset_id=dataset_id)
                  .values_list("data", flat=True)[:500])
        cols = []
        seen = set()
        for d in sample:
            if isinstance(d, dict):
                for k in d.keys():
                    if k not in seen:
                        seen.add(k); cols.append(k)

        # плоские строки в том же порядке колонок
        out_rows = []
        for d in rows:
            row = [ (d or {}).get(c, None) for c in cols ]
            out_rows.append(row)

        return Response({"columns": cols, "rows": out_rows})
