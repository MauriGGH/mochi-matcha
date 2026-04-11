"""
Decoradores de acceso basados en roles para los módulos de staff.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def rol_requerido(*roles):
    """
    Verifica que el usuario autenticado tenga uno de los roles indicados.

    Uso:
        @rol_requerido('mesero', 'gerente')
        def mi_vista(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if request.user.rol not in roles:
                messages.error(request, "No tienes permiso para acceder a esta sección.")
                return redirect("accounts:login")
            if not request.user.is_active:
                messages.error(request, "Tu cuenta está inactiva. Contacta al administrador.")
                return redirect("accounts:login")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


# Shortcuts
def mesero_requerido(view_func):
    return rol_requerido("mesero", "gerente", "admin")(view_func)

def gerente_requerido(view_func):
    return rol_requerido("gerente", "admin")(view_func)

def cocina_requerido(view_func):
    return rol_requerido("cocina", "gerente", "admin")(view_func)

def admin_requerido(view_func):
    return rol_requerido("admin")(view_func)


def sesion_cliente_requerida(view_func):
    """
    Para vistas del módulo cliente.
    Verifica que request.sesion_cliente esté presente (seteado por el middleware).
    Si no, redirige a bienvenida con el parámetro de mesa si está disponible.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.sesion_cliente:
            mesa_id = request.GET.get("mesa") or request.session.get("mesa_id")
            if mesa_id:
                return redirect(f"/bienvenida/?mesa={mesa_id}")
            return redirect("/bienvenida/")
        return view_func(request, *args, **kwargs)
    return _wrapped
