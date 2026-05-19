import hashlib
import re
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests
from django.conf import settings

from chain.services.zakupki import (
    ContractData,
    ZakupkiSyncResult,
    clean,
    decode_response,
    digits_only,
    get_contract_date_from,
    parse_price,
    save_contract,
)


SBERBANK_AST_PUBLIC_URL = 'https://www.sberbank-ast.ru/'
DEFAULT_REGISTRY_URLS = (
    'https://utp.sberbank-ast.ru/SB/List/PurchaseList',
    'https://utp.sberbank-ast.ru/SB/List/PurchaseListSMiSP',
    'https://utp.sberbank-ast.ru/Trade/List/PurchaseList',
    'https://utp.sberbank-ast.ru/Trade/List/PurchaseListSMiSP',
    'https://utp.sberbank-ast.ru/Trade/List/PurchaseListOOS',
)
MAX_SBERBANK_AST_ROWS = 100
ANTI_BOT_MARKERS = (
    'Действия блокированы защитой ЭТП',
    'Посторонее ПО',
    'The Session ID is: N/A',
)
LOGIN_MARKERS = (
    'Login.aspx',
    'txtPassword',
    'btnSubmitByLoginPassword',
)
DISABLED_MESSAGE = (
    'Источник подключён как best-effort HTML parser, но по умолчанию отключён: '
    'Sberbank AST часто блокирует автоматический доступ защитой ЭТП и не предоставляет '
    'стабильный публичный CSV/JSON API без авторизации.'
)
BLOCKED_MESSAGE = (
    'Sberbank AST вернул страницу защиты ЭТП или форму входа вместо публичного реестра. '
    'Источник оставлен как best-effort parser для публичного HTML, но обход защиты, '
    'капчи или авторизации не выполняется.'
)


class SberbankAstAccessBlocked(ValueError):
    pass


class TableRowParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current_row = None
        self.current_cell = None
        self.current_href = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)

        if tag == 'tr':
            self.current_row = []
            return

        if tag in ('td', 'th') and self.current_row is not None:
            self.current_cell = {
                'text': [],
                'hrefs': [],
            }
            return

        if tag == 'a' and self.current_cell is not None:
            href = clean(attrs.get('href'))
            if href:
                self.current_cell['hrefs'].append(href)
                self.current_href = href

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell['text'].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == 'a':
            self.current_href = None
            return

        if tag in ('td', 'th') and self.current_cell is not None:
            text = clean(' '.join(self.current_cell['text']))
            hrefs = list(dict.fromkeys(self.current_cell['hrefs']))
            self.current_row.append({'text': text, 'hrefs': hrefs})
            self.current_cell = None
            return

        if tag == 'tr' and self.current_row is not None:
            if any(cell['text'] for cell in self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None


def sync_sberbank_ast_contracts_by_inn(inn, limit=None):
    if not getattr(settings, 'SBERBANK_AST_SYNC_ENABLED', False):
        result = ZakupkiSyncResult(enabled=False)
        result.errors.append(DISABLED_MESSAGE)
        return result

    clean_inn = digits_only(inn)
    export_limit = limit or getattr(settings, 'ZAKUPKI_CONTRACTS_LIMIT', 100)
    export_limit = max(1, min(int(export_limit), MAX_SBERBANK_AST_ROWS))
    date_from = get_contract_date_from()

    result = ZakupkiSyncResult()

    if len(clean_inn) not in (10, 12):
        result.errors.append('Некорректный ИНН: нужно 10 или 12 цифр.')
        return result

    session = requests.Session()
    seen = set()

    for registry_url in get_registry_urls():
        if result.saved >= export_limit:
            break

        result.source_urls.append(registry_url)

        try:
            html = fetch_registry_html(session, registry_url)
            entries = parse_sberbank_ast_entries(html, clean_inn, registry_url)
        except SberbankAstAccessBlocked:
            result.errors.append(BLOCKED_MESSAGE)
            break
        except requests.RequestException as exc:
            result.errors.append(f'Sberbank AST временно недоступен: {exc}')
            continue
        except ValueError as exc:
            result.errors.append(f'Ответ Sberbank AST не удалось разобрать: {exc}')
            continue

        result.fetched += len(entries)

        for contract_data in entries:
            if contract_data.date and contract_data.date < date_from:
                continue
            if contract_data.key in seen:
                continue

            seen.add(contract_data.key)
            saved_status = save_contract(contract_data, source_file='sberbank-ast.ru:customer')

            if saved_status == 'created':
                result.imported += 1
            elif saved_status == 'updated':
                result.updated += 1
            else:
                result.unchanged += 1

            if result.saved >= export_limit:
                break

    return result


def get_registry_urls():
    configured = getattr(settings, 'SBERBANK_AST_REGISTRY_URLS', '')
    if isinstance(configured, str):
        urls = [url.strip() for url in configured.split(',') if url.strip()]
        return tuple(urls) or DEFAULT_REGISTRY_URLS
    return tuple(configured) or DEFAULT_REGISTRY_URLS


def fetch_registry_html(session, registry_url):
    response = session.get(
        registry_url,
        headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'User-Agent': getattr(settings, 'ZAKUPKI_USER_AGENT', 'SupplyTrace/1.0'),
        },
        timeout=getattr(settings, 'SBERBANK_AST_TIMEOUT', getattr(settings, 'ZAKUPKI_TIMEOUT', 25)),
    )
    response.raise_for_status()

    html = decode_response(response)
    if is_access_blocked(html) or is_login_required(html):
        raise SberbankAstAccessBlocked(BLOCKED_MESSAGE)
    if '<html' not in html[:1000].lower() and '<table' not in html.lower():
        raise ValueError('ожидался HTML с реестром закупок')

    return html


