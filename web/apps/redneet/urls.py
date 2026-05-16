from django.urls import path
from . import views

app_name = 'redneet'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload-indicadores/', views.upload_indicadores, name='upload_indicadores'),
    path('upload-experiencia/', views.upload_experiencia, name='upload_experiencia'),
    path('upload-equipo/', views.upload_equipo, name='upload_equipo'),
    path('clear-indicadores/', views.clear_indicadores, name='clear_indicadores'),
    path('clear-experiencia/', views.clear_experiencia, name='clear_experiencia'),
    path('clear-equipo/', views.clear_equipo, name='clear_equipo'),
    path('settings/', views.system_settings, name='settings'),
    path('download-excel/<str:file_type>/', views.download_excel, name='download_excel'),
]
