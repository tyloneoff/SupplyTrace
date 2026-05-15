import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from chain.models import Company, Contract


ZAKUPKI_SEARCH_URL = 'https://zakupki.gov.ru/epz/contract/search/results.html'
ZAKUPKI_CSV_URL = 'https://zakupki.gov.ru/epz/contract/contractCsvSettings/download.html'
MAX_EXPORT_ROWS = 500

CSV_FLAGS = {
    'numberRegisterContractCsv': 'true',
    'customerNameCsv': 'true',
    'customerInnCsv': 'true',
    'customerKppCsv': 'true',
    'contractDateCsv': 'true',
    'contractNumberCsv': 'true',
    'contractSubjectNameCsv': 'true',
    'contractPriceCsv': 'true',
    'infoSupplierNameCsv': 'true',
    'infoSupplierInnCsv': 'true',
    'infoSupplierKppCsv': 'true',
    'dateContractCsv': 'true',
}

BASE_PARAMS = {
    'morphology': 'on',
    'search-filter': 'Дате размещения',
    'fz44': 'on',
    'contractStageList_0': 'on',
    'contractStageList_1': 'on',
    'contractStageList_2': 'on',
    'contractStageList_3': 'on',
    'contractStageList': '0,1,2,3',
    'selectedContractDataChanges': 'ANY',
    'contractCurrencyID': '-1',
    'budgetLevelsIdNameHidden': '{}',
    'sortBy': 'UPDATE_DATE',
    'pageNumber': '1',
    'sortDirection': 'false',
    'recordsPerPage': '_50',
    'showLotsInfoHidden': 'false',
}

def clean(value):
    if value is None:
        return ''

    value = str(value).strip()

    if value.startswith("'"):
        value = value[1:]
    if value.endswith("'"):
        value = value[:-1]

    return value.strip()


def _normalize_header(value):
    value = clean(value).lower().replace('ё', 'е')
    return re.sub(r'[^0-9a-zа-я]+', '', value)


FIELD_ALIASES = {
    'number': (
        'номер реестровой записи контракта',
        'номер реестровой записи',
        'реестровый номер контракта',
        'реестровый номер',
        'number',
    ),
    'date': (
        'дата заключения контракта',
        'дата контракта',
        'дата заключения',
        'контракт дата',
        'contract date',
        'date',
    ),
    'execution_date': (
        'дата исполнения контракта по контракту',
        'дата исполнения контракта',
        'дата исполнения',
        'срок исполнения',
        'execution date',
    ),
    'price': (
        'цена контракта',
        'цена заключенных контрактов',
        'цена контракта руб',
        'сумма',
        'price',
    ),
    'title': (
        'предмет контракта',
        'объект закупки',
        'наименование товара услуги',
        'contract subject',
        'title',
    ),
    'customer_name': (
        'наименование заказчика',
        'наименование организации заказчика',
        'заказчик наименование',
        'заказчик',
        'customer name',
    ),
    'customer_inn': (
        'инн заказчика',
        'заказчик инн',
        'customer inn',
    ),
    'customer_kpp': (
        'кпп заказчика',
        'заказчик кпп',
        'customer kpp',
    ),
    'supplier_name': (
        'наименование поставщика',
        'наименование поставщика подрядчика исполнителя',
        'наименование юридического лица фио физического лица поставщика',
        'информация о поставщиках исполнителях подрядчиках по контракту наименование юридического лица фио физического лица',
        'поставщик',
        'supplier name',
    ),
    'supplier_inn': (
        'инн поставщика',
        'инн поставщика подрядчика исполнителя',
        'информация о поставщиках исполнителях подрядчиках по контракту инн',
        'supplier inn',
    ),
    'supplier_kpp': (
        'кпп поставщика',
        'кпп поставщика подрядчика исполнителя',
        'информация о поставщиках исполнителях подрядчиках по контракту кпп',
        'supplier kpp',
    ),
}

NORMALIZED_ALIASES = {
    field: tuple(normalized for normalized in (_normalize_header(alias) for alias in aliases) if normalized)
    for field, aliases in FIELD_ALIASES.items()
}


@dataclass
class ContractData:
    number: str
    title: str
    price: Decimal
    date: object
    execution_date: object
    customer_inn: str
    customer_name: str
    customer_kpp: str
    supplier_inn: str
    supplier_name: str
    supplier_kpp: str
    is_closed: bool = False
    supplier_disclosed: bool = True
    source_url: str = ''

    @property
    def key(self):
        return self.number, self.customer_inn, self.supplier_inn or 'closed'


@dataclass
class ZakupkiSyncResult:
    enabled: bool = True
    fetched: int = 0
    imported: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)

    @property
    def saved(self):
        return self.imported + self.updated

    @property
    def has_errors(self):
        return bool(self.errors)


