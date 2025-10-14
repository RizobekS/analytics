from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DatasetViewSet, DatasetRowViewSet, HandleRegistryViewSet
from .views_dashboards import DashboardViewSet, ChartConfigViewSet, DashboardView, MIITGrpDashboardView
from .views_aggregate import AggregateView
from .views_meta import DatasetKeysView, DatasetDistinctView
from .views_facets import FacetsView
from .views_datasets import DatasetTableView
from .views_table_preview import DatasetPreview
from .views_export import DatasetExportCSV
from .views_editable import EditableSchemaView, EditableRowsView
from .views_resolve import DatasetResolveView, WorkbookPeriodsView, ResolveRowsView
from .views_editable_resolve import (
    ResolveOrCreateWorkbookView,
    EditableResolveSchemaView,
    EditableResolveRowsView,
)
from .views_dashboard_cards_rows import DashboardCardsRowsView
from .views_ingest_upload import UploadXLSXView

router = DefaultRouter()
router.register(r"datasets", DatasetViewSet, basename="dataset")
router.register(r"dashboards", DashboardViewSet, basename="dashboard")
router.register(r"charts", ChartConfigViewSet, basename="chart")
router.register(r"handles", HandleRegistryViewSet, basename="handle")

urlpatterns = [
    path("dashboard/cards/rows", DashboardCardsRowsView.as_view(), name="dashboard-cards-rows"),
    path("workbooks/resolve-or-create/", ResolveOrCreateWorkbookView.as_view(), name="workbook-resolve-or-create"),
    path("editable/resolve/schema/",    EditableResolveSchemaView.as_view(),  name="editable-resolve-schema"),
    path("editable/resolve/rows/",      EditableResolveRowsView.as_view(),    name="editable-resolve-rows"),
    path("workbooks/periods/", WorkbookPeriodsView.as_view(), name="workbook-periods"),
    path("datasets/resolve/rows/", ResolveRowsView.as_view(), name="dataset-resolve-rows"),
    path("datasets/resolve/", DatasetResolveView.as_view(), name="dataset-resolve"),

    path("editable/<int:dataset_id>/schema/", EditableSchemaView.as_view(), name="editable-schema"),
    path("editable/<int:dataset_id>/rows/",   EditableRowsView.as_view(),   name="editable-rows"),
    path("datasets/<int:dataset_id>/rows/", DatasetRowViewSet.as_view({"get": "list"}), name="dataset-rows"),
    path("ingest/upload-xlsx", UploadXLSXView.as_view(), name="ingest-upload-xlsx"),
    # агрегатор
    path("aggregate/", AggregateView.as_view(), name="aggregate"),
    path("datasets/<int:dataset_id>/keys", DatasetKeysView.as_view(), name="dataset-keys"),
    path("datasets/<int:dataset_id>/distinct", DatasetDistinctView.as_view(), name="dataset-distinct"),
    path("dashboard/", DashboardView.as_view(), name="dashboard-page"),
    path("datasets/<int:dataset_id>/facets", FacetsView.as_view(), name="dataset-facets"),
    path("datasets/<int:dataset_id>/preview", DatasetPreview.as_view(), name="dataset-preview"),
    path("table/<int:dataset_id>/", DatasetTableView.as_view(), name="dataset-table-page"),
    path("datasets/<int:dataset_id>/export.csv", DatasetExportCSV.as_view(), name="dataset-export-csv"),
    path("miit/grp/", MIITGrpDashboardView.as_view(), name="miit-grp"),
    *router.urls,
]
