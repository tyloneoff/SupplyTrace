from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('company/<str:inn>/', views.company_detail, name='company_detail'),
    path('history/', views.history, name='history'),
    path('report/<str:inn>/', views.report, name='report'),
]
