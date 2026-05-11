from django.http import JsonResponse
from django.shortcuts import redirect, render
from .forms import InnSearchForm
from .models import Company, SearchHistory
from .services.analytics import build_graph_data, get_company_contracts, get_counterparty_stats
from .services.company_lookup import get_or_create_company_by_inn
from .services.public_sources import record_sync_result, sync_public_contracts_by_inn
from .services.zakupki import digits_only


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
    if not is_valid_inn(clean_inn):
        return render(
            request,
            'chain/company_not_found.html',
            {
                'inn': clean_inn or inn,
                'sync_result': None,
            },
            status=400,
        )

    sync_result = None
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

    if request.method == 'POST' and request.POST.get('action') == 'refresh':
        sync_result = sync_public_contracts_by_inn(clean_inn)
        company.refresh_from_db()
        record_sync_result(company, sync_result)

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
    if not is_valid_inn(clean_inn):
        return render(
            request,
            'chain/company_not_found.html',
            {
                'inn': clean_inn or inn,
                'sync_result': None,
            },
            status=400,
        )

    sync_result = None
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


def company_graph_json(request, inn):
    clean_inn = digits_only(inn)
    if not is_valid_inn(clean_inn):
        return JsonResponse({'error': 'Некорректный ИНН'}, status=400)

    company = Company.objects.filter(inn=clean_inn).first() or get_or_create_company_by_inn(clean_inn)

    contracts = get_company_contracts(company)
    graph_data = build_graph_data(company, contracts)

    return JsonResponse(graph_data)


def is_valid_inn(inn):
    return inn.isdigit() and len(inn) in (10, 12)
