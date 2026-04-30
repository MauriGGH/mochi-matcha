"""
Middleware para autenticación de clientes vía cookie.
FIX: añadida verificación real de expiración (2 horas desde fecha_inicio).
"""
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

CLIENT_COOKIE_NAME = "mm_session"
SESSION_DURATION_HOURS = 2

EXEMPT_PATHS = [
    "/bienvenida/",
    "/admin/",
    "/mesero/",
    "/cocina/",
    "/gerente/",
    "/accounts/",
    "/static/",
    "/media/",
]


class ClienteSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.sesion_cliente = None
        request.carrito_count = 0

        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return self.get_response(request)

        token = request.COOKIES.get(CLIENT_COOKIE_NAME)
        if token:
            try:
                from apps.mesas.models import SesionCliente
                sesion = SesionCliente.objects.select_related("mesa").get(
                    token_cookie=token,
                    estado="activa",
                )

                # FIX: verificación real de expiración
                expira_en = sesion.fecha_inicio + timedelta(hours=SESSION_DURATION_HOURS)
                if timezone.now() > expira_en:
                    # Sesión expirada — cerrar y limpiar cookie
                    sesion.estado = "cerrada"
                    sesion.save(update_fields=["estado"])
                    response = self.get_response(request)
                    response.delete_cookie(CLIENT_COOKIE_NAME)
                    return response

                request.sesion_cliente = sesion
                carrito = request.session.get("carrito", [])
                request.carrito_count = len(carrito)

            except Exception:
                response = self.get_response(request)
                response.delete_cookie(CLIENT_COOKIE_NAME)
                return response

        return self.get_response(request)
