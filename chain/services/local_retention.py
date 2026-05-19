from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from chain.models import Company, Contract, SearchHistory, SyncLog


def get_local_data_ttl():
    ttl_hours = getattr(settings, 'SUPPLYTRACE_LOCAL_DATA_TTL_HOURS', 24)

    if ttl_hours is None or int(ttl_hours) < 0:
        return None

    return timedelta(hours=int(ttl_hours))


def purge_expired_local_data(now=None):
    ttl = get_local_data_ttl()
    if ttl is None:
        return {
            'contracts': 0,
            'companies': 0,
            'searches': 0,
            'sync_logs': 0,
        }

    now = now or timezone.now()
    cutoff = now - ttl

    deleted_contracts = Contract.objects.filter(imported_at__lt=cutoff).delete()[0]
    deleted_searches = SearchHistory.objects.filter(created_at__lt=cutoff).delete()[0]
    deleted_sync_logs = SyncLog.objects.filter(created_at__lt=cutoff).delete()[0]
    deleted_companies = (
        Company.objects
        .filter(customer_contracts__isnull=True, supplier_contracts__isnull=True)
        .filter(Q(created_at__lt=cutoff) | Q(created_at__isnull=True))
        .delete()[0]
    )

    return {
        'contracts': deleted_contracts,
        'companies': deleted_companies,
        'searches': deleted_searches,
        'sync_logs': deleted_sync_logs,
    }
