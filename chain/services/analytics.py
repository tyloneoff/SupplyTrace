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


def get_tender_summary(contracts):
    total = len(contracts)
    closed_count = sum(1 for contract in contracts if contract.is_closed)
    known_winner_count = sum(1 for contract in contracts if contract.has_known_supplier)

    return {
        'total': total,
        'open_count': total - closed_count,
        'closed_count': closed_count,
        'known_winner_count': known_winner_count,
        'undisclosed_winner_count': total - known_winner_count,
    }


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
            'role': 'Закрытая закупка',
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


def build_graph_data(company, contracts, limit=10, contract_limit=30, aggregate_threshold=18):
    counterparty_stats = get_counterparty_stats(company, contracts)
    shown_counterparties = counterparty_stats[:limit]
    closed_stat = next((item for item in counterparty_stats if item['is_closed']), None)
    if closed_stat and all(not item['is_closed'] for item in shown_counterparties):
        shown_counterparties = [*shown_counterparties[:max(limit - 1, 0)], closed_stat]
    shown_keys = {item['inn'] or CLOSED_COUNTERPARTY_KEY for item in shown_counterparties}
    stats_by_key = {
        item['inn'] or CLOSED_COUNTERPARTY_KEY: item
        for item in shown_counterparties
    }

    visible_contracts = [
        contract
        for contract in contracts
        if (info := get_counterparty_info(company, contract)) and info['key'] in shown_keys
    ][:contract_limit]
    grouped_contracts = group_contracts_by_counterparty(company, contracts, shown_keys)
    use_aggregated_edges = len(visible_contracts) > aggregate_threshold

    nodes = [
        {
            'id': company.inn,
            'label': f'{shorten_name(company.name, 36)}\nИНН {company.inn}',
            'group': 'main',
            'x': 0,
            'y': 0,
            'fixed': False,
            'title': build_plain_title(build_company_details(company, contracts)),
            'details': build_company_details(company, contracts),
            'role': 'central',
            'contracts_count': len(contracts),
            'total_price': str(sum((contract.price or Decimal('0')) for contract in contracts)),
        }
    ]
    edges = []
    added_counterparties = set()

    if use_aggregated_edges:
        add_aggregated_graph_items(company, shown_counterparties, grouped_contracts, nodes, edges)

        return {
            'nodes': nodes,
            'edges': edges,
            'mode': 'aggregated',
            'shown_count': len(shown_counterparties),
            'total_count': len(counterparty_stats),
            'contracts_shown_count': sum(len(items) for items in grouped_contracts.values()),
            'contracts_total_count': len(contracts),
        }

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
        edge_details = build_contract_edge_details(contract)

        nodes.append({
            'id': contract_node_id,
            'label': f'{shorten_name(contract.title or contract.number, 34)}\n{format_price(contract.price)}',
            'group': 'closed_contract' if contract.is_closed else 'contract',
            'x': contract_x,
            'y': contract_y,
            'fixed': False,
            'title': build_plain_title(build_contract_details(contract)),
            'details': build_contract_details(contract),
            'role': 'closed_contract' if contract.is_closed else 'contract',
            'status': contract.procurement_status_display,
            'amount': str(contract.price or Decimal('0')),
        })

        if counterparty_node_id not in added_counterparties:
            added_counterparties.add(counterparty_node_id)
            stat = stats_by_key.get(info['key'])
            nodes.append({
                'id': counterparty_node_id,
                'label': build_counterparty_label(info),
                'group': 'closed' if info['is_closed'] else ('supplier' if info['role'] == 'Поставщик' else 'customer'),
                'x': counterparty_x,
                'y': counterparty_y,
                'fixed': False,
                'title': build_plain_title(build_counterparty_details(info, stat)),
                'details': build_counterparty_details(info, stat),
                'role': info['role'],
                'contracts_count': stat['count'] if stat else 0,
                'total_price': str(stat['total_price'] if stat else Decimal('0')),
            })

        if contract.customer_id == company.id:
            edges.append({
                'from': company.inn,
                'to': contract_node_id,
                'arrows': 'to',
                'title': build_plain_title(edge_details),
                'details': edge_details,
                'role': 'customer_to_contract',
                'status': contract.procurement_status_display,
            })
            edges.append({
                'from': contract_node_id,
                'to': counterparty_node_id,
                'arrows': 'to',
                'title': build_plain_title(edge_details),
                'details': edge_details,
                'role': 'contract_to_supplier',
                'status': contract.procurement_status_display,
            })
        else:
            edges.append({
                'from': counterparty_node_id,
                'to': contract_node_id,
                'arrows': 'to',
                'title': build_plain_title(edge_details),
                'details': edge_details,
                'role': 'customer_to_contract',
                'status': contract.procurement_status_display,
            })
            edges.append({
                'from': contract_node_id,
                'to': company.inn,
                'arrows': 'to',
                'title': build_plain_title(edge_details),
                'details': edge_details,
                'role': 'contract_to_supplier',
                'status': contract.procurement_status_display,
            })

    return {
        'nodes': nodes,
        'edges': edges,
        'mode': 'detailed',
        'shown_count': len(shown_counterparties),
        'total_count': len(counterparty_stats),
        'contracts_shown_count': len(visible_contracts),
        'contracts_total_count': len(contracts),
    }


