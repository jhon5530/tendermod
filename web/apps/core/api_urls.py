from django.urls import path
from . import views

urlpatterns = [
    path('task-status/<str:task_id>/', views.task_status, name='task_status'),
    path('db-status/', views.db_status, name='db_status'),
]
