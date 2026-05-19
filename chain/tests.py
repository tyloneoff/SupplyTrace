from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from chain.models import Company, Contract, SearchHistory, SyncLog
from chain.services import zakupki
from chain.services.analytics import build_graph_data, get_tender_summary
from chain.services.local_retention import purge_expired_local_data
from chain.services.public_sources import PUBLIC_SOURCE_PROVIDERS, PUBLIC_SOURCES
from chain.services.mos_zakupki import parse_mos_contract_item
from chain.services.sberbank_ast import (
    SberbankAstAccessBlocked,
    parse_sberbank_ast_entries,
    sync_sberbank_ast_contracts_by_inn,
)
from chain.services.tektorg import (
    parse_tektorg_procedure,
    parse_tektorg_soap_response,
    sync_tektorg_contracts_by_inn,
)


TARGET_INN = '7729040491'


def zakupki_row(
    number,
    *,
    customer_inn=TARGET_INN,
    customer_name='ФГБОУ ВО "МИРЭА - РОССИЙСКИЙ ТЕХНОЛОГИЧЕСКИЙ УНИВЕРСИТЕТ"',
    supplier_inn='4821012620',
    supplier_name='ООО "ЦЕНТР"',
    price='738 384,95',
):
    return {
        'Номер реестровой записи контракта': f"'{number}'",
        'Заказчик: наименование': customer_name,
        'Заказчик: ИНН': f"'{customer_inn}'",
        'Заказчик: КПП': "'772901001'",
        'Контракт: дата': '13.04.2026',
        'Контракт: номер': "'0373100029526000053'",
        'Предмет контракта': "'Поставка сантехнических товаров'",
        'Цена контракта': f"'{price}'",
        'Информация о поставщиках (исполнителях, подрядчиках) по контракту: наименование юридического лица (ф.и.о. физического лица)': supplier_name,
        'Информация о поставщиках (исполнителях, подрядчиках) по контракту: ИНН': f"'{supplier_inn}'",
        'Информация о поставщиках (исполнителях, подрядчиках) по контракту: КПП': "'482101001'",
        'Дата исполнения контракта: по контракту': '17.07.2026',
    }


def tektorg_soap_response():
    return '''
        <?xml version="1.0" encoding="UTF-8"?>
        <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
          <SOAP-ENV:Body>
            <SOAP-ENV:proceduresResponse>
              <totalProcedures>1</totalProcedures>
              <currentPage>1</currentPage>
              <totalPage>1</totalPage>
              <limitProceduresInPage>1</limitProceduresInPage>
              <sectionName>МИРЭА</sectionName>
              <sectionCode>mirea_44</sectionCode>
              <procedures>
                <procedure id="848551">
                  <remoteId>848551</remoteId>
                  <url_to_showcase>https://www.tektorg.ru/44-fz/procedures/19097811</url_to_showcase>
                  <registryNumber>0373100029526000128</registryNumber>
                  <title>Поставка мебели</title>
                  <datePublished>2026-05-19T15:18:49+03:00</datePublished>
                  <organizer>
                    <id>33663</id>
                    <fullName>ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ "МИРЭА"</fullName>
                    <inn>7729040491</inn>
                  </organizer>
                  <lots>
                    <lot id="22204972">
                      <remoteId>848551</remoteId>
                      <number>1</number>
                      <subject>Поставка мебели</subject>
                      <startPrice>8629844.5</startPrice>
                      <status>Приём заявок</status>
                      <customers>
                        <customer>
                          <id>-33663</id>
                          <fullName>ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ "МИРЭА"</fullName>
                          <inn>7729040491</inn>
                        </customer>
                      </customers>
                    </lot>
                  </lots>
                </procedure>
              </procedures>
            </SOAP-ENV:proceduresResponse>
          </SOAP-ENV:Body>
        </SOAP-ENV:Envelope>
    '''


def sberbank_ast_html_response():
    return '''
        <html>
          <body>
            <table>
              <tr>
                <th>Номер</th>
                <th>Заказчик</th>
                <th>Предмет</th>
                <th>Дата</th>
                <th>НМЦ</th>
              </tr>
              <tr>
                <td><a href="/SB/Purchase/Details/42">SBR035-260000042</a></td>
                <td>ФГБОУ ВО "МИРЭА", ИНН 7729040491</td>
                <td>Поставка серверного оборудования</td>
                <td>19.05.2026</td>
                <td>1 250 000,50 руб.</td>
              </tr>
            </table>
          </body>
        </html>
    '''


class ZakupkiParserTests(SimpleTestCase):
    def test_parse_contract_row_with_real_zakupki_headers(self):
        contract = zakupki.parse_contract_row(zakupki_row('1772904049126000102'))

        self.assertEqual(contract.number, '1772904049126000102')
        self.assertEqual(contract.customer_inn, TARGET_INN)
        self.assertEqual(contract.supplier_inn, '4821012620')
        self.assertEqual(contract.title, 'Поставка сантехнических товаров')
        self.assertEqual(contract.price, Decimal('738384.95'))
        self.assertEqual(contract.date, date(2026, 4, 13))
        self.assertEqual(contract.execution_date, date(2026, 7, 17))
        self.assertFalse(contract.is_closed)
        self.assertTrue(contract.supplier_disclosed)

    def test_parse_contract_row_allows_closed_tender_without_supplier(self):
        contract = zakupki.parse_contract_row(
            zakupki_row('1772904049126000999', supplier_inn='', supplier_name='')
        )

        self.assertEqual(contract.number, '1772904049126000999')
        self.assertEqual(contract.customer_inn, TARGET_INN)
        self.assertEqual(contract.supplier_inn, '')
        self.assertTrue(contract.is_closed)
        self.assertFalse(contract.supplier_disclosed)

    def test_parse_contract_row_uses_first_supplier_inn_when_csv_has_multiple_values(self):
        contract = zakupki.parse_contract_row(
            zakupki_row('1772904049126000888', supplier_inn='77205184947720518494')
        )

        self.assertEqual(contract.supplier_inn, '7720518494')

    @override_settings(
        ZAKUPKI_SYNC_ENABLED=True,
        ZAKUPKI_CONTRACTS_LIMIT=100,
        ZAKUPKI_CONTRACT_LOOKBACK_DAYS=365,
    )
    @patch('chain.services.zakupki.save_contract')
    @patch('chain.services.zakupki.fetch_csv_rows')
    def test_sync_contracts_by_inn_limits_each_role(self, fetch_csv_rows, save_contract):
        fetch_csv_rows.side_effect = [
            [
                zakupki_row('1772904049126000001'),
                zakupki_row('1999999999926000001', customer_inn='9999999999'),
                zakupki_row('1772904049126000002'),
                zakupki_row('1772904049126000003'),
            ],
            [
                zakupki_row('2772904049126000001', customer_inn='7414002238', supplier_inn=TARGET_INN),
                zakupki_row('2772904049126000002', customer_inn='7414002238', supplier_inn=TARGET_INN),
                zakupki_row('2772904049126000003', customer_inn='7414002238', supplier_inn=TARGET_INN),
            ],
        ]
        save_contract.side_effect = ['created', 'updated', 'unchanged', 'created']

        result = zakupki.sync_contracts_by_inn(TARGET_INN, limit=2)

        self.assertEqual(result.fetched, 7)
        self.assertEqual(result.imported, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.unchanged, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(save_contract.call_count, 4)

        saved_numbers = [call.args[0].number for call in save_contract.call_args_list]
        self.assertEqual(saved_numbers, [
            '1772904049126000001',
            '1772904049126000002',
            '2772904049126000001',
            '2772904049126000002',
        ])
        self.assertEqual(save_contract.call_args_list[0].kwargs['source_file'], 'zakupki.gov.ru:customer')
        self.assertEqual(save_contract.call_args_list[2].kwargs['source_file'], 'zakupki.gov.ru:supplier')


class MosZakupkiParserTests(SimpleTestCase):
    def test_parse_mos_contract_item(self):
        contract = parse_mos_contract_item({
            'registerNumber': '26-91087301',
            'subject': 'Поставка строительных тачек',
            'rubSum': 15456.25,
            'conclusionDate': '11.05.2026 17:33:32',
            'executionDate': '21.05.2026 17:33:32',
            'entityId': 216611478,
            'customer': {
                'inn': '7751335162',
                'kpp': '',
                'name': 'ГБУ Жилищник района Троицк',
            },
            'supplier': {
                'inn': '7724489149',
                'kpp': '',
                'name': 'ООО ТК СНАБТОРГ',
            },
        })

        self.assertEqual(contract.number, '26-91087301')
        self.assertEqual(contract.customer_inn, '7751335162')
        self.assertEqual(contract.supplier_inn, '7724489149')
        self.assertEqual(contract.price, Decimal('15456.25'))
        self.assertEqual(contract.date, date(2026, 5, 11))
        self.assertEqual(contract.execution_date, date(2026, 5, 21))
        self.assertEqual(contract.source_url, 'https://zakupki.mos.ru/contract/216611478')


class TekTorgParserTests(SimpleTestCase):
    def test_parse_tektorg_soap_response_and_procedure(self):
        procedures = parse_tektorg_soap_response(tektorg_soap_response())

        self.assertEqual(len(procedures), 1)

        contracts = parse_tektorg_procedure(procedures[0], TARGET_INN)

        self.assertEqual(len(contracts), 1)
        contract = contracts[0]
        self.assertEqual(contract.number, '0373100029526000128')
        self.assertEqual(contract.customer_inn, TARGET_INN)
        self.assertEqual(
            contract.customer_name,
            'ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ "МИРЭА"',
        )
        self.assertEqual(contract.title, 'Поставка мебели')
        self.assertEqual(contract.price, Decimal('8629844.5'))
        self.assertEqual(contract.date, date(2026, 5, 19))
        self.assertEqual(contract.source_url, 'https://www.tektorg.ru/44-fz/procedures/19097811')
        self.assertFalse(contract.is_closed)
        self.assertFalse(contract.supplier_disclosed)

    def test_parse_tektorg_empty_customer_fault_as_empty_result(self):
        procedures = parse_tektorg_soap_response('''
            <Envelope>
              <Body>
                <Fault>
                  <faultcode>SOAP-ENV:Client</faultcode>
                  <faultstring>Customers not found by INN.</faultstring>
                </Fault>
              </Body>
            </Envelope>
        ''')

        self.assertEqual(procedures, [])

    @override_settings(
        TEKTORG_SYNC_ENABLED=True,
        TEKTORG_SECTION_CODES='mirea_44',
        ZAKUPKI_CONTRACTS_LIMIT=100,
        ZAKUPKI_CONTRACT_LOOKBACK_DAYS=365,
    )
    @patch('chain.services.tektorg.save_contract')
    @patch('chain.services.tektorg.fetch_procedures')
    def test_sync_tektorg_contracts_by_inn_saves_customer_procedures(self, fetch_procedures, save_contract):
        fetch_procedures.return_value = parse_tektorg_soap_response(tektorg_soap_response())
        save_contract.return_value = 'created'

        result = sync_tektorg_contracts_by_inn(TARGET_INN, limit=5)

        self.assertEqual(result.fetched, 1)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.unchanged, 0)
        self.assertFalse(result.has_errors)

        saved_contract = save_contract.call_args.args[0]
        self.assertEqual(saved_contract.number, '0373100029526000128')
        self.assertEqual(save_contract.call_args.kwargs['source_file'], 'tektorg.ru:customer:mirea_44')


