from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from chain.models import Company, Contract, SyncLog
from chain.services import zakupki
from chain.services.analytics import get_tender_summary
from chain.services.mos_zakupki import parse_mos_contract_item


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
