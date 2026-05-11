from django.core.management.base import BaseCommand, CommandError

from chain.services.zakupki import digits_only, sync_contracts_by_inn


class Command(BaseCommand):
    help = 'Загружает реальные контракты 44-ФЗ из zakupki.gov.ru по ИНН.'

    def add_arguments(self, parser):
        parser.add_argument('inn', type=str, help='ИНН заказчика или поставщика')
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Сколько строк запрашивать в каждой выгрузке ЕИС, максимум 500',
        )

    def handle(self, *args, **options):
        inn = digits_only(options['inn'])

        if len(inn) not in (10, 12):
            raise CommandError('ИНН должен содержать 10 или 12 цифр.')

        result = sync_contracts_by_inn(inn, limit=options['limit'])

        if not result.enabled:
            self.stdout.write(self.style.WARNING('Автообновление ЕИС отключено в настройках.'))
            return

        for error in result.errors:
            self.stderr.write(self.style.WARNING(error))

        self.stdout.write(
            self.style.SUCCESS(
                'Готово. '
                f'Получено строк: {result.fetched}. '
                f'Добавлено: {result.imported}. '
                f'Обновлено: {result.updated}. '
                f'Пропущено: {result.skipped}.'
            )
        )

        if result.source_urls:
            self.stdout.write('Проверочные ссылки ЕИС:')
            for url in result.source_urls:
                self.stdout.write(url)
