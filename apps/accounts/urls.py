from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('logout/', views.logout_view, name='logout'),
    # login genérico (fallback; cada módulo tiene su propio login)
    path('login/', auth_views.LoginView.as_view(template_name='base/login.html'), name='login'),
]
