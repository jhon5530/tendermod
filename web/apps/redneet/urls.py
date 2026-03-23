from django.urls import path
from . import views

app_name = 'redneet'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload-indicadores/', views.upload_indicadores, name='upload_indicadores'),
    path('upload-experiencia/', views.upload_experiencia, name='upload_experiencia'),
    path('settings/', views.system_settings, name='settings'),
]