def sync_contracts_by_inn(inn, limit=None):
    """Loads current 44-FZ contracts from EIS and saves them to the local DB."""
    if not getattr(settings, 'ZAKUPKI_SYNC_ENABLED', True):
        return ZakupkiSyncResult(enabled=False)

    clean_inn = digits_only(inn)
    export_limit = limit or getattr(settings, 'ZAKUPKI_CONTRACTS_LIMIT', 100)
    export_limit = max(1, min(int(export_limit), MAX_EXPORT_ROWS))

    result = ZakupkiSyncResult()

    if len(clean_inn) not in (10, 12):
        result.errors.append('Некорректный ИНН: нужно 10 или 12 цифр.')
        return result

    session = requests.Session()
    seen = set()
    date_from = get_contract_date_from()

    for role in ('customer', 'supplier'):
        params = build_params(clean_inn, role, export_limit, date_from=date_from)
        result.source_urls.append(build_search_url(params))
        role_saved = 0

        try:
            rows = fetch_csv_rows(session, params)
        except requests.RequestException as exc:
            result.errors.append(f'ЕИС недоступна для роли "{role}": {exc}')
            continue
        except ValueError as exc:
            result.errors.append(f'Ответ ЕИС для роли "{role}" не удалось разобрать: {exc}')
            continue

        result.fetched += len(rows)

        for row in rows:
            try:
                contract_data = parse_contract_row(row)
            except ValueError:
                result.skipped += 1
                continue

            if not contract_matches_role(contract_data, clean_inn, role):
                result.skipped += 1
                continue

            if contract_data.key in seen:
                continue

            seen.add(contract_data.key)
            saved_status = save_contract(contract_data, source_file=f'zakupki.gov.ru:{role}')

            if saved_status == 'created':
                result.imported += 1
            elif saved_status == 'updated':
                result.updated += 1
            else:
                result.unchanged += 1

            role_saved += 1
            if role_saved >= export_limit:
                break

    return result


def build_params(inn, role, limit, date_from=None):
    date_from = date_from or get_contract_date_from()
    params = {
        **BASE_PARAMS,
        **CSV_FLAGS,
        'from': '1',
        'to': str(limit),
        'contractDateFrom': format_date(date_from),
    }

    if role == 'customer':
        # In the 44-FZ registry number, the customer INN follows the leading registry digit.
        params['searchString'] = f'1{inn}'
    else:
        params['supplierTitle'] = inn
        params['countryRegIdNameHidden'] = '{}'

    return params


def contract_matches_role(contract_data, inn, role):
    if role == 'customer':
        return contract_data.customer_inn == inn
    if role == 'supplier':
        return contract_data.supplier_inn == inn
    raise ValueError(f'unknown zakupki role: {role}')


def get_contract_date_from():
    depth_days = int(getattr(settings, 'ZAKUPKI_CONTRACT_LOOKBACK_DAYS', 365))
    return timezone.localdate() - timedelta(days=max(1, depth_days))


def build_search_url(params):
    visible_params = {
        key: value
        for key, value in params.items()
        if key not in CSV_FLAGS and key not in {'from', 'to'}
    }
    return f'{ZAKUPKI_SEARCH_URL}?{urlencode(visible_params)}'


def fetch_csv_rows(session, params):
    response = session.get(
        ZAKUPKI_CSV_URL,
        params=params,
        headers={
            'Accept': 'text/csv,application/octet-stream,*/*',
            'User-Agent': getattr(settings, 'ZAKUPKI_USER_AGENT', 'SupplyTrace/1.0'),
        },
        timeout=getattr(settings, 'ZAKUPKI_TIMEOUT', 25),
    )
    response.raise_for_status()

    text = decode_response(response)

    if looks_like_html(text):
        raise ValueError('получена HTML-страница вместо CSV')

    return parse_csv(text)


def decode_response(response):
    encodings = [
        response.encoding,
        'utf-8-sig',
        'utf-8',
        'cp1251',
        'windows-1251',
    ]

    for encoding in dict.fromkeys(encoding for encoding in encodings if encoding):
        try:
            text = response.content.decode(encoding)
        except UnicodeDecodeError:
            continue

        if text.count('\ufffd') < 3:
            return text

    return response.content.decode('utf-8', errors='replace')


def parse_csv(text):
    text = text.lstrip('\ufeff')
    stream = io.StringIO(text)
    first_line = stream.readline()

    if first_line.lower().startswith('sep='):
        delimiter = first_line.strip()[-1] or ';'
        csv_text = stream.read()
    else:
        delimiter = detect_delimiter(text)
        csv_text = text

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

    if not reader.fieldnames:
        return []

    rows = []
    for row in reader:
        if any(clean(value) for value in row.values()):
            rows.append(row)

    return rows


def detect_delimiter(text):
    sample = text[:4096]

    try:
        return csv.Sniffer().sniff(sample, delimiters=';\t,').delimiter
    except csv.Error:
        return ';'


