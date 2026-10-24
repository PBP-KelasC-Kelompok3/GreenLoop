from django.apps import AppConfig


class WasteRewardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'waste_reward'
    verbose_name = 'Waste & Reward'

    def ready(self):
        from .signals import connect_pickup_signals

        connect_pickup_signals()
