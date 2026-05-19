from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import requests
from django.conf import settings

from chain.services.zakupki import (
    ContractData,
    ZakupkiSyncResult,
    clean,
    decode_response,
    digits_only,
    get_contract_date_from,
    looks_like_html,
    parse_price,
    save_contract,
)


TEKTORG_SOAP_URL = 'https://api.tektorg.ru/procedures/soap'
TEKTORG_PUBLIC_URL = 'https://www.tektorg.ru/'
MAX_TEKTORG_ROWS = 100
DEFAULT_SECTION_CODES = (
    'mirea_44',
    'mirea_223',
    '44fz',
    'zakupki',
)
EMPTY_FAULT_MESSAGES = (
    'Customers not found by INN.',
    'Organizers type not found.',
)


def sync_tektorg_contracts_by_inn(inn, limit=None):
    """Loads public procurement procedures from the official TEK-Torg SOAP API."""
    if not getattr(settings, 'TEKTORG_SYNC_ENABLED', True):
        return ZakupkiSyncResult(enabled=False)

    clean_inn = digits_only(inn)
    export_limit = limit or getattr(settings, 'ZAKUPKI_CONTRACTS_LIMIT', 100)
    export_limit = max(1, min(int(export_limit), MAX_TEKTORG_ROWS))
    section_codes = get_section_codes()
    date_from = get_contract_date_from()

    result = ZakupkiSyncResult()

    if len(clean_inn) not in (10, 12):
        result.errors.append('Некорректный ИНН: нужно 10 или 12 цифр.')
        return result

    if not section_codes:
        result.errors.append('ТЭК-Торг не настроен: список секций пуст.')
        return result

    session = requests.Session()
    seen = set()
    saved_count = 0

    for section_code in section_codes:
        if saved_count >= export_limit:
            break

        result.source_urls.append(build_source_url(clean_inn, section_code, date_from))
        per_section_limit = max(1, export_limit - saved_count)

        try:
            procedures = fetch_procedures(
                session,
                inn=clean_inn,
                section_code=section_code,
                limit=per_section_limit,
                date_from=date_from,
            )
        except requests.RequestException as exc:
            result.errors.append(f'ТЭК-Торг временно недоступен для секции "{section_code}": {exc}')
            continue
        except ValueError as exc:
            result.errors.append(f'Ответ ТЭК-Торга для секции "{section_code}" не удалось разобрать: {exc}')
            continue

        result.fetched += len(procedures)

        for procedure in procedures:
            try:
                contracts = parse_tektorg_procedure(procedure, clean_inn)
            except ValueError:
                result.skipped += 1
                continue

            for contract_data in contracts:
                if contract_data.date and contract_data.date < date_from:
                    continue
                if contract_data.key in seen:
                    continue

                seen.add(contract_data.key)
                saved_status = save_contract(
                    contract_data,
                    source_file=f'tektorg.ru:customer:{section_code}',
                )

                if saved_status == 'created':
                    result.imported += 1
                elif saved_status == 'updated':
                    result.updated += 1
                else:
                    result.unchanged += 1

                saved_count += 1
                if saved_count >= export_limit:
                    break

            if saved_count >= export_limit:
                break

    return result


def get_section_codes():
    value = getattr(settings, 'TEKTORG_SECTION_CODES', '')
    if isinstance(value, str):
        return tuple(code.strip() for code in value.split(',') if code.strip()) or DEFAULT_SECTION_CODES
    return tuple(value) or DEFAULT_SECTION_CODES


def build_source_url(inn, section_code, date_from):
    params = {
        'customerINN': inn,
        'sectionCode': section_code,
        'startDate': format_tektorg_date(date_from),
    }
    return f'{TEKTORG_SOAP_URL}?{urlencode(params)}'


def fetch_procedures(session, inn, section_code, limit, date_from):
    response = session.post(
        TEKTORG_SOAP_URL,
        data=build_soap_request(inn, section_code, limit, date_from).encode('utf-8'),
        headers={
            'Accept': 'text/xml,application/xml,*/*',
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'urn:procedures',
            'User-Agent': getattr(settings, 'ZAKUPKI_USER_AGENT', 'SupplyTrace/1.0'),
        },
        timeout=getattr(settings, 'TEKTORG_TIMEOUT', getattr(settings, 'ZAKUPKI_TIMEOUT', 25)),
    )
    response.raise_for_status()

    text = decode_response(response)
    if looks_like_html(text):
        raise ValueError('получена HTML-страница вместо XML')

    return parse_tektorg_soap_response(text)