def parse_contract_row(row):
    normalized_row = {
        _normalize_header(key): value
        for key, value in row.items()
        if key
    }

    number = clean(get_field(normalized_row, 'number'))
    customer_inn = normalize_inn(get_field(normalized_row, 'customer_inn'))
    supplier_inn = normalize_inn(get_field(normalized_row, 'supplier_inn'))
    supplier_name = clean(get_field(normalized_row, 'supplier_name'))
    supplier_disclosed = bool(supplier_inn)

    if not number:
        raise ValueError('нет номера реестровой записи')
    if not customer_inn:
        raise ValueError('нет ИНН заказчика')

    return ContractData(
        number=number,
        title=clean(get_field(normalized_row, 'title')),
        price=parse_price(get_field(normalized_row, 'price')),
        date=parse_date(get_field(normalized_row, 'date')),
        execution_date=parse_date(get_field(normalized_row, 'execution_date')),
        customer_inn=customer_inn,
        customer_name=clean(get_field(normalized_row, 'customer_name')) or f'Компания {customer_inn}',
        customer_kpp=digits_only(get_field(normalized_row, 'customer_kpp')),
        supplier_inn=supplier_inn,
        supplier_name=supplier_name or (f'Компания {supplier_inn}' if supplier_inn else ''),
        supplier_kpp=digits_only(get_field(normalized_row, 'supplier_kpp')),
        is_closed=not supplier_disclosed,
        supplier_disclosed=supplier_disclosed,
        source_url=build_contract_url(number),
    )


def get_field(normalized_row, field):
    for alias in NORMALIZED_ALIASES[field]:
        if alias in normalized_row:
            return normalized_row[alias]

    for alias in NORMALIZED_ALIASES[field]:
        for key, value in normalized_row.items():
            if alias and (alias in key or key in alias):
                return value

    return ''


@transaction.atomic
def save_contract(contract_data, source_file):
    customer = save_company(
        contract_data.customer_inn,
        contract_data.customer_name,
        contract_data.customer_kpp,
    )
    supplier = None

    if contract_data.supplier_disclosed:
        supplier = save_company(
            contract_data.supplier_inn,
            contract_data.supplier_name,
            contract_data.supplier_kpp,
        )

    defaults = {
        'title': contract_data.title,
        'price': contract_data.price,
        'date': contract_data.date,
        'execution_date': contract_data.execution_date,
        'purchase_url': contract_data.source_url or build_contract_url(contract_data.number),
        'source_file': source_file,
        'is_closed': contract_data.is_closed,
        'supplier_disclosed': contract_data.supplier_disclosed,
    }

    contract, created = Contract.objects.get_or_create(
        number=contract_data.number,
        customer=customer,
        supplier=supplier,
        defaults=defaults,
    )

    if created:
        return 'created'

    updates = {
        field: value
        for field, value in defaults.items()
        if getattr(contract, field) != value
    }

    if not updates:
        return 'unchanged'

    for field, value in updates.items():
        setattr(contract, field, value)
    contract.save(update_fields=[*updates.keys()])

    return 'updated'


def save_company(inn, name, kpp='', ogrn=''):
    company, created = Company.objects.get_or_create(
        inn=inn,
        defaults={
            'name': name or f'Компания {inn}',
            'kpp': kpp,
            'ogrn': ogrn,
        },
    )

    if created:
        return company

    updates = {}

    if name and company.name != name:
        updates['name'] = name
    if kpp and company.kpp != kpp:
        updates['kpp'] = kpp
    if ogrn and company.ogrn != ogrn:
        updates['ogrn'] = ogrn

    if updates:
        for field, value in updates.items():
            setattr(company, field, value)
        company.save(update_fields=[*updates.keys()])

    return company


def build_contract_url(number):
    return f'https://zakupki.gov.ru/epz/contract/contractCard/common-info.html?reestrNumber={number}'


def parse_price(value):
    value = clean(value)

    if not value:
        return Decimal('0')

    value = value.replace('\xa0', '').replace(' ', '')
    value = re.sub(r'[^\d,.\-]', '', value)

    if ',' in value and '.' in value:
        value = value.replace('.', '').replace(',', '.')
    elif ',' in value:
        value = value.replace(',', '.')
    elif value.count('.') > 1:
        parts = value.split('.')
        value = ''.join(parts[:-1]) + '.' + parts[-1]

    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f'некорректная сумма: {value}') from exc


def parse_date(value):
    value = clean(value)

    if not value:
        return None

    value = value.split()[0]

    for date_format in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y'):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise ValueError(f'некорректная дата: {value}')


def format_date(value):
    return value.strftime('%d.%m.%Y')


def digits_only(value):
    return ''.join(char for char in clean(value) if char.isdigit())


def normalize_inn(value):
    value = clean(value)
    digit_groups = re.findall(r'\d+', value)

    for group in digit_groups:
        if len(group) in (10, 12):
            return group

    digits = ''.join(digit_groups)

    if len(digits) in (10, 12):
        return digits
    if len(digits) > 12 and len(digits) % 10 == 0:
        return digits[:10]
    if len(digits) > 12 and len(digits) % 12 == 0:
        return digits[:12]

    return digits


def looks_like_html(text):
    start = text[:300].lstrip().lower()
    return start.startswith('<!doctype') or start.startswith('<html') or '<html' in start
