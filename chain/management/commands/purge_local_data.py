from django.core.management.base import BaseCommand

from chain.services.local_retention import purge_expired_local_data


class Command(BaseCommand):
    help = 'Удаляет локально сохранённые бизнес-данные SupplyTrace старше настроенного TTL.'

    def handle(self, *args, **options):
        result = purge_expired_local_data()

        self.stdout.write(
            self.style.SUCCESS(
                'Готово. '
                f'Удалено контрактов/закупок: {result["contracts"]}. '
                f'Компаний: {result["companies"]}. '
                f'Поисков: {result["searches"]}. '
                f'Записей журнала синхронизации: {result["sync_logs"]}.'
            )
        )
