from django.core.management.base import BaseCommand, CommandError

from chain.models import Company
from chain.services.company_lookup import get_or_create_company_by_inn
from chain.services.local_retention import purge_expired_local_data
from chain.services.public_sources import record_sync_result
from chain.services.zakupki import digits_only, sync_contracts_by_inn


class Command(BaseCommand):
    help = 'Загружает реальные контракты 44-ФЗ из zakupki.gov.ru по ИНН.'

    def add_arguments(self, parser):
        parser.add_argument('inn', type=str, help='ИНН заказчика или поставщика')
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Сколько релевантных контрактов сохранять для каждой роли ИНН, максимум 500',
        )

    def handle(self, *args, **options):
        purge_expired_local_data()
        inn = digits_only(options['inn'])

        if len(inn) not in (10, 12):
            raise CommandError('ИНН должен содержать 10 или 12 цифр.')

        result = sync_contracts_by_inn(inn, limit=options['limit'])

        company = Company.objects.filter(inn=inn).first() or get_or_create_company_by_inn(inn)
        if company:
            company.refresh_from_db()
            record_sync_result(company, result)

        if not result.enabled:
            self.stdout.write(self.style.WARNING('Обновление ЕИС отключено в настройках.'))
            return

        for error in result.errors:
            self.stderr.write(self.style.WARNING(error))

        self.stdout.write(
            self.style.SUCCESS(
                'Готово. '
                f'Получено строк: {result.fetched}. '
                f'Добавлено: {result.imported}. '
                f'Обновлено: {result.updated}. '
                f'Без изменений: {result.unchanged}. '
                f'Пропущено: {result.skipped}.'
            )
        )

        if result.source_urls:
            self.stdout.write('Проверочные ссылки ЕИС:')
            for url in result.source_urls:
                self.stdout.write(url)