def group_contracts_by_counterparty(company, contracts, shown_keys):
    grouped = {key: [] for key in shown_keys}

    for contract in contracts:
        info = get_counterparty_info(company, contract)
        if info and info['key'] in shown_keys:
            grouped.setdefault(info['key'], []).append(contract)

    return grouped


def add_aggregated_graph_items(company, counterparties, grouped_contracts, nodes, edges):
    role_buckets = {
        'Заказчик': [],
        'Поставщик': [],
        'Закрытая закупка': [],
    }

    for item in counterparties:
        role_buckets.setdefault(item['role'], []).append(item)

    positioned = []
    positioned.extend(position_counterparty_bucket(role_buckets.get('Заказчик', []), -430))
    positioned.extend(position_counterparty_bucket(role_buckets.get('Поставщик', []), 430))
    positioned.extend(position_counterparty_bucket(role_buckets.get('Закрытая закупка', []), 0, y_offset=300))

    for item, x, y in positioned:
        node_id = item['inn'] or CLOSED_COUNTERPARTY_KEY
        info = {
            'display_name': item['display_name'],
            'inn': item['inn'],
            'role': item['role'],
            'is_closed': item['is_closed'],
        }
        contracts_for_item = grouped_contracts.get(item['inn'] or CLOSED_COUNTERPARTY_KEY, [])
        node_details = build_counterparty_details(info, item)
        edge_details = build_aggregated_edge_details(company, item, contracts_for_item)

        nodes.append({
            'id': node_id,
            'label': build_counterparty_label(info),
            'group': 'closed' if item['is_closed'] else ('supplier' if item['role'] == 'Поставщик' else 'customer'),
            'x': x,
            'y': y,
            'fixed': False,
            'title': build_plain_title(node_details),
            'details': node_details,
            'role': item['role'],
            'contracts_count': item['count'],
            'total_price': str(item['total_price']),
        })

        if item['role'] == 'Заказчик':
            edge_from = node_id
            edge_to = company.inn
        else:
            edge_from = company.inn
            edge_to = node_id

        edges.append({
            'from': edge_from,
            'to': edge_to,
            'arrows': 'to',
            'title': build_plain_title(edge_details),
            'details': edge_details,
            'role': 'aggregated',
            'status': build_status_summary(contracts_for_item),
            'value': max(1, min(item['count'], 8)),
        })


def position_counterparty_bucket(items, x, y_offset=0):
    count = len(items)
    if not count:
        return []

    spacing = 145
    start_y = y_offset - ((count - 1) * spacing / 2)

    return [
        (item, x, int(start_y + index * spacing))
        for index, item in enumerate(items)
    ]


def build_counterparty_label(info):
    if info['is_closed']:
        return 'Победитель\nне раскрыт'
    return f'{shorten_name(info["display_name"], 28)}\nИНН {info["inn"]}'


def build_details(heading, items, kind='default'):
    return {
        'heading': heading,
        'kind': kind,
        'items': [
            {
                'label': label,
                'value': str(value),
            }
            for label, value in items
        ],
    }


def build_plain_title(details):
    lines = [details['heading']]
    lines.extend(
        f'{item["label"]}: {item["value"]}'
        for item in details['items'][:8]
    )
    return '\n'.join(lines)


