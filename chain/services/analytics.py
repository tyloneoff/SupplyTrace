import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone


CLOSED_COUNTERPARTY_KEY = '__closed_supplier__'


def get_company_contracts(company):
    from chain.models import Contract

    one_year_ago = timezone.localdate() - timedelta(days=365)

    return (
        Contract.objects
        .select_related('customer', 'supplier')
        .filter(Q(customer=company) | Q(supplier=company), date__gte=one_year_ago)
        .order_by('-date')
    )


def get_counterparty_stats(company, contracts):
    stats = {}

    for contract in contracts:
        info = get_counterparty_info(company, contract)
        if info is None:
            continue

        item = stats.setdefault(info['key'], {
            'company': info['company'],
            'display_name': info['display_name'],
            'inn': info['inn'],
            'role': info['role'],
            'is_closed': info['is_closed'],
            'count': 0,
            'total_price': Decimal('0'),
        })

        item['count'] += 1
        item['total_price'] += contract.price or Decimal('0')

    return sorted(
        stats.values(),
        key=lambda item: (item['count'], item['total_price']),
        reverse=True,
    )


def get_counterparty_info(company, contract):
    if contract.customer_id == company.id:
        if contract.supplier and contract.supplier_disclosed:
            return {
                'key': contract.supplier.inn,
                'company': contract.supplier,
                'display_name': contract.supplier.name,
                'inn': contract.supplier.inn,
                'role': 'Поставщик',
                'is_closed': False,
            }

        return {
            'key': CLOSED_COUNTERPARTY_KEY,
            'company': None,
            'display_name': 'Победитель не раскрыт',
            'inn': '',
            'role': 'Закрытый тендер',
            'is_closed': True,
        }

    if contract.supplier_id == company.id:
        return {
            'key': contract.customer.inn,
            'company': contract.customer,
            'display_name': contract.customer.name,
            'inn': contract.customer.inn,
            'role': 'Заказчик',
            'is_closed': False,
        }

    return None


def shorten_name(name, max_len=32):
    if not name:
        return 'Без названия'

    name = ' '.join(name.split())

    replacements = {
        'ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ': 'ФГБОУ ВО',
        'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ': 'ООО',
        'АКЦИОНЕРНОЕ ОБЩЕСТВО': 'АО',
        'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО': 'ПАО',
        'ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ': 'ИП',
    }

    upper_name = name.upper()

    for long_text, short_text in replacements.items():
        upper_name = upper_name.replace(long_text, short_text)

    if len(upper_name) <= max_len:
        return upper_name

    return upper_name[:max_len - 3] + '...'


def build_graph_data(company, contracts, limit=10, contract_limit=30):
    counterparty_stats = get_counterparty_stats(company, contracts)
    shown_counterparties = counterparty_stats[:limit]
    closed_stat = next((item for item in counterparty_stats if item['is_closed']), None)
    if closed_stat and all(not item['is_closed'] for item in shown_counterparties):
        shown_counterparties = [*shown_counterparties[:max(limit - 1, 0)], closed_stat]
    shown_keys = {item['inn'] or CLOSED_COUNTERPARTY_KEY for item in shown_counterparties}

    visible_contracts = [
        contract
        for contract in contracts
        if (info := get_counterparty_info(company, contract)) and info['key'] in shown_keys
    ][:contract_limit]

    nodes = [
        {
            'id': company.inn,
            'label': f'{shorten_name(company.name, 36)}\nИНН {company.inn}',
            'group': 'main',
            'x': 0,
            'y': 0,
            'fixed': True,
            'title': f'{company.name}<br>ИНН: {company.inn}',
        }
    ]
    edges = []
    added_counterparties = set()

    contract_radius = 210
    counterparty_radius = 420
    visible_count = max(len(visible_contracts), 1)

    for index, contract in enumerate(visible_contracts):
        info = get_counterparty_info(company, contract)
        if info is None:
            continue

        angle = 2 * math.pi * index / visible_count
        contract_node_id = f'contract:{contract.id}'
        counterparty_node_id = info['inn'] or f'closed:{contract.id}'

        contract_x = int(contract_radius * math.cos(angle))
        contract_y = int(contract_radius * math.sin(angle))
        counterparty_x = int(counterparty_radius * math.cos(angle))
        counterparty_y = int(counterparty_radius * math.sin(angle))

        nodes.append({
            'id': contract_node_id,
            'label': f'{shorten_name(contract.title or contract.number, 34)}\n{format_price(contract.price)}',
            'group': 'closed_contract' if contract.is_closed else 'contract',
            'x': contract_x,
            'y': contract_y,
            'fixed': True,
            'title': (
                f'Номер: {contract.number}<br>'
                f'Дата: {contract.date or "не указана"}<br>'
                f'Предмет: {contract.title or "не указан"}<br>'
                f'Сумма: {format_price(contract.price)}<br>'
                f'Статус: {"закрытый тендер" if contract.is_closed else "открытый контракт"}'
            ),
        })

        if counterparty_node_id not in added_counterparties:
            added_counterparties.add(counterparty_node_id)
            nodes.append({
                'id': counterparty_node_id,
                'label': build_counterparty_label(info),
                'group': 'closed' if info['is_closed'] else ('supplier' if info['role'] == 'Поставщик' else 'customer'),
                'x': counterparty_x,
                'y': counterparty_y,
                'fixed': True,
                'title': build_counterparty_title(info),
            })

        if contract.customer_id == company.id:
            edges.append({
                'from': company.inn,
                'to': contract_node_id,
                'arrows': 'to',
                'title': 'Компания выступает заказчиком',
            })
            edges.append({
                'from': contract_node_id,
                'to': counterparty_node_id,
                'arrows': 'to',
                'title': 'Поставщик или победитель закупки',
            })
        else:
            edges.append({
                'from': counterparty_node_id,
                'to': contract_node_id,
                'arrows': 'to',
                'title': 'Заказчик закупки',
            })
            edges.append({
                'from': contract_node_id,
                'to': company.inn,
                'arrows': 'to',
                'title': 'Компания выступает поставщиком',
            })

    return {
        'nodes': nodes,
        'edges': edges,
        'shown_count': len(shown_counterparties),
        'total_count': len(counterparty_stats),
        'contracts_shown_count': len(visible_contracts),
        'contracts_total_count': len(contracts),
    }


def build_counterparty_label(info):
    if info['is_closed']:
        return 'Победитель\nне раскрыт'
    return f'{shorten_name(info["display_name"], 28)}\nИНН {info["inn"]}'


def build_counterparty_title(info):
    if info['is_closed']:
        return 'Закрытый тендер<br>Победитель или поставщик не раскрыт'
    return f'{info["display_name"]}<br>ИНН: {info["inn"]}<br>Роль: {info["role"]}'


def format_price(value):
    if value in (None, ''):
        return 'сумма не указана'

    value = Decimal(value)
    if value == 0:
        return 'сумма не указана'

    return f'{value:,.2f} ₽'.replace(',', ' ')
