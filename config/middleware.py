"""
config/middleware.py
Middleware de modo mantenimiento para Mochi Matcha.

Lee la clave `modo_mantenimiento` del modelo Configuracion.
Si está activa, redirige a /mantenimiento/ excepto a usuarios staff y rutas excluidas.
"""
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

EXCLUDED_PATHS = [
    '/mantenimiento/',
    '/admin/',
    '/gerente/login/',
    '/gerente/logout/',
    '/mesero/login/',
    '/cocina/login/',
]


class MaintenanceModeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Siempre permitir rutas excluidas
        path = request.path_info
        if any(path.startswith(p) for p in EXCLUDED_PATHS):
            return None

        # Siempre permitir staff/superusers autenticados
        if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'rol', '') in ('gerente', 'admin')):
            return None

        # Verificar en BD (con caché simple en memoria por proceso)
        try:
            from apps.gerente.models import Configuracion
            cfg = Configuracion.objects.filter(clave='modo_mantenimiento').first()
            if cfg and cfg.valor.lower() in ('true', '1', 'yes'):
                return redirect('/mantenimiento/')
        except Exception:
            # Si la tabla no existe aún (primera migración), no bloquear
            pass

        return None