class SberbankAstParserTests(SimpleTestCase):
    def test_parse_sberbank_ast_public_html_row(self):
        entries = parse_sberbank_ast_entries(
            sberbank_ast_html_response(),
            TARGET_INN,
            'https://utp.sberbank-ast.ru/SB/List/PurchaseList',
        )

        self.assertEqual(len(entries), 1)
        contract = entries[0]
        self.assertEqual(contract.number, 'SBR035-260000042')
        self.assertEqual(contract.customer_inn, TARGET_INN)
        self.assertEqual(contract.customer_name, 'ФГБОУ ВО "МИРЭА"')
        self.assertEqual(contract.title, 'Поставка серверного оборудования')
        self.assertEqual(contract.price, Decimal('1250000.50'))
        self.assertEqual(contract.date, date(2026, 5, 19))
        self.assertEqual(contract.source_url, 'https://utp.sberbank-ast.ru/SB/Purchase/Details/42')
        self.assertFalse(contract.supplier_disclosed)

    def test_parse_sberbank_ast_access_block_as_warning(self):
        with self.assertRaises(SberbankAstAccessBlocked):
            parse_sberbank_ast_entries(
                'Действия блокированы защитой ЭТП. Посторонее ПО.',
                TARGET_INN,
            )

    def test_parse_sberbank_ast_login_page_as_warning(self):
        with self.assertRaises(SberbankAstAccessBlocked):
            parse_sberbank_ast_entries(
                '<html><form action="./Login.aspx"><input id="mainContent_txtPassword"></form></html>',
                TARGET_INN,
            )

    @override_settings(
        SBERBANK_AST_SYNC_ENABLED=True,
        SBERBANK_AST_REGISTRY_URLS='https://utp.sberbank-ast.ru/SB/List/PurchaseList',
        ZAKUPKI_CONTRACTS_LIMIT=100,
        ZAKUPKI_CONTRACT_LOOKBACK_DAYS=365,
    )
    @patch('chain.services.sberbank_ast.save_contract')
    @patch('chain.services.sberbank_ast.fetch_registry_html')
    def test_sync_sberbank_ast_contracts_by_inn_saves_public_html_entries(
        self,
        fetch_registry_html,
        save_contract,
    ):
        fetch_registry_html.return_value = sberbank_ast_html_response()
        save_contract.return_value = 'created'

        result = sync_sberbank_ast_contracts_by_inn(TARGET_INN, limit=5)

        self.assertEqual(result.fetched, 1)
        self.assertEqual(result.imported, 1)
        self.assertFalse(result.has_errors)
        self.assertEqual(save_contract.call_args.args[0].number, 'SBR035-260000042')
        self.assertEqual(save_contract.call_args.kwargs['source_file'], 'sberbank-ast.ru:customer')


class TenderSummaryTests(TestCase):
    def test_counts_open_closed_and_disclosed_winners(self):
        company = Company.objects.create(inn=TARGET_INN, name='Компания')
        customer = Company.objects.create(inn='7707083893', name='Заказчик')
        supplier = Company.objects.create(inn='7705966893', name='Поставщик')

        contracts = [
            Contract.objects.create(
                number='OPEN-1',
                customer=customer,
                supplier=company,
                supplier_disclosed=True,
            ),
            Contract.objects.create(
                number='OPEN-2',
                customer=company,
                supplier=supplier,
                supplier_disclosed=True,
            ),
            Contract.objects.create(
                number='CLOSED-1',
                customer=company,
                supplier=None,
                is_closed=True,
                supplier_disclosed=False,
            ),
        ]

        summary = get_tender_summary(contracts)

        self.assertEqual(summary, {
            'total': 3,
            'open_count': 2,
            'closed_count': 1,
            'known_winner_count': 2,
            'undisclosed_winner_count': 1,
        })


class LocalRetentionTests(TestCase):
    @override_settings(SUPPLYTRACE_LOCAL_DATA_TTL_HOURS=1)
    def test_purge_expired_local_data_removes_old_business_records(self):
        old_time = timezone.now() - timedelta(hours=2)
        company = Company.objects.create(inn=TARGET_INN, name='Компания')
        supplier = Company.objects.create(inn='7705966893', name='Поставщик')
        contract = Contract.objects.create(
            number='OLD-1',
            customer=company,
            supplier=supplier,
            date=timezone.localdate(),
        )
        search = SearchHistory.objects.create(inn=TARGET_INN)
        sync_log = SyncLog.objects.create(
            inn=TARGET_INN,
            company=company,
            status=Company.SYNC_STATUS_OK,
        )

        Company.objects.filter(id__in=[company.id, supplier.id]).update(created_at=old_time)
        Contract.objects.filter(id=contract.id).update(imported_at=old_time)
        SearchHistory.objects.filter(id=search.id).update(created_at=old_time)
        SyncLog.objects.filter(id=sync_log.id).update(created_at=old_time)

        result = purge_expired_local_data(now=timezone.now())

        self.assertEqual(result['contracts'], 1)
        self.assertEqual(result['searches'], 1)
        self.assertEqual(result['sync_logs'], 1)
        self.assertEqual(Contract.objects.count(), 0)
        self.assertEqual(SearchHistory.objects.count(), 0)
        self.assertEqual(SyncLog.objects.count(), 0)


class GraphDataTests(TestCase):
    def test_graph_nodes_are_draggable_and_tooltips_include_contract_details(self):
        company = Company.objects.create(inn=TARGET_INN, name='Центральная компания')
        supplier = Company.objects.create(inn='7705966893', name='ООО Поставщик')

        contract = Contract.objects.create(
            number='OPEN-42',
            title='Поставка оборудования',
            price=Decimal('150000.50'),
            date=timezone.localdate(),
            customer=company,
            supplier=supplier,
            source_file='zakupki.gov.ru:customer',
            purchase_url='https://zakupki.gov.ru/example',
        )

        graph_data = build_graph_data(company, [contract])

        self.assertTrue(graph_data['nodes'])
        self.assertTrue(graph_data['edges'])
        self.assertEqual(graph_data['mode'], 'detailed')
        self.assertTrue(all(node.get('fixed') is False for node in graph_data['nodes']))
        self.assertIn('Роль: центральная компания', graph_data['nodes'][0]['title'])
        self.assertIn('Связанных закупок/контрактов: 1', graph_data['nodes'][0]['title'])
        self.assertIn('details', graph_data['nodes'][0])
        self.assertNotIn('<br>', graph_data['edges'][0]['title'])

        edge_titles = ' '.join(edge['title'] for edge in graph_data['edges'])
        self.assertIn('OPEN-42', edge_titles)
        self.assertIn('Поставка оборудования', edge_titles)
        self.assertIn('Направление: Центральная компания → ООО Поставщик', edge_titles)
        self.assertIn('Статус: открытая закупка', edge_titles)
        self.assertIn('zakupki.gov.ru', edge_titles)

    def test_graph_handles_closed_contract_without_supplier(self):
        company = Company.objects.create(inn=TARGET_INN, name='Компания')
        contract = Contract.objects.create(
            number='CLOSED-42',
            title='Закрытая поставка',
            price=Decimal('250000'),
            date=timezone.localdate(),
            customer=company,
            supplier=None,
            is_closed=True,
            supplier_disclosed=False,
        )

        graph_data = build_graph_data(company, [contract])
        closed_titles = [
            node['title']
            for node in graph_data['nodes']
            if node.get('group') == 'closed'
        ]

        self.assertTrue(closed_titles)
        self.assertIn('Победитель не раскрыт', closed_titles[0])
        self.assertIn('ИНН поставщика отсутствует', closed_titles[0])
        self.assertIn('закрытая закупка', ' '.join(edge['title'] for edge in graph_data['edges']))

    def test_graph_aggregates_large_contract_sets_by_counterparty(self):
        company = Company.objects.create(inn=TARGET_INN, name='Компания')
        supplier = Company.objects.create(inn='7705966893', name='Поставщик')
        contracts = [
            Contract(
                number=f'OPEN-{index}',
                title='Повторяющаяся поставка',
                price=Decimal('1000'),
                date=timezone.localdate(),
                customer=company,
                supplier=supplier,
            )
            for index in range(20)
        ]

        graph_data = build_graph_data(company, contracts)

        self.assertEqual(graph_data['mode'], 'aggregated')
        self.assertEqual(len([node for node in graph_data['nodes'] if node.get('group') == 'contract']), 0)
        self.assertEqual(len(graph_data['edges']), 1)
        self.assertEqual(graph_data['edges'][0]['details']['kind'], 'aggregate')
        self.assertIn('Количество контрактов: 20', graph_data['edges'][0]['title'])


class ImportContractsCsvTests(TestCase):
    def test_demo_csv_still_imports_with_optional_supplier_fields(self):
        csv_path = Path(__file__).resolve().parents[1] / 'data' / 'import' / 'contracts_demo.csv'
        stdout = StringIO()

        call_command('import_contracts_csv', str(csv_path), stdout=stdout)

        self.assertEqual(Contract.objects.count(), 8)
        closed_contract = Contract.objects.get(number='DEMO-2026-004')
        self.assertTrue(closed_contract.is_closed)
        self.assertFalse(closed_contract.supplier_disclosed)
        self.assertIsNone(closed_contract.supplier)
        self.assertIsNone(closed_contract.execution_date)


class DemoDatasetSmokeTests(TestCase):
    DEMO_INNS = (
        '7729040491',
        '7705966893',
        '7710349494',
        '7707083893',
        '9731073530',
        '760406370881',
        '2634035198',
        '3500004094',
    )

    @classmethod
    def setUpTestData(cls):
        data_dir = Path(__file__).resolve().parents[1] / 'data' / 'import'
        call_command('import_contracts_csv', str(data_dir / 'contracts_demo.csv'), stdout=StringIO())
        call_command('import_contracts_csv', str(data_dir / 'contracts_eis_demo_mirea_30.csv'), stdout=StringIO())

    def test_demo_inn_pages_render(self):
        for inn in self.DEMO_INNS:
            with self.subTest(inn=inn):
                response = self.client.get(f'/company/{inn}/')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Тендеры и закупки')


class CompanyViewTests(TestCase):
    def test_company_detail_rejects_invalid_inn(self):
        response = self.client.get('/company/not-an-inn/')

        self.assertEqual(response.status_code, 400)

    @patch('chain.services.company_lookup.fetch_company_from_dadata', return_value=None)
    @patch('chain.views.sync_public_contracts_by_inn')
    def test_company_detail_get_does_not_sync_sources(self, sync_public_sources, _fetch_company):
        response = self.client.get(f'/company/{TARGET_INN}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'данные ещё не запрашивались')
        self.assertContains(response, 'Найти данные в публичных источниках')
        sync_public_sources.assert_not_called()

    @patch('chain.services.company_lookup.fetch_company_from_dadata', return_value=None)
    @patch('chain.views.sync_public_contracts_by_inn')
    def test_company_detail_post_refresh_syncs_sources(self, sync_public_sources, _fetch_company):
        sync_public_sources.return_value = zakupki.ZakupkiSyncResult(fetched=1, imported=1)

        response = self.client.post(f'/company/{TARGET_INN}/', {'action': 'refresh'})

        self.assertEqual(response.status_code, 200)
        sync_public_sources.assert_called_once_with(TARGET_INN)

        company = Company.objects.get(inn=TARGET_INN)
        self.assertIsNotNone(company.last_synced_at)
        self.assertEqual(company.last_sync_status, Company.SYNC_STATUS_OK)
        self.assertEqual(company.last_sync_message, 'Загружено 1, обновлено 0 контракт(ов).')

        log = SyncLog.objects.get(inn=TARGET_INN)
        self.assertEqual(log.status, Company.SYNC_STATUS_OK)
        self.assertEqual(log.fetched, 1)
        self.assertEqual(log.imported, 1)

    @patch('chain.services.company_lookup.fetch_company_from_dadata', return_value=None)
    def test_company_detail_shows_tender_block_and_closed_procurement_fallbacks(self, _fetch_company):
        company = Company.objects.create(inn=TARGET_INN, name='Компания')
        Contract.objects.create(
            number='CLOSED-1',
            customer=company,
            supplier=None,
            date=timezone.localdate(),
            is_closed=True,
            supplier_disclosed=False,
        )

        response = self.client.get(f'/company/{TARGET_INN}/')

        self.assertContains(response, 'Тендеры и закупки')
        self.assertContains(response, 'Дата исполнения')
        self.assertContains(response, 'Закрытая закупка')
        self.assertContains(response, 'Победитель не раскрыт')
        self.assertContains(response, 'ИНН поставщика отсутствует')
        self.assertContains(response, 'Настройка колонок')
        self.assertContains(response, 'data-column-toggle="supplier"')
        self.assertContains(response, 'Не выбрана ни одна колонка')
        self.assertContains(response, 'class="side-nav"')
        self.assertContains(response, 'href="#graph-section"')

    @patch('chain.services.company_lookup.fetch_company_from_dadata', return_value=None)
    def test_dynamic_business_pages_are_not_cached(self, _fetch_company):
        Company.objects.create(inn=TARGET_INN, name='Компания')

        for url in (
            f'/company/{TARGET_INN}/',
            f'/company/{TARGET_INN}/graph.json',
            f'/report/{TARGET_INN}/',
            '/history/',
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                cache_control = response.headers.get('Cache-Control', '')
                self.assertIn('no-cache', cache_control)
                self.assertIn('no-store', cache_control)
                self.assertIn('must-revalidate', cache_control)

    def test_public_sources_keep_provider_interface_and_legacy_tuple(self):
        provider_names = [provider.name for provider in PUBLIC_SOURCE_PROVIDERS]
        legacy_names = [name for name, _sync_func in PUBLIC_SOURCES]

        self.assertEqual(provider_names, [
            'ЕИС zakupki.gov.ru',
            'Портал поставщиков Москвы',
            'ТЭК-Торг',
            'Sberbank AST',
            'Bicotender',
            'RTS-tender',
        ])
        self.assertEqual(legacy_names, provider_names)

    @patch('chain.services.company_lookup.fetch_company_from_dadata', return_value=None)
    def test_report_download_returns_attachment(self, _fetch_company):
        Company.objects.create(inn=TARGET_INN, name='Компания')

        response = self.client.get(f'/report/{TARGET_INN}/?download=1')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers['Content-Disposition'],
            f'attachment; filename="supplytrace_report_{TARGET_INN}.html"',
        )