def build_company_details(company, contracts):
    total_price = sum((contract.price or Decimal('0')) for contract in contracts)

    return build_details(company.name, [
        ('ИНН', company.inn),
        ('Роль', 'центральная компания'),
        ('Связанных закупок/контрактов', len(contracts)),
        ('Общая сумма', format_price(total_price)),
    ], kind='company')


def build_counterparty_details(info, stat=None):
    count = stat['count'] if stat else 0
    total_price = stat['total_price'] if stat else Decimal('0')

    if info['is_closed']:
        return build_details('Победитель не раскрыт', [
            ('ИНН', 'ИНН поставщика отсутствует'),
            ('Роль', 'закрытая закупка'),
            ('Связанных закупок/контрактов', count),
            ('Общая сумма', format_price(total_price)),
        ], kind='closed')

    return build_details(info['display_name'], [
        ('ИНН', info['inn']),
        ('Роль', info['role']),
        ('Связанных закупок/контрактов', count),
        ('Общая сумма', format_price(total_price)),
    ], kind='counterparty')


def build_contract_details(contract):
    return build_details(contract.number, [
        ('Дата', format_date_display(contract.date)),
        ('Дата исполнения', format_date_display(contract.execution_date)),
        ('Предмет', contract.title or 'не указан'),
        ('Сумма', format_price(contract.price)),
        ('Направление', build_contract_direction(contract)),
        ('Статус', contract.procurement_status_display.lower()),
        ('Источник', contract.source_display_name or 'не указан'),
    ], kind='contract')


def build_contract_edge_details(contract):
    return build_details(f'Связь по закупке {contract.number}', [
        ('Номер', contract.number),
        ('Сумма', format_price(contract.price)),
        ('Дата', format_date_display(contract.date)),
        ('Предмет', contract.title or 'не указан'),
        ('Направление', build_contract_direction(contract)),
        ('Статус', contract.procurement_status_display.lower()),
        ('Источник', contract.source_display_name or 'не указан'),
    ], kind='edge')


def build_aggregated_edge_details(company, counterparty, contracts):
    total_price = sum((contract.price or Decimal('0')) for contract in contracts)
    direction = build_aggregated_direction(company, counterparty)

    return build_details(f'Агрегированная связь: {counterparty["display_name"]}', [
        ('Количество контрактов', len(contracts)),
        ('Общая сумма', format_price(total_price)),
        ('Диапазон дат', format_date_range(contracts)),
        ('Направление', direction),
        ('Статус', build_status_summary(contracts)),
        ('Источник', format_sources(contracts)),
        ('Примеры номеров', format_contract_numbers(contracts)),
    ], kind='aggregate')


def build_aggregated_direction(company, counterparty):
    if counterparty['role'] == 'Заказчик':
        return f'{counterparty["display_name"]} → {company.name}'
    return f'{company.name} → {counterparty["display_name"]}'


def build_contract_direction(contract):
    customer_name = contract.customer.name
    supplier_name = contract.supplier_display_name
    return f'{customer_name} → {supplier_name}'


def build_status_summary(contracts):
    if not contracts:
        return 'не указан'

    closed_count = sum(1 for contract in contracts if contract.is_closed)
    open_count = len(contracts) - closed_count

    if closed_count and open_count:
        return f'открытых: {open_count}, закрытых: {closed_count}'
    if closed_count:
        return 'закрытая закупка'
    return 'открытая закупка'


def format_date_range(contracts):
    dates = sorted(contract.date for contract in contracts if contract.date)

    if not dates:
        return 'не указана'
    if dates[0] == dates[-1]:
        return format_date_display(dates[0])
    return f'{format_date_display(dates[0])} — {format_date_display(dates[-1])}'


def format_sources(contracts):
    sources = sorted({
        contract.source_display_name
        for contract in contracts
        if contract.source_display_name
    })

    return ', '.join(sources) if sources else 'не указан'


def format_contract_numbers(contracts, limit=5):
    numbers = [contract.number for contract in contracts[:limit]]

    if not numbers:
        return 'не указаны'
    if len(contracts) > limit:
        numbers.append(f'и ещё {len(contracts) - limit}')
    return ', '.join(numbers)


def format_date_display(value):
    if not value:
        return 'не указана'
    return value.strftime('%d.%m.%Y')


def format_price(value):
    if value in (None, ''):
        return 'сумма не указана'

    value = Decimal(value)
    if value == 0:
        return 'сумма не указана'

    return f'{value:,.2f} ₽'.replace(',', ' ')
