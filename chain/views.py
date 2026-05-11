from django.shortcuts import redirect, render
from .forms import InnSearchForm
from .models import Company, SearchHistory
from .services.analytics import build_graph_data, get_company_contracts, get_counterparty_stats
from .services.company_lookup import get_or_create_company_by_inn
from .services.zakupki import digits_only, sync_contracts_by_inn


def index(request):
    form = InnSearchForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        inn = form.cleaned_data['inn']
        SearchHistory.objects.create(inn=inn)
        return redirect('company_detail', inn=inn)

    recent_searches = SearchHistory.objects.all()[:10]
    return render(request, 'chain/index.html', {
        'form': form,
        'recent_searches': recent_searches,
    })


def company_detail(request, inn):
    clean_inn = digits_only(inn)
    sync_result = sync_contracts_by_inn(clean_inn)
    company = Company.objects.filter(inn=clean_inn).first() or get_or_create_company_by_inn(clean_inn)

    if company is None:
        return render(
            request,
            'chain/company_not_found.html',
            {
                'inn': clean_inn,
                'sync_result': sync_result,
            },
            status=404,
        )

    contracts = get_company_contracts(company)
    stats = get_counterparty_stats(company, contracts)
    graph_data = build_graph_data(company, contracts)

    return render(request, 'chain/company_detail.html', {
        'company': company,
        'contracts': contracts,
        'stats': stats,
        'graph_data': graph_data,
        'sync_result': sync_result,
    })


def history(request):
    searches = SearchHistory.objects.all()[:100]
    return render(request, 'chain/history.html', {'searches': searches})


def report(request, inn):
    clean_inn = digits_only(inn)
    sync_result = sync_contracts_by_inn(clean_inn)
    company = Company.objects.filter(inn=clean_inn).first() or get_or_create_company_by_inn(clean_inn)

    if company is None:
        return render(
            request,
            'chain/company_not_found.html',
            {
                'inn': clean_inn,
                'sync_result': sync_result,
            },
            status=404,
        )

    contracts = get_company_contracts(company)
    stats = get_counterparty_stats(company, contracts)
    graph_data = build_graph_data(company, contracts)

    return render(request, 'chain/report.html', {
        'company': company,
        'contracts': contracts,
        'stats': stats,
        'graph_data': graph_data,
        'sync_result': sync_result,
    })
