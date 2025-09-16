from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DatasetViewSet, DatasetRowViewSet
from .views_dashboards import DashboardViewSet, ChartConfigViewSet, DashboardView, MIITGrpDashboardView
from .views_aggregate import AggregateView
from .views_meta import DatasetKeysView, DatasetDistinctView
from .views_facets import FacetsView
from .views_datasets import DatasetTableView
from .views_table_preview import DatasetPreview
from .views_export import DatasetExportCSV

router = DefaultRouter()
router.register(r"datasets", DatasetViewSet, basename="dataset")
router.register(r"dashboards", DashboardViewSet, basename="dashboard")
router.register(r"charts", ChartConfigViewSet, basename="chart")

urlpatterns = [
    *router.urls,
    path("datasets/<int:dataset_id>/rows/", DatasetRowViewSet.as_view({"get": "list"}), name="dataset-rows"),
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

]
