from django.db.models import Count, Min, Max
from django.db.models.functions import Cast
from django.db.models import CharField, DecimalField, DateField
from django.db.models.fields.json import KeyTextTransform
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ingest.models import DatasetRow

DEC = DecimalField(max_digits=24, decimal_places=6)

class FacetsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, dataset_id: int):
        keys = request.query_params.getlist("keys")
        if not keys:
            return Response({"facets": {}}, status=200)

        qs = DatasetRow.objects.filter(dataset_id=dataset_id)
        facets = {}

        for k in keys:
            txt = KeyTextTransform(k, "data")
            # текстовые top-значения
            tops = (qs
              .annotate(_val=Cast(txt, CharField()))
              .values("_val")
              .exclude(_val__isnull=True)
              .exclude(_val__exact="")
              .annotate(n=Count("*"))
              .order_by("-n")[:50])
            facets[k] = {"top": [{"value": t["_val"], "count": t["n"]} for t in tops]}

            # числовой/датовый диапазон
            num = (qs
              .annotate(_n=Cast(txt, DEC))
              .aggregate(min=Min("_n"), max=Max("_n")))
            if num["min"] is not None or num["max"] is not None:
                facets[k]["numeric_range"] = num

            dt = (qs
              .annotate(_d=Cast(txt, DateField()))
              .aggregate(min=Min("_d"), max=Max("_d")))
            if dt["min"]:
                facets[k]["date_range"] = {"min": dt["min"], "max": dt["max"]}

        return Response({"facets": facets})