def parse_sberbank_ast_entries(html, inn, base_url=SBERBANK_AST_PUBLIC_URL):
    if is_access_blocked(html) or is_login_required(html):
        raise SberbankAstAccessBlocked(BLOCKED_MESSAGE)

    parser = TableRowParser()
    parser.feed(html)

    entries = []
    for row in parser.rows:
        row_text = ' '.join(cell['text'] for cell in row)
        if inn not in digits_only(row_text):
            continue

        entries.append(build_contract_data_from_row(row, inn, base_url))

    return entries


def build_contract_data_from_row(row, inn, base_url):
    row_text = ' '.join(cell['text'] for cell in row)
    number = extract_number(row_text, inn) or build_stable_number(row_text, inn)
    title = extract_title(row, inn, number)
    price = extract_price(row_text)
    date = extract_date(row_text)
    source_url = extract_source_url(row, base_url)
    customer_name = extract_customer_name(row, inn)

    return ContractData(
        number=number,
        title=title,
        price=price,
        date=date,
        execution_date=None,
        customer_inn=inn,
        customer_name=customer_name,
        customer_kpp='',
        supplier_inn='',
        supplier_name='',
        supplier_kpp='',
        is_closed=False,
        supplier_disclosed=False,
        source_url=source_url,
    )


def extract_number(text, inn):
    patterns = (
        r'\b(?:SBR|AST|UTP|COM)[A-Za-z0-9/-]{4,}\b',
        r'№\s*([A-Za-zА-Яа-я0-9/-]{4,})',
        r'\b\d{8,24}\b',
    )

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = clean(match.group(1) if match.groups() else match.group(0))
            if digits_only(value) != inn:
                return value

    return ''


def extract_title(row, inn, number):
    ignored_values = {digits_only(inn), digits_only(number)}
    candidates = []

    for cell in row:
        text = clean(cell['text'])
        if not text:
            continue
        if digits_only(text) in ignored_values:
            continue
        if extract_date(text) or extract_price(text) != Decimal('0'):
            continue
        if not re.search(r'[A-Za-zА-Яа-я]', text):
            continue
        candidates.append(text)

    if candidates:
        return max(candidates, key=len)[:1000]
    return f'Закупка Sberbank AST {number}'


def extract_customer_name(row, inn):
    for index, cell in enumerate(row):
        text = clean(cell['text'])
        if inn not in digits_only(text):
            continue

        text_without_inn = re.sub(rf'\bИНН\b[:\s]*{re.escape(inn)}', '', text, flags=re.IGNORECASE)
        text_without_inn = re.sub(r'\bИНН\b[:\s]*', '', text_without_inn, flags=re.IGNORECASE)
        text_without_inn = clean(text_without_inn.replace(inn, '').strip(' ,;:-'))
        if re.search(r'[A-Za-zА-Яа-я]', text_without_inn):
            return text_without_inn[:500]

        for nearby in (index - 1, index + 1):
            if 0 <= nearby < len(row):
                nearby_text = clean(row[nearby]['text'])
                if re.search(r'[A-Za-zА-Яа-я]', nearby_text):
                    return nearby_text[:500]

    return f'Компания {inn}'


def extract_price(text):
    price_pattern = re.compile(
        r'(\d{1,3}(?:[\s\xa0]\d{3})+(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?)\s*(?:₽|руб\.?|RUB)',
        flags=re.IGNORECASE,
    )
    matches = list(price_pattern.finditer(text))
    if not matches:
        return Decimal('0')

    return parse_price(matches[-1].group(1))


def extract_date(text):
    match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', text)
    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), '%d.%m.%Y').date()
    except ValueError:
        return None


def extract_source_url(row, base_url):
    for cell in row:
        for href in cell['hrefs']:
            return urljoin(base_url, href)
    return base_url


def build_stable_number(text, inn):
    digest = hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()[:12]
    return f'sberbank-ast:{inn}:{digest}'


def is_access_blocked(html):
    return any(marker in html for marker in ANTI_BOT_MARKERS)


def is_login_required(html):
    return any(marker in html for marker in LOGIN_MARKERS)
