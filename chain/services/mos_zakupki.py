from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import requests
from django.conf import settings

from chain.services.zakupki import (
    ContractData,
    ZakupkiSyncResult,
    digits_only,
    get_contract_date_from,
    save_contract,
)


MOS_CONTRACT_QUERY_URL = 'https://zakupki.mos.ru/newapi/api/Contract/Query'
MOS_CONTRACT_PUBLIC_URL = 'https://zakupki.mos.ru/contract/{entity_id}'
MAX_MOS_ROWS = 100


def sync_mos_contracts_by_inn(inn, limit=None):
    """Loads public supplier portal contracts for Moscow and partner regions."""
    if not getattr(settings, 'ZAKUPKI_MOS_SYNC_ENABLED', True):
        return ZakupkiSyncResult(enabled=False)

    clean_inn = digits_only(inn)
    export_limit = limit or getattr(settings, 'ZAKUPKI_CONTRACTS_LIMIT', 100)
    export_limit = max(1, min(int(export_limit), MAX_MOS_ROWS))
    date_from = get_contract_date_from()

    result = ZakupkiSyncResult()

    if len(clean_inn) not in (10, 12):
        result.errors.append('Некорректный ИНН: нужно 10 или 12 цифр.')
        return result

    session = requests.Session()
    seen = set()

    for role, filter_field in (
        ('customer', 'customerKeyword'),
        ('supplier', 'supplierKeyword'),
    ):
        query_filter = build_query_filter(clean_inn, filter_field, export_limit)
        result.source_urls.append(build_source_url(query_filter))

        try:
            payload = fetch_contracts(session, query_filter)
        except requests.RequestException as exc:
            result.errors.append(f'Портал поставщиков временно недоступен для роли "{role}": {exc}')
            continue
        except ValueError as exc:
            result.errors.append(f'Ответ Портала поставщиков для роли "{role}" не удалось разобрать: {exc}')
            continue

        rows = payload.get('items') or []
        result.fetched += len(rows)

        for item in rows:
            try:
                contract_data = parse_mos_contract_item(item)
            except ValueError:
                result.skipped += 1
                continue

            if contract_data.date and contract_data.date < date_from:
                continue

            if not contract_matches_role(contract_data, clean_inn, role):
                result.skipped += 1
                continue

            if contract_data.key in seen:
                continue

            seen.add(contract_data.key)
            saved_status = save_contract(contract_data, source_file=f'zakupki.mos.ru:{role}')

            if saved_status == 'created':
                result.imported += 1
            elif saved_status == 'updated':
                result.updated += 1
            else:
                result.unchanged += 1

    return result


def build_query_filter(inn, filter_field, limit):
    return {
        'filter': {
            filter_field: {
                'value': inn,
            },
        },
        'order': [
            {
                'field': 'conclusionDate',
                'desc': True,
            },
        ],
        'take': limit,
        'skip': 0,
        'withCount': True,
    }


def build_source_url(query_filter):
    return f'{MOS_CONTRACT_QUERY_URL}?{urlencode({"queryFilter": to_json(query_filter)})}'


def fetch_contracts(session, query_filter):
    response = session.get(
        MOS_CONTRACT_QUERY_URL,
        params={'queryFilter': to_json(query_filter)},
        headers={
            'Accept': 'application/json',
            'User-Agent': getattr(settings, 'ZAKUPKI_USER_AGENT', 'SupplyTrace/1.0'),
        },
        timeout=getattr(settings, 'ZAKUPKI_TIMEOUT', 25),
    )
    response.raise_for_status()

    content_type = response.headers.get('content-type', '')
    if 'application/json' not in content_type:
        raise ValueError('получена HTML-страница вместо JSON')

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError('ожидался JSON-объект')

    return data


def parse_mos_contract_item(item):
    customer = item.get('customer') or {}
    supplier = item.get('supplier') or {}

    number = clean(item.get('registerNumber') or item.get('number') or item.get('id'))
    customer_inn = digits_only(customer.get('inn'))
    supplier_inn = digits_only(supplier.get('inn'))
    supplier_name = clean(supplier.get('name'))
    supplier_disclosed = bool(supplier_inn)

    if not number:
        raise ValueError('нет номера контракта')
    if not customer_inn:
        raise ValueError('нет ИНН заказчика')

    return ContractData(
        number=number,
        title=clean(item.get('subject')),
        price=parse_mos_price(item.get('rubSum')),
        date=parse_mos_date(item.get('conclusionDate')),
        execution_date=parse_optional_mos_date(
            item.get('executionDate')
            or item.get('completionDate')
            or item.get('endDate')
        ),
        customer_inn=customer_inn,
        customer_name=clean(customer.get('name')) or f'Компания {customer_inn}',
        customer_kpp=digits_only(customer.get('kpp')),
        supplier_inn=supplier_inn,
        supplier_name=supplier_name or (f'Компания {supplier_inn}' if supplier_inn else ''),
        supplier_kpp=digits_only(supplier.get('kpp')),
        is_closed=not supplier_disclosed,
        supplier_disclosed=supplier_disclosed,
        source_url=build_contract_url(item),
    )


def contract_matches_role(contract_data, inn, role):
    if role == 'customer':
        return contract_data.customer_inn == inn
    if role == 'supplier':
        return contract_data.supplier_inn == inn
    return False


def build_contract_url(item):
    entity_id = item.get('entityId') or item.get('id')
    if entity_id:
        return MOS_CONTRACT_PUBLIC_URL.format(entity_id=entity_id)
    return 'https://zakupki.mos.ru/contract/list'


def parse_mos_price(value):
    if value in (None, ''):
        return Decimal('0')

    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'некорректная сумма: {value}') from exc


def parse_mos_date(value):
    value = clean(value)
    if not value:
        return None

    for date_format in ('%d.%m.%Y %H:%M:%S', '%d.%m.%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(value.split('.')[0] if 'T' in value else value, date_format).date()
        except ValueError:
            continue

    raise ValueError(f'некорректная дата: {value}')


def parse_optional_mos_date(value):
    if value in (None, ''):
        return None
    return parse_mos_date(value)


def to_json(value):
    import json

    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def clean(value):
    if value is None:
        return ''
    return str(value).strip()
