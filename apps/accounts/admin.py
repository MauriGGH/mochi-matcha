"""
apps/accounts/admin.py — Registro del modelo Empleado en el panel de administración.

Se oculta el modelo Group de Django porque el control de acceso se hace mediante
el campo `rol` del Empleado, no con grupos de permisos de Django.
EmpleadoAdmin hereda de UserAdmin para que la contraseña se maneje con el widget
seguro de Django (hash, cambio de contraseña).
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .models import Empleado

# Ocultar el modelo Group del admin
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

@admin.register(Empleado)
class EmpleadoAdmin(UserAdmin):
    """
    Administración de empleados. Usa UserAdmin como base para heredar el manejo
    seguro de contraseñas. `add_fieldsets` define los campos visibles al crear
    un empleado nuevo desde el admin.
    """
    fieldsets = (
        (None, {'fields': ('usuario', 'password')}),
        ('Información personal', {'fields': ('nombre',)}),
        ('Rol y permisos', {
            'fields': ('rol', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('usuario', 'nombre', 'rol', 'password1', 'password2'),
        }),
    )
    list_display = ('usuario', 'nombre', 'rol', 'is_active')
    list_filter = ('rol', 'is_active')
    search_fields = ('usuario', 'nombre')
    ordering = ('usuario',)