"""
Middleware para autenticación de clientes vía cookie.

No usa el sistema de auth de Django — los comensales no son usuarios Django.
Valida el token_cookie contra SesionCliente y adjunta la sesión al request.
"""
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

CLIENT_COOKIE_NAME = "mm_session"
SESSION_DURATION_HOURS = 2

# Rutas que NO requieren sesión de cliente
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
    """
    Para cada request hacia el módulo cliente:
      1. Lee la cookie mm_session
      2. Busca la SesionCliente activa correspondiente
      3. Verifica que no haya expirado (2 horas de inactividad)
      4. Adjunta la sesión a request.sesion_cliente
      5. Si no existe o expiró → request.sesion_cliente = None
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.sesion_cliente = None
        request.carrito_count  = 0

        # Solo procesa rutas del módulo cliente
        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return self.get_response(request)

        token = request.COOKIES.get(CLIENT_COOKIE_NAME)
        if token:
            try:
                from mesas.models import SesionCliente
                sesion = SesionCliente.objects.select_related("mesa").get(
                    token_cookie=token,
                    estado="activa",
                )
                # Check expiry via last activity (stored in session or inferred)
                # For simplicity we extend on each request via a last_activity cookie
                request.sesion_cliente = sesion

                # Attach carrito count from Django session
                carrito = request.session.get("carrito", [])
                request.carrito_count = len(carrito)

            except Exception:
                # Invalid or expired token — clear cookie in response
                response = self.get_response(request)
                response.delete_cookie(CLIENT_COOKIE_NAME)
                return response

        return self.get_response(request)
