from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chain.models import Company, Contract


REQUIRED_COLUMNS = {
    'number',
    'date',
    'price',
    'customer_inn',
    'customer_name',
}


class Command(BaseCommand):
    help = 'Импортирует демонстрационные контракты из CSV-файла.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Путь к CSV-файлу с контрактами')

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path'])

        if not csv_path.exists():
            raise CommandError(f'Файл не найден: {csv_path}')

        imported = 0
        skipped = 0

        with csv_path.open('r', encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise CommandError('CSV-файл пустой или без заголовков.')

            missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing_columns:
                raise CommandError('Не хватает колонок: ' + ', '.join(sorted(missing_columns)))

            for row_number, row in enumerate(reader, start=2):
                try:
                    self.import_row(row, csv_path.name)
                    imported += 1
                except Exception as exc:
                    skipped += 1
                    self.stderr.write(self.style.WARNING(f'Строка {row_number} пропущена: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'Готово. Импортировано: {imported}. Пропущено: {skipped}.'))

    @transaction.atomic
    def import_row(self, row, source_file):
        number = clean(row.get('number'))
        customer_inn = clean(row.get('customer_inn'))
        supplier_inn = clean(row.get('supplier_inn'))
        supplier_name = clean(row.get('supplier_name'))
        is_closed = parse_bool(row.get('is_closed'))
        supplier_disclosed = not is_closed and bool(supplier_inn)

        if not number:
            raise ValueError('нет номера контракта')
        if not customer_inn:
            raise ValueError('нет ИНН заказчика')

        customer = self.get_or_create_company(
            inn=customer_inn,
            name=clean(row.get('customer_name')) or f'Компания {customer_inn}',
            kpp=clean(row.get('customer_kpp')),
            ogrn=clean(row.get('customer_ogrn')),
        )
        supplier = None

        if supplier_disclosed:
            if not supplier_inn:
                raise ValueError('нет ИНН поставщика для открытого контракта')

            supplier = self.get_or_create_company(
                inn=supplier_inn,
                name=supplier_name or f'Компания {supplier_inn}',
                kpp=clean(row.get('supplier_kpp')),
                ogrn=clean(row.get('supplier_ogrn')),
            )

        Contract.objects.update_or_create(
            number=number,
            customer=customer,
            supplier=supplier,
            defaults={
                'title': clean(row.get('title')),
                'price': parse_price(row.get('price')),
                'date': parse_date(row.get('date')),
                'purchase_url': clean(row.get('purchase_url')),
                'source_file': source_file,
                'is_closed': is_closed,
                'supplier_disclosed': supplier_disclosed,
            },
        )

    def get_or_create_company(self, inn, name, kpp='', ogrn=''):
        company, _ = Company.objects.update_or_create(
            inn=inn,
            defaults={
                'name': name,
                'kpp': kpp,
                'ogrn': ogrn,
            },
        )
        return company


def clean(value):
    if value is None:
        return ''
    return str(value).strip()


def parse_price(value):
    value = clean(value).replace(' ', '').replace(',', '.')
    if not value:
        return Decimal('0')
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f'некорректная сумма: {value}') from exc


def parse_date(value):
    value = clean(value)
    if not value:
        return None

    for date_format in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            pass

    raise ValueError(f'некорректная дата: {value}')


def parse_bool(value):
    value = clean(value).lower()
    return value in {'1', 'true', 'yes', 'y', 'да', 'закрыт', 'закрытый'}
