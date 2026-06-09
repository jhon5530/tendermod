from django.urls import path
from . import views

app_name = 'analysis'

urlpatterns = [
    path('', views.analysis_list, name='list'),
    path('new/', views.analysis_new, name='new'),
    path('quick/', views.redneet_qa, name='quick'),
    path('quick/redneet/', views.redneet_qa, name='quick_redneet'),
    path('quick/query/', views.redneet_qa_query, name='redneet_qa_query'),
    path('quick/clear/', views.redneet_qa_clear, name='redneet_qa_clear'),
    path('quick/evaluate/', views.analysis_quick_evaluate, name='quick_evaluate'),
    path('<int:pk>/step1/', views.analysis_step1, name='step1'),
    path('<int:pk>/step1/extract/', views.analysis_extract, name='extract'),
    path('<int:pk>/auto/', views.analysis_auto, name='analysis_auto'),
    path('<int:pk>/auto/progress/', views.auto_progress, name='auto_progress'),
    path('<int:pk>/auto/evaluate-experience/', views.auto_evaluate_experience, name='auto_evaluate_experience'),
    path('<int:pk>/auto/evaluate-indicators/', views.auto_evaluate_indicators, name='auto_evaluate_indicators'),
    path('<int:pk>/auto/evaluate-team-profiles/', views.auto_evaluate_team_profiles, name='auto_evaluate_team_profiles'),
    path('<int:pk>/auto/generate-conclusion/', views.auto_generate_conclusion, name='auto_generate_conclusion'),
    path('<int:pk>/step2/', views.analysis_step2, name='step2'),
    path('<int:pk>/step2/evaluate/', views.analysis_evaluate, name='evaluate'),
    path('<int:pk>/results/', views.analysis_results, name='results'),
    path('<int:pk>/export/excel/', views.export_excel, name='export_excel'),
    path('<int:pk>/export/text/', views.export_text, name='export_text'),
    path('<int:pk>/export/context/', views.export_context, name='export_context'),
    path('<int:pk>/checklist/save/', views.analysis_checklist_save, name='checklist_save'),
    path('<int:pk>/pliego/qa/', views.analysis_pliego_qa, name='pliego_qa'),
    path('<int:pk>/download-ocr/', views.download_ocr, name='download_ocr'),
    path('<int:pk>/download-pdf/', views.download_pdf, name='download_pdf'),
    path('<int:pk>/rename/', views.session_rename, name='rename'),
    path('<int:pk>/delete/', views.analysis_delete, name='delete'),
    path('team/', views.team_qa, name='team_qa'),
    path('team/query/', views.team_qa_query, name='team_qa_query'),
    path('team/clear/', views.team_qa_clear, name='team_qa_clear'),
]
