from django.urls import path
from . import views

app_name = 'gerente'

urlpatterns = [
    path('login/', views.login_gerente, name='login_gerente'),
    path('logout/', views.logout_gerente, name='logout_gerente'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('floor-plan/', views.floor_plan, name='floor_plan'),
    path('floor-plan/estado/', views.mesas_estado, name='mesas_estado'),
    path('floor-plan/mesa/<int:mesa_id>/', views.detalle_mesa, name='detalle_mesa'),
    path('pedidos/cancelar/', views.cancelar_pedido, name='cancelar_pedido'),
    # Productos / menú
    path('menu/', views.productos, name='productos'),
    path('menu/productos/', views.productos, name='productos'),
    path('menu/productos/nuevo/', views.productos_nuevo, name='productos_nuevo'),
    path('menu/productos/<int:id>/editar/', views.producto_editar, name='producto_editar'),
    path('menu/productos/<int:id>/eliminar/', views.producto_eliminar, name='producto_eliminar'),
    path('menu/categorias/', views.categorias, name='categorias'),
    path('menu/categorias/<int:id>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
    path('menu/modificadores/', views.modificadores, name='modificadores'),
    path('menu/modificadores/crear/', views.modificador_crear, name='modificador_crear'),
    path('menu/modificadores/<int:id>/eliminar/', views.modificador_eliminar, name='modificador_eliminar'),
    path('menu/promociones/', views.promociones, name='promociones'),
    path('menu/promociones/<int:id>/toggle/', views.promocion_toggle, name='promocion_toggle'),
    path('menu/promociones/<int:id>/eliminar/', views.promocion_eliminar, name='promocion_eliminar'),
    # Mesas
    path('mesas/', views.mesas, name='mesas'),
    path('mesas/crud/', views.mesas_crud, name='mesas_crud'),
    path('mesas/<int:id>/eliminar/', views.mesa_eliminar, name='mesa_eliminar'),
    path('mesas/<int:mesa_id>/asignar/', views.asignar_mesero, name='asignar_mesero'),
    # Empleados
    path('empleados/', views.empleados, name='empleados'),
    path('empleados/nuevo/', views.empleados_nuevo, name='empleados_nuevo'),
    path('empleados/<int:id>/toggle/', views.empleado_toggle, name='empleado_toggle'),
    path('empleados/<int:id>/editar/', views.empleado_editar, name='empleado_editar'),
    # Reportes
    path('reportes/', views.reportes, name='reportes'),
    path('auditoria/', views.auditoria, name='auditoria'),
    path('stats/', views.stats_json, name='stats_json'),
    # Configuración
    path('configuracion/', views.configuracion, name='configuracion'),
    # Aliases que usan los templates actuales
    path('menu/mesas/', views.mesas_crud, name='mesas_crud'),
    path('menu/empleados/', views.empleados, name='empleados_menu'),
]
