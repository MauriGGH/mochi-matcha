# accounts/models.py
"""
apps/accounts/models.py — Modelo de usuario personalizado para el sistema Mochi Matcha.

Reemplaza al User de Django con un modelo Empleado que usa `usuario` como
USERNAME_FIELD (en lugar de `email` o `username` estándar). Esto permite que el
sistema de autenticación de Django funcione con las credenciales del personal interno.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class EmpleadoManager(BaseUserManager):
    """
    Manager personalizado para el modelo Empleado.

    `create_user`: crea un empleado con el rol por defecto 'mesero'.
    `create_superuser`: crea un empleado admin/superuser desde la consola de Django
                        (manage.py createsuperuser). Lee `usuario` de extra_fields
                        porque Django no lo pasa como argumento posicional cuando
                        USERNAME_FIELD no es 'username'.
    """
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('El usuario es obligatorio')
        extra_fields.setdefault('rol', 'mesero')
        user = self.model(usuario=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, password=None, **extra_fields):
        username = extra_fields.pop('usuario', None)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', 'admin')
        extra_fields.setdefault('nombre', username)
        return self.create_user(username, password, **extra_fields)


class Empleado(AbstractBaseUser, PermissionsMixin):
    """
    Usuario del sistema (empleado del restaurante).

    `usuario`: campo de login, único. Es el USERNAME_FIELD para Django Auth.
    `rol`: controla el acceso a módulos (mesero → panel mesas; cocina → KDS;
           gerente/admin → dashboard y configuración).
    `activo` / `is_active`: `is_active` es el campo estándar de Django Auth;
                             `activo` es el campo propio del negocio (ambos deben
                             estar en True para que el empleado pueda operar).
    `is_staff`: permite acceso al Django Admin (/admin/).
    El nombre se normaliza a MAYÚSCULAS en save().
    """
    ROLES = [
        ('mesero', 'Mesero'),
        ('cocina', 'Cocina'),
        ('gerente', 'Gerente'),
        ('admin', 'Administrador'),
    ]

    id_empleado = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    usuario = models.CharField(max_length=50, unique=True)
    rol = models.CharField(max_length=20, choices=ROLES, default='mesero')
    activo = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    USERNAME_FIELD = 'usuario'
    REQUIRED_FIELDS = ['nombre']

    objects = EmpleadoManager()

    def save(self, *args, **kwargs):
        if self.nombre:
            self.nombre = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre