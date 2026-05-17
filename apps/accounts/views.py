# accounts/views.py — vistas de autenticación compartidas (logout universal + login por rol)
"""
apps/accounts/views.py — Vistas de autenticación genéricas del sistema.

`login_view`:  punto de entrada unificado para todos los roles de staff.
               Redirige al módulo correspondiente según el rol del empleado.
`logout_view`: cierra la sesión Django y redirige a la raíz del sitio.

Los login específicos de cada módulo (cocina, mesero, gerente) tienen sus propias
vistas que validan el rol antes de hacer login, garantizando que solo el personal
del área pueda acceder a cada pantalla.
"""
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render

# Mapeo rol → URL nombrada de destino tras el login exitoso.
# Gerente y admin aterrizan en el mismo dashboard.
_ROLE_REDIRECTS = {
    "mesero":  "mesero:mapa_mesas",
    "cocina":  "cocina:kds",
    "gerente": "gerente:dashboard",
    "admin":   "gerente:dashboard",
}

def login_view(request):
    """Login genérico que redirige al módulo correcto según el rol del empleado."""
    if request.user.is_authenticated:
        dest = _ROLE_REDIRECTS.get(getattr(request.user, "rol", ""), "/")
        return redirect(dest)

    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, username=usuario, password=contrasena)
        if user and user.is_active and user.rol in _ROLE_REDIRECTS:
            login(request, user)
            return redirect(_ROLE_REDIRECTS[user.rol])
        error = "Credenciales incorrectas o sin acceso al sistema."

    return render(request, "base/login.html", {
        "rol": "staff",
        "rol_display": "Acceso al sistema",
        "form_action": "/accounts/login/",
        "error": error,
        "usuario_previo": request.POST.get("usuario", ""),
    })


def logout_view(request):
    """Cierra la sesión Django de cualquier rol y redirige a la raíz del sitio."""
    logout(request)
    return redirect("/")
