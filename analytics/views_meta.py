from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ingest.models import DatasetRow
import re

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

class DatasetKeysView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id: int):
        limit = int(request.query_params.get("limit", 1000))
        qs = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id")[:limit]
        counters = {}
        samples = {}
        for row in qs:
            data = row.data or {}
            for k, v in data.items():
                if k not in counters:
                    counters[k] = {"num": 0, "date": 0, "text": 0, "total": 0}
                    samples[k] = []
                c = counters[k]
                c["total"] += 1
                if v is None or v == "":
                    continue
                # number?
                try:
                    fv = float(v)
                    if fv == fv and fv != float("inf") and fv != float("-inf"):
                        c["num"] += 1
                        if len(samples[k]) < 3: samples[k].append(v)
                        continue
                except Exception:
                    pass
                # date (ISO)
                if isinstance(v, str) and ISO_DATE.match(v):
                    c["date"] += 1
                    if len(samples[k]) < 3: samples[k].append(v)
                    continue
                c["text"] += 1
                if len(samples[k]) < 3: samples[k].append(v)

        keys_numeric = []
        keys_date = []
        keys_text = []
        for k, c in counters.items():
            if c["date"] > 0:
                keys_date.append(k)
            elif c["num"] > 0 and c["text"] == 0:
                keys_numeric.append(k)
            else:
                keys_text.append(k)

        return Response({
            "keys_all": sorted(list(counters.keys())),
            "keys_numeric": sorted(keys_numeric),
            "keys_date": sorted(keys_date),
            "keys_text": sorted(keys_text),
            "samples": samples,
        })


class DatasetDistinctView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id: int):
        field = request.query_params.get("field")
        if not field:
            return Response({"detail": "field is required"}, status=400)
        limit = int(request.query_params.get("limit", 200))
        qs = DatasetRow.objects.filter(dataset_id=dataset_id).values_list("data", flat=True)[:5000]
        seen = {}
        for d in qs:
            if not isinstance(d, dict): continue
            v = d.get(field, None)
            if v is None or v == "": continue
            s = str(v)
            if s not in seen:
                seen[s] = 1
                if len(seen) >= limit:
                    break
        return Response({"values": list(seen.keys())})

