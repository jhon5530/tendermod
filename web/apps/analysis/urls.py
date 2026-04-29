from django.urls import path
from . import views

app_name = 'analysis'

urlpatterns = [
    path('', views.analysis_list, name='list'),
    path('new/', views.analysis_new, name='new'),
    path('quick/', views.analysis_quick, name='quick'),
    path('quick/evaluate/', views.analysis_quick_evaluate, name='quick_evaluate'),
    path('<int:pk>/step1/', views.analysis_step1, name='step1'),
    path('<int:pk>/step1/extract/', views.analysis_extract, name='extract'),
    path('<int:pk>/step2/', views.analysis_step2, name='step2'),
    path('<int:pk>/step2/evaluate/', views.analysis_evaluate, name='evaluate'),
    path('<int:pk>/results/', views.analysis_results, name='results'),
    path('<int:pk>/export/excel/', views.export_excel, name='export_excel'),
    path('<int:pk>/export/text/', views.export_text, name='export_text'),
    path('<int:pk>/export/context/', views.export_context, name='export_context'),
    path('<int:pk>/checklist/save/', views.analysis_checklist_save, name='checklist_save'),
    path('<int:pk>/pliego/qa/', views.analysis_pliego_qa, name='pliego_qa'),
]
