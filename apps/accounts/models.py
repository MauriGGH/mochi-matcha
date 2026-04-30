# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class EmpleadoManager(BaseUserManager):
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

    def __str__(self):
        return self.nombre