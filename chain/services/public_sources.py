from dataclasses import dataclass

from django.utils import timezone

from chain.models import Company, SyncLog
from chain.services.external_platforms import (
    sync_bicotender_contracts_by_inn,
    sync_rts_tender_contracts_by_inn,
)
from chain.services.mos_zakupki import sync_mos_contracts_by_inn
from chain.services.sberbank_ast import sync_sberbank_ast_contracts_by_inn
from chain.services.tektorg import sync_tektorg_contracts_by_inn
from chain.services.zakupki import ZakupkiSyncResult, sync_contracts_by_inn as sync_eis_contracts_by_inn


@dataclass(frozen=True)
class PublicSourceProvider:
    name: str
    sync_func: object

    def sync(self, inn, limit=None):
        return self.sync_func(inn, limit=limit)


PUBLIC_SOURCE_PROVIDERS = (
    PublicSourceProvider('ЕИС zakupki.gov.ru', sync_eis_contracts_by_inn),
    PublicSourceProvider('Портал поставщиков Москвы', sync_mos_contracts_by_inn),
    PublicSourceProvider('ТЭК-Торг', sync_tektorg_contracts_by_inn),
    PublicSourceProvider('Sberbank AST', sync_sberbank_ast_contracts_by_inn),
    PublicSourceProvider('Bicotender', sync_bicotender_contracts_by_inn),
    PublicSourceProvider('RTS-tender', sync_rts_tender_contracts_by_inn),
)

PUBLIC_SOURCES = tuple((provider.name, provider.sync_func) for provider in PUBLIC_SOURCE_PROVIDERS)


def sync_public_contracts_by_inn(inn, limit=None):
    result = ZakupkiSyncResult(enabled=False)

    for provider in PUBLIC_SOURCE_PROVIDERS:
        try:
            source_result = provider.sync(inn, limit=limit)
        except Exception as exc:
            source_result = ZakupkiSyncResult()
            source_result.errors.append(f'Источник "{provider.name}" временно недоступен: {exc}')

        result.sources.append(build_source_status(provider.name, source_result))

        if not source_result.enabled:
            continue

        if not result.enabled:
            result.enabled = True

        merge_sync_result(result, source_result)

    return result


def merge_sync_result(target, source):
    target.fetched += source.fetched
    target.imported += source.imported
    target.updated += source.updated
    target.unchanged += source.unchanged
    target.skipped += source.skipped
    target.errors.extend(source.errors)
    target.source_urls.extend(source.source_urls)


def build_source_status(name, result):
    return {
        'name': name,
        'enabled': result.enabled,
        'fetched': result.fetched,
        'saved': result.saved,
        'imported': result.imported,
        'updated': result.updated,
        'unchanged': result.unchanged,
        'skipped': result.skipped,
        'errors': result.errors,
        'message': result.errors[0] if result.errors else '',
    }


def record_sync_result(company, result):
    status = get_sync_status(result)
    message = build_sync_message(result)
    now = timezone.now()

    company.last_synced_at = now
    company.last_sync_status = status
    company.last_sync_message = message
    company.save(update_fields=['last_synced_at', 'last_sync_status', 'last_sync_message'])

    SyncLog.objects.create(
        inn=company.inn,
        company=company,
        status=status,
        message=message,
        fetched=result.fetched,
        imported=result.imported,
        updated=result.updated,
        unchanged=result.unchanged,
        skipped=result.skipped,
        source_snapshot=result.sources,
    )


def get_sync_status(result):
    if not result.enabled:
        return Company.SYNC_STATUS_DISABLED
    if result.has_errors and not (result.fetched or result.saved or result.unchanged):
        return Company.SYNC_STATUS_ERROR
    if result.has_errors:
        return Company.SYNC_STATUS_WARNING
    return Company.SYNC_STATUS_OK


def build_sync_message(result):
    if not result.enabled:
        return 'Обновление из публичных источников отключено.'
    if result.has_errors and not (result.fetched or result.saved or result.unchanged):
        return 'Публичные источники сейчас недоступны.'
    if result.has_errors:
        return 'Данные частично обновлены, один из источников временно недоступен.'
    if result.saved:
        return f'Загружено {result.imported}, обновлено {result.updated} контракт(ов).'
    if result.unchanged:
        return f'Проверено {result.unchanged} контракт(ов), изменений нет.'
    return 'Новых контрактов за последний год не найдено.'
