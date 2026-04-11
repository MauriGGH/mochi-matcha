# accounts/views.py — vistas de autenticación compartidas (logout universal)
from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    logout(request)
    return redirect("/")
