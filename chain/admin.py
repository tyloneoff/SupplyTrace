from django.contrib import admin
from .models import Company, Contract, SearchHistory


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'inn', 'kpp', 'ogrn')
    search_fields = ('name', 'inn', 'kpp', 'ogrn')


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'price', 'customer', 'supplier')
    search_fields = ('number', 'customer__name', 'customer__inn', 'supplier__name', 'supplier__inn')
    list_filter = ('date',)


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('inn', 'created_at')
    search_fields = ('inn',)
    list_filter = ('created_at',)
