import os

import requests

from chain.models import Company


DADATA_FIND_PARTY_URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'


def fetch_company_from_dadata(inn):
    """Ищет организацию или ИП по ИНН через DaData.

    Возвращает словарь с реквизитами или None, если токена нет / компания не найдена / API недоступен.
    """
    token = os.getenv('DADATA_TOKEN', '').strip()

    if not token:
        return None

    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    payload = {
        'query': inn,
        'count': 1,
    }

    try:
        response = requests.post(
            DADATA_FIND_PARTY_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    suggestions = response.json().get('suggestions', [])

    if not suggestions:
        return None

    item = suggestions[0]
    data = item.get('data') or {}
    name_data = data.get('name') or {}

    name = (
        name_data.get('short_with_opf')
        or name_data.get('full_with_opf')
        or item.get('value')
        or f'Компания {inn}'
    )

    found_inn = data.get('inn') or inn

    return {
        'inn': found_inn,
        'name': name,
        'kpp': data.get('kpp') or '',
        'ogrn': data.get('ogrn') or '',
    }


def get_or_create_company_by_inn(inn):
    """Возвращает компанию из базы, DaData или создает минимальную карточку по ИНН."""
    if len(inn) not in (10, 12) or not inn.isdigit():
        return None

    company = Company.objects.filter(inn=inn).first()

    if company:
        return company

    company_data = fetch_company_from_dadata(inn)

    if company_data is None:
        company_data = {
            'inn': inn,
            'name': f'Компания с ИНН {inn}',
            'kpp': '',
            'ogrn': '',
        }

    company, _ = Company.objects.update_or_create(
        inn=company_data['inn'],
        defaults={
            'name': company_data['name'],
            'kpp': company_data['kpp'],
            'ogrn': company_data['ogrn'],
        },
    )
    return company
