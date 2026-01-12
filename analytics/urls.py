from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import HandleRegistryViewSet, UploadHistoryView
from .views_egov_identity import EgovPinppLookupView
from .views_resolve import ResolveRowsView
from .views_dashboard_cards_rows import DashboardCardsRowsView
from .views_ingest_upload import UploadXLSXView
from .views_resolve import DatasetStatusUpdateView
from .views_users import UserViewSet, CurrentUserMeView

router = DefaultRouter()
router.register(r"handles", HandleRegistryViewSet, basename="handle")
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("dashboard/cards/rows/", DashboardCardsRowsView.as_view(), name="dashboard-cards-rows"),
    path("datasets/resolve/rows/", ResolveRowsView.as_view(), name="dataset-resolve-rows"),
    path("datasets/status/", DatasetStatusUpdateView.as_view(), name="dataset-status-update"),
    path("upload-history/", UploadHistoryView.as_view(), name="upload-history"),
    path("ingest/upload-xlsx/", UploadXLSXView.as_view(), name="ingest-upload-xlsx"),
    path("auth/me/", CurrentUserMeView.as_view(), name="auth-me"),
    path("egov/pinpp/", EgovPinppLookupView.as_view(), name="egov-pinpp-lookup"),
    *router.urls,
]
