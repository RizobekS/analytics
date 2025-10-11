# analytics/views_editable.py
from rest_framework import views, permissions, response, status
from django.db import transaction
from ingest.models import Dataset, DatasetRow, DataTemplate
from .validators import validate_row_against_template

class IsDatasetEditable(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj: Dataset):
        return obj.meta.get("editable", False)  # и тут можно добавить RBAC/роль

class EditableSchemaView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, dataset_id: int):
        ds = Dataset.objects.select_related().get(pk=dataset_id)
        if not ds.meta.get("editable"):
            return response.Response({"detail": "dataset is not editable"}, status=403)

        tmpl_id = ds.meta.get("template_id")
        if not tmpl_id:
            return response.Response({"detail": "template not bound"}, status=400)

        t = DataTemplate.objects.prefetch_related("mappings").get(pk=tmpl_id)
        cols = []
        for m in t.mappings.all().order_by("id"):
            cols.append({
                "key": m.canonical_key,
                "dtype": m.dtype,
                "required": m.required,
                "min": m.min_value,
                "max": m.max_value,
                "regex": m.regex,
                "choices": m.choices,
            })
        return response.Response({"columns": cols})

class EditableRowsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, dataset_id: int):
        # пагинация/поиск при желании
        qs = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id")
        data = [{"id": r.id, "version": r.revisions.count()+1, "data": r.data} for r in qs]
        return response.Response({"rows": data})

    @transaction.atomic
    def post(self, request, dataset_id: int):
        """
        BULK upsert/delete
        payload:
        {
          "upsert": [ {"id": null|int, "version": int, "data": {...}}, ... ],
          "delete_ids": [1,2,...]
        }
        """
        ds = Dataset.objects.get(pk=dataset_id)
        if not ds.meta.get("editable"):
            return response.Response({"detail": "dataset is not editable"}, status=403)

        tmpl_id = ds.meta.get("template_id")
        t = DataTemplate.objects.prefetch_related("mappings").get(pk=tmpl_id)

        upsert = request.data.get("upsert", [])
        delete_ids = request.data.get("delete_ids", [])

        # Удаление
        if delete_ids:
            DatasetRow.objects.filter(dataset_id=dataset_id, id__in=delete_ids).delete()

        # Upsert с валидацией и аудитом
        saved_ids = []
        errors = []

        for item in upsert:
            rid = item.get("id")
            ver = int(item.get("version") or 1)
            row_data = dict(item.get("data") or {})

            # валидация
            verrs = validate_row_against_template(row_data, t)
            if verrs:
                errors.append({"id": rid, "errors": verrs})
                continue

            if rid:
                # оптимистическая блокировка: текущая версия = ревизий + 1
                r = DatasetRow.objects.select_for_update().get(dataset_id=dataset_id, id=rid)
                current_version = r.revisions.count() + 1
                if ver != current_version:
                    errors.append({"id": rid, "errors": [f"конфликт версии (ожидали {current_version}, получили {ver})"]})
                    continue

                before = r.data
                r.data = row_data
                r.save()

                # аудит
                from ingest.models import DatasetRowRevision
                DatasetRowRevision.objects.create(
                    row=r, version=current_version, data_before=before, data_after=row_data, changed_by=request.user
                )
                saved_ids.append(r.id)
            else:
                r = DatasetRow.objects.create(dataset_id=dataset_id, data=row_data)
                # аудит первой версии
                from ingest.models import DatasetRowRevision
                DatasetRowRevision.objects.create(
                    row=r, version=1, data_before={}, data_after=row_data, changed_by=request.user
                )
                saved_ids.append(r.id)

        status_code = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return response.Response({"saved_ids": saved_ids, "errors": errors}, status=status_code)
