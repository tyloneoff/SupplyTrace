import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone


def get_company_contracts(company):
    from chain.models import Contract

    one_year_ago = timezone.localdate() - timedelta(days=365)

    return (
        Contract.objects
        .select_related("customer", "supplier")
        .filter(Q(customer=company) | Q(supplier=company), date__gte=one_year_ago)
        .order_by("-date")
    )


def get_counterparty_stats(company, contracts):
    stats = {}

    for contract in contracts:
        if contract.customer_id == company.id:
            counterparty = contract.supplier
            role = "Поставщик"
        else:
            counterparty = contract.customer
            role = "Заказчик"

        item = stats.setdefault(counterparty.inn, {
            "company": counterparty,
            "role": role,
            "count": 0,
            "total_price": Decimal("0"),
        })

        item["count"] += 1
        item["total_price"] += contract.price or Decimal("0")

    return sorted(
        stats.values(),
        key=lambda item: (item["count"], item["total_price"]),
        reverse=True,
    )


def shorten_name(name, max_len=32):
    if not name:
        return "Без названия"

    name = " ".join(name.split())

    replacements = {
        "ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ": "ФГБОУ ВО",
        "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ": "ООО",
        "АКЦИОНЕРНОЕ ОБЩЕСТВО": "АО",
        "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО": "ПАО",
        "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ": "ИП",
    }

    upper_name = name.upper()

    for long_text, short_text in replacements.items():
        upper_name = upper_name.replace(long_text, short_text)

    if len(upper_name) <= max_len:
        return upper_name

    return upper_name[:max_len - 3] + "..."


def build_graph_data(company, contracts, limit=10):
    counterparty_map = {}

    for contract in contracts:
        if contract.customer_id == company.id:
            counterparty = contract.supplier
            role = "Поставщик"
            edge_from = counterparty.inn
            edge_to = company.inn
        elif contract.supplier_id == company.id:
            counterparty = contract.customer
            role = "Заказчик"
            edge_from = company.inn
            edge_to = counterparty.inn
        else:
            continue

        item = counterparty_map.setdefault(counterparty.inn, {
            "company": counterparty,
            "role": role,
            "count": 0,
            "total_price": Decimal("0"),
            "edge_from": edge_from,
            "edge_to": edge_to,
        })

        item["count"] += 1
        item["total_price"] += contract.price or Decimal("0")

    counterparties = sorted(
        counterparty_map.values(),
        key=lambda item: (item["count"], item["total_price"]),
        reverse=True,
    )

    total_count = len(counterparties)
    counterparties = counterparties[:limit]
    shown_count = len(counterparties)

    nodes = [
        {
            "id": company.inn,
            "label": f"{shorten_name(company.name, 36)}\nИНН {company.inn}",
            "group": "main",
            "x": 0,
            "y": 0,
            "fixed": True,
            "title": f"{company.name}<br>ИНН: {company.inn}",
        }
    ]

    edges = []

    radius = 230

    for index, item in enumerate(counterparties):
        counterparty = item["company"]
        angle = 2 * math.pi * index / max(shown_count, 1)

        x = int(radius * math.cos(angle))
        y = int(radius * math.sin(angle))

        group = "supplier" if item["role"] == "Поставщик" else "customer"

        nodes.append({
            "id": counterparty.inn,
            "label": f"{shorten_name(counterparty.name, 28)}\nИНН {counterparty.inn}",
            "group": group,
            "x": x,
            "y": y,
            "fixed": True,
            "title": (
                f"{counterparty.name}<br>"
                f"ИНН: {counterparty.inn}<br>"
                f"Роль: {item['role']}<br>"
                f"Контрактов: {item['count']}<br>"
                f"Сумма: {item['total_price']} ₽"
            ),
        })

        edges.append({
            "from": item["edge_from"],
            "to": item["edge_to"],
            "arrows": "to",
            "width": min(6, 1 + item["count"]),
            "title": (
                f"Контрактов: {item['count']}<br>"
                f"Сумма: {item['total_price']} ₽"
            ),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "shown_count": shown_count,
        "total_count": total_count,
    }