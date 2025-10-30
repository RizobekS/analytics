from django.apps import AppConfig


class EgovuzProviderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'egovuz_provider'
    label = "egovuz_provider"
    verbose_name = "Allauth Provider: id.egov.uz"

    def ready(self):
        import egovuz_provider.signals
        import egovuz_provider.egov_sync