def build_soap_request(inn, section_code, limit, date_from):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:soap="https://api.tektorg.ru/procedures/soap">
  <soapenv:Header/>
  <soapenv:Body>
    <soap:procedures>
      <symbol>
        <sectionCode>{escape(section_code)}</sectionCode>
        <customerINN>{escape(inn)}</customerINN>
        <startDate>{format_tektorg_date(date_from)}</startDate>
        <limitPage>{int(limit)}</limitPage>
        <page>1</page>
        <sort>
          <field>datePublished</field>
          <operator>DESC</operator>
        </sort>
      </symbol>
    </soap:procedures>
  </soapenv:Body>
</soapenv:Envelope>'''


def parse_tektorg_soap_response(text):
    try:
        root = ElementTree.fromstring(text.strip())
    except ElementTree.ParseError as exc:
        raise ValueError(f'некорректный XML: {exc}') from exc

    fault = find_first(root, 'Fault')
    if fault is not None:
        fault_text = child_text(fault, 'faultstring')
        if fault_text in EMPTY_FAULT_MESSAGES:
            return []
        raise ValueError(fault_text or 'SOAP Fault')

    procedures = find_first(root, 'procedures')
    if procedures is None:
        return []

    return children(procedures, 'procedure')


def parse_tektorg_procedure(procedure, inn):
    base_number = (
        child_text(procedure, 'registryNumber')
        or child_text(procedure, 'eisRegistryNumber')
        or child_text(procedure, 'remoteId')
        or procedure.attrib.get('id')
    )
    base_number = clean(base_number)
    if not base_number:
        raise ValueError('нет номера процедуры')

    procedure_title = clean(child_text(procedure, 'title'))
    date = parse_tektorg_date(child_text(procedure, 'datePublished'))
    source_url = clean(child_text(procedure, 'url_to_showcase')) or TEKTORG_PUBLIC_URL
    organizer = first_child(procedure, 'organizer')
    lots = children(first_child(procedure, 'lots'), 'lot')

    if not lots:
        customer = extract_organization(organizer)
        if customer['inn'] != inn:
            raise ValueError('процедура не относится к запрошенному ИНН')
        return [
            build_contract_data(
                number=base_number,
                title=procedure_title,
                price=Decimal('0'),
                date=date,
                customer=customer,
                source_url=source_url,
            )
        ]

    contracts = []
    for lot_index, lot in enumerate(lots, start=1):
        lot_customers = extract_lot_customers(lot) or [extract_organization(organizer)]
        lot_number = clean(child_text(lot, 'number')) or str(lot_index)
        lot_title = clean(child_text(lot, 'subject')) or procedure_title
        lot_price = parse_tektorg_price(child_text(lot, 'startPrice'))

        for customer_index, customer in enumerate(lot_customers, start=1):
            if customer['inn'] != inn:
                continue

            number = base_number
            if len(lots) > 1 or len(lot_customers) > 1:
                number = f'{base_number}/lot-{lot_number}-{customer_index}'

            contracts.append(
                build_contract_data(
                    number=number,
                    title=lot_title,
                    price=lot_price,
                    date=date,
                    customer=customer,
                    source_url=source_url,
                )
            )

    if not contracts:
        raise ValueError('нет заказчика с запрошенным ИНН')

    return contracts


def build_contract_data(number, title, price, date, customer, source_url):
    return ContractData(
        number=number,
        title=title,
        price=price,
        date=date,
        execution_date=None,
        customer_inn=customer['inn'],
        customer_name=customer['name'] or f'Компания {customer["inn"]}',
        customer_kpp='',
        supplier_inn='',
        supplier_name='',
        supplier_kpp='',
        is_closed=False,
        supplier_disclosed=False,
        source_url=source_url,
    )


def extract_lot_customers(lot):
    customers_node = first_child(lot, 'customers')
    return [
        customer
        for customer in (extract_organization(node) for node in children(customers_node, 'customer'))
        if customer['inn']
    ]


def extract_organization(node):
    if node is None:
        return {'inn': '', 'name': ''}

    return {
        'inn': digits_only(child_text(node, 'inn')),
        'name': clean(child_text(node, 'fullName')),
    }


def parse_tektorg_price(value):
    value = clean(value)
    if not value:
        return Decimal('0')

    try:
        return parse_price(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'некорректная сумма: {value}') from exc


def parse_tektorg_date(value):
    value = clean(value)
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError as exc:
        raise ValueError(f'некорректная дата: {value}') from exc


def format_tektorg_date(value):
    return value.strftime('%Y-%m-%dT00:00:00+03:00')


def first_child(element, name):
    matches = children(element, name)
    return matches[0] if matches else None


def find_first(element, name):
    if element is None:
        return None

    for child in element.iter():
        if local_name(child.tag) == name:
            return child
    return None


def children(element, name):
    if element is None:
        return []

    return [
        child
        for child in list(element)
        if local_name(child.tag) == name
    ]


def child_text(element, name):
    child = first_child(element, name)
    if child is None or child.text is None:
        return ''
    return child.text


def local_name(tag):
    return tag.rsplit('}', 1)[-1]
