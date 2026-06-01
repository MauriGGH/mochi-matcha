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

# Prefijos de ruta que no necesitan cookie de cliente: bienvenida (creación de sesión),
# áreas de staff (mesero, cocina, gerente) y recursos estáticos.
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
    Middleware que resuelve la cookie mm_session en una instancia de SesionCliente
    y la adjunta a request.sesion_cliente antes de llamar a la vista.

    También expone request.sesion_pagada (bool) y request.carrito_count (int)
    para que las plantillas los usen sin consultas adicionales.
    Las rutas en EXEMPT_PATHS se dejan pasar sin verificar la cookie.
    """

    def __init__(self, get_response):
        """Almacena el callable de la siguiente capa del stack de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """
        Procesa la request entrante:
        1. Inicializa los atributos de sesión en None/0/False.
        2. Omite la verificación en rutas exentas (staff, bienvenida, estáticos).
        3. Si existe la cookie mm_session, carga la SesionCliente correspondiente,
           verifica que no haya expirado (2 h desde fecha_inicio) y la asigna.
        4. En caso de token inválido o sesión expirada, elimina la cookie.
        """
        request.sesion_cliente = None
        request.carrito_count = 0
        request.sesion_pagada = False

        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return self.get_response(request)

        token = request.COOKIES.get(CLIENT_COOKIE_NAME)
        if token:
            try:
                from apps.mesas.models import SesionCliente
                # BUGFIX (problema 2): incluir "pagada". Si solo aceptamos
                # "activa", cuando el mesero cobra la mesa la sesión pasa a
                # "pagada", el .get() lanza DoesNotExist, se borra la cookie y
                # el cliente es EXPULSADO sin aviso. Manteniéndola cargada, el
                # cliente ve la pantalla de "cuenta pagada" y decide si sigue
                # o sale. Las sesiones "cerrada" sí terminan (expiración/salida).
                sesion = SesionCliente.objects.select_related("mesa").get(
                    token_cookie=token,
                    estado__in=("activa", "pagada"),
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
                # Bandera para vistas/plantillas: la cuenta ya se saldó. La
                # sesión sigue navegable en modo solo-lectura (sin nuevos
                # pedidos) hasta que el cliente decida salir.
                request.sesion_pagada = (sesion.estado == "pagada")
                carrito = request.session.get("carrito", [])
                request.carrito_count = len(carrito)

            except Exception:
                response = self.get_response(request)
                response.delete_cookie(CLIENT_COOKIE_NAME)
                return response

        return self.get_response(request)
