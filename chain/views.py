from django.shortcuts import redirect, render
from .forms import InnSearchForm
from .models import Company, SearchHistory
from .services.analytics import build_graph_data, get_company_contracts, get_counterparty_stats
from .services.company_lookup import get_or_create_company_by_inn


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
    company = get_or_create_company_by_inn(inn)

    if company is None:
        return render(request, 'chain/company_not_found.html', {'inn': inn}, status=404)

    contracts = get_company_contracts(company)
    stats = get_counterparty_stats(company, contracts)
    graph_data = build_graph_data(company, contracts)

    return render(request, 'chain/company_detail.html', {
        'company': company,
        'contracts': contracts,
        'stats': stats,
        'graph_data': graph_data,
    })


def history(request):
    searches = SearchHistory.objects.all()[:100]
    return render(request, 'chain/history.html', {'searches': searches})


def report(request, inn):
    company = get_or_create_company_by_inn(inn)

    if company is None:
        return render(request, 'chain/company_not_found.html', {'inn': inn}, status=404)

    contracts = get_company_contracts(company)
    stats = get_counterparty_stats(company, contracts)
    graph_data = build_graph_data(company, contracts)

    return render(request, 'chain/report.html', {
        'company': company,
        'contracts': contracts,
        'stats': stats,
        'graph_data': graph_data,
    })
