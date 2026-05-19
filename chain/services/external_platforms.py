from django.conf import settings

from chain.services.zakupki import ZakupkiSyncResult, digits_only


UNSUPPORTED_SOURCE_MESSAGE = (
    'Источник не подключен: не найден стабильный публичный CSV/JSON API без авторизации, '
    'капчи или HTML-scraping.'
)


def sync_sberbank_ast_contracts_by_inn(inn, limit=None):
    return build_unsupported_source_result(
        inn=inn,
        enabled=getattr(settings, 'SBERBANK_AST_SYNC_ENABLED', False),
        source_url='https://www.sberbank-ast.ru/',
    )


def sync_bicotender_contracts_by_inn(inn, limit=None):
    return build_unsupported_source_result(
        inn=inn,
        enabled=getattr(settings, 'BICOTENDER_SYNC_ENABLED', False),
        source_url='https://www.bicotender.ru/',
    )


def sync_rts_tender_contracts_by_inn(inn, limit=None):
    return build_unsupported_source_result(
        inn=inn,
        enabled=getattr(settings, 'RTS_TENDER_SYNC_ENABLED', False),
        source_url='https://www.rts-tender.ru/',
    )


def build_unsupported_source_result(inn, enabled, source_url):
    result = ZakupkiSyncResult(enabled=enabled)
    clean_inn = digits_only(inn)

    if clean_inn:
        result.source_urls.append(source_url)

    result.errors.append(UNSUPPORTED_SOURCE_MESSAGE)
    return result
