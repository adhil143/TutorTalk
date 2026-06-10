from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('app/', views.notebook_hub, name='notebook_hub'),
    path('app/notebook/<int:notebook_id>/', views.notebook_workspace, name='notebook_workspace'),
    path('app/notebook/delete/<int:notebook_id>/', views.delete_notebook, name='delete_notebook'),
    path('app/source/delete/<int:note_id>/', views.delete_source, name='delete_source'),
    path('send_chat/', views.send_chat, name='send_chat'),
    path('register/', views.api_register, name='register'),
    path('login/', views.api_login, name='login'),
    path('logout/', views.api_logout, name='logout'),
]
