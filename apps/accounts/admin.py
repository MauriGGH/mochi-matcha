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