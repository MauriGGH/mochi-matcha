"""
Rutas URL del panel de administración (rol gerente/admin) de Mochi Matcha.
Cubre autenticación, floor plan, CRUD de menú, empleados, reportes y configuración.
"""
from django.urls import path
from . import views

app_name = 'gerente'

urlpatterns = [
    # ── Autenticación ────────────────────────────────────────────────────────
    path('login/', views.login_gerente, name='login_gerente'),
    path('logout/', views.logout_gerente, name='logout_gerente'),
    # ── Panel principal ──────────────────────────────────────────────────────
    path('dashboard/', views.dashboard, name='dashboard'),
    path('floor-plan/', views.floor_plan, name='floor_plan'),
    # Endpoint de polling JSON para actualizar el floor plan en tiempo real
    path('floor-plan/estado/', views.mesas_estado, name='mesas_estado'),
    # Detalle JSON de una mesa específica (pedidos activos + solicitudes de pago)
    path('floor-plan/mesa/<int:mesa_id>/', views.detalle_mesa, name='detalle_mesa'),
    # Cancelación de pedidos y solicitudes de pago desde la vista de gerente
    path('pedidos/cancelar/', views.cancelar_pedido, name='cancelar_pedido'),
    path('cuentas/cancelar/', views.cancelar_solicitud_pago, name='cancelar_solicitud_pago'),
    # Productos / menú
    path('menu/', views.productos, name='productos'),
    path('menu/productos/', views.productos, name='productos'),
    path('menu/productos/nuevo/', views.productos_nuevo, name='productos_nuevo'),
    path('menu/productos/<int:id>/editar/', views.producto_editar, name='producto_editar'),
    # Soft-delete: marca el producto como no disponible en lugar de borrarlo
    path('menu/productos/<int:id>/eliminar/', views.producto_eliminar, name='producto_eliminar'),
    # ── Categorías ───────────────────────────────────────────────────────────
    path('menu/categorias/', views.categorias, name='categorias'),
    path('menu/categorias/<int:id>/editar/', views.categoria_editar, name='categoria_editar'),
    path('menu/categorias/<int:id>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
    # ── Modificadores (grupos de opciones) ───────────────────────────────────
    path('menu/modificadores/', views.modificadores, name='modificadores'),
    path('menu/modificadores/crear/', views.modificador_crear, name='modificador_crear'),
    # Clona un grupo plantilla y lo asocia a uno o más productos
    path('menu/modificadores/clonar/', views.modificador_clonar, name='modificador_clonar'),
    # GET devuelve JSON con datos del grupo; POST actualiza (upsert seguro de opciones)
    path('menu/modificadores/<int:id>/editar/', views.modificador_editar, name='modificador_editar'),
    path('menu/modificadores/<int:id>/eliminar/', views.modificador_eliminar, name='modificador_eliminar'),
    # Marca/desmarca el grupo como plantilla reutilizable
    path('menu/modificadores/<int:id>/plantilla/', views.modificador_toggle_plantilla, name='modificador_toggle_plantilla'),
    # ── Promociones ──────────────────────────────────────────────────────────
    path('menu/promociones/', views.promociones, name='promociones'),
    # Activa/desactiva la promoción sin eliminarla
    path('menu/promociones/<int:id>/toggle/', views.promocion_toggle, name='promocion_toggle'),
    path('menu/promociones/<int:id>/eliminar/', views.promocion_eliminar, name='promocion_eliminar'),
    # GET devuelve JSON para el modal; POST guarda cambios
    path('menu/promociones/<int:id>/editar/', views.promocion_editar, name='promocion_editar'),
    # Mesas
    path('mesas/', views.mesas, name='mesas'),
    path('mesas/crud/', views.mesas_crud, name='mesas_crud'),
    # AJAX para gestión de ubicaciones (zonas del restaurante)
    path('mesas/ubicacion/crear/', views.ubicacion_crear, name='ubicacion_crear'),
    path('mesas/ubicacion/<int:id>/editar/', views.ubicacion_editar, name='ubicacion_editar'),
    path('mesas/ubicacion/<int:id>/eliminar/', views.ubicacion_eliminar, name='ubicacion_eliminar'),
    path('mesas/<int:id>/editar/', views.mesa_editar, name='mesa_editar'),
    # Eliminación protegida: solo borra si la mesa está libre
    path('mesas/<int:id>/eliminar/', views.mesa_eliminar, name='mesa_eliminar'),
    path('mesas/<int:mesa_id>/asignar/', views.asignar_mesero, name='asignar_mesero'),
    # Empleados
    path('empleados/', views.empleados, name='empleados'),
    path('empleados/nuevo/', views.empleados_nuevo, name='empleados_nuevo'),
    # Activa/desactiva el acceso del empleado al sistema
    path('empleados/<int:id>/toggle/', views.empleado_toggle, name='empleado_toggle'),
    path('empleados/<int:id>/editar/', views.empleado_editar, name='empleado_editar'),
    # Reportes UNIFICADOS (una sola sección)
    # Aliases legacy para no romper templates existentes
    # Reportes (todos unificados)
    path('reportes/', views.reportes_avanzados, name='reportes'),
    path('reportes/avanzados/', views.reportes_avanzados, name='reportes_avanzados'),
    # Exportación rápida del reporte avanzado a Excel (tipo pasado por querystring)
    path('reportes/avanzados/exportar/', views.reportes_avanzados_exportar, name='reportes_avanzados_exportar'),
    # Exportación básica a Excel o PDF (rango de fechas por querystring)
    path('reportes/exportar/', views.reporte_exportar, name='reporte_exportar'),
    # Exportación personalizada: el usuario elige secciones y formato
    path('reportes/exportar-custom/', views.reportes_exportar_custom, name='reportes_exportar_custom'),
    # Registro de auditoría de acciones del sistema
    path('auditoria/', views.auditoria, name='auditoria'),
    # JSON de KPIs en tiempo real para el dashboard
    path('stats/', views.stats_json, name='stats_json'),
    # Configuración
    path('configuracion/', views.configuracion, name='configuracion'),
    # Horarios de atención (3.1)
    path('configuracion/horarios/crear/',           views.horario_crear,    name='horario_crear'),
    path('configuracion/horarios/<int:id>/toggle/', views.horario_toggle,   name='horario_toggle'),
    path('configuracion/horarios/<int:id>/eliminar/', views.horario_eliminar, name='horario_eliminar'),
    # Upload / gestor de imágenes
    path('upload-imagen/', views.upload_imagen, name='upload_imagen'),
    path('imagenes/listar/', views.listar_imagenes, name='listar_imagenes'),
    path('imagenes/eliminar/', views.eliminar_imagen, name='eliminar_imagen'),
    # Aliases
    path('menu/mesas/', views.mesas_crud, name='mesas_crud'),
    path('menu/empleados/', views.empleados, name='empleados_menu'),
]
