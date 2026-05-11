from django.contrib import admin
from .models import Company, Contract, SearchHistory, SyncLog


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'inn', 'kpp', 'ogrn', 'last_synced_at', 'last_sync_status')
    search_fields = ('name', 'inn', 'kpp', 'ogrn')
    list_filter = ('last_sync_status', 'last_synced_at')


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'price', 'customer', 'supplier', 'is_closed', 'supplier_disclosed')
    search_fields = ('number', 'customer__name', 'customer__inn', 'supplier__name', 'supplier__inn')
    list_filter = ('date', 'is_closed', 'supplier_disclosed')


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('inn', 'created_at')
    search_fields = ('inn',)
    list_filter = ('created_at',)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('inn', 'status', 'fetched', 'imported', 'updated', 'unchanged', 'skipped', 'created_at')
    search_fields = ('inn', 'company__name', 'company__inn')
    list_filter = ('status', 'created_at')
    readonly_fields = (
        'inn',
        'company',
        'status',
        'message',
        'fetched',
        'imported',
        'updated',
        'unchanged',
        'skipped',
        'source_snapshot',
        'created_at',
    )
