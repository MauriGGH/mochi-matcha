from django.db import models

# Create your models here.
# ============================
# Catálogos
# ============================

class Empleado(models.Model):
    ROLES = [
        ('mesero', 'Mesero'),
        ('cajero', 'Cajero'),
        ('cocina', 'Cocina'),
        ('gerente', 'Gerente'),
        ('admin', 'Admin'),
    ]
    nombre = models.CharField(max_length=100)
    usuario = models.CharField(max_length=50, unique=True)
    contrasena_hash = models.CharField(max_length=255)
    rol = models.CharField(max_length=10, choices=ROLES)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class ModalidadIngreso(models.Model):
    descripcion = models.CharField(max_length=50)

    def __str__(self):
        return self.descripcion

class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    orden = models.IntegerField(default=0)

    def __str__(self):
        return self.nombre

class TipoPromocion(models.Model):
    descripcion = models.CharField(max_length=50)

    def __str__(self):
        return self.descripcion

class Promocion(models.Model):
    titulo = models.CharField(max_length=100)
    tipo_promocion = models.ForeignKey(TipoPromocion, on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    activa = models.BooleanField(default=True)
    codigo_cupon = models.CharField(max_length=50, null=True, blank=True, unique=True)
    limite_usos = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.titulo

class Mesa(models.Model):
    ESTADOS = [('libre', 'Libre'), ('ocupada', 'Ocupada')]
    numero_mesa = models.IntegerField(unique=True)
    capacidad = models.IntegerField()
    ubicacion = models.CharField(max_length=50, null=True, blank=True)
    codigo_qr = models.CharField(max_length=255, unique=True)
    pin_actual = models.CharField(max_length=60, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='libre')
    id_mesero_asignado = models.ForeignKey(Empleado, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Mesa {self.numero_mesa}"

class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen_url = models.CharField(max_length=255, null=True, blank=True)
    disponible = models.BooleanField(default=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre

class GrupoModificador(models.Model):
    TIPOS = [('única', 'Única'), ('múltiple', 'Múltiple')]
    nombre_grupo = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPOS, default='única')
    es_obligatorio = models.BooleanField(default=False)
    max_selecciones = models.IntegerField(null=True, blank=True)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_grupo

class OpcionModificador(models.Model):
    nombre_opcion = models.CharField(max_length=100)
    precio_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grupo = models.ForeignKey(GrupoModificador, on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_opcion

class MetodoPago(models.Model):
    descripcion = models.CharField(max_length=50)

    def __str__(self):
        return self.descripcion

class EstadoSolicitud(models.Model):
    descripcion = models.CharField(max_length=50)

    def __str__(self):
        return self.descripcion

# ============================
# Tablas dependientes
# ============================

class SesionCliente(models.Model):
    ESTADOS = [('activa','Activa'), ('pagada','Pagada'), ('cerrada','Cerrada')]
    alias = models.CharField(max_length=50)
    token_cookie = models.CharField(max_length=255, unique=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='activa')
    fecha_inicio = models.DateTimeField()
    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE)
    modalidad_ingreso = models.ForeignKey(ModalidadIngreso, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('mesa', 'alias')

    def __str__(self):
        return self.alias

class PromocionProducto(models.Model):
    promocion = models.ForeignKey(Promocion, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('promocion', 'producto')

class Pedido(models.Model):
    ESTADOS = [('recibido','Recibido'), ('preparando','Preparando'), ('listo','Listo'), ('entregado','Entregado'), ('cancelado','Cancelado')]
    fecha_hora_ingreso = models.DateTimeField()
    fecha_hora_entrega = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='recibido')
    motivo_cancelacion = models.TextField(null=True, blank=True)
    sesion = models.ForeignKey(SesionCliente, on_delete=models.CASCADE)
    modalidad = models.ForeignKey(ModalidadIngreso, on_delete=models.CASCADE)
    empleado_entrega = models.ForeignKey(Empleado, null=True, blank=True, on_delete=models.SET_NULL, related_name='entregas')

class DetallePedido(models.Model):
    cantidad = models.IntegerField()
    notas = models.CharField(max_length=255, null=True, blank=True)
    subtotal_calculado = models.DecimalField(max_digits=10, decimal_places=2)
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    promocion = models.ForeignKey(Promocion, null=True, blank=True, on_delete=models.SET_NULL)

class DetalleModificador(models.Model):
    cantidad = models.IntegerField(default=1)
    precio_extra_aplicado = models.DecimalField(max_digits=10, decimal_places=2)
    detalle = models.ForeignKey(DetallePedido, on_delete=models.CASCADE)
    opcion = models.ForeignKey(OpcionModificador, on_delete=models.CASCADE)

class SolicitudPago(models.Model):
    TIPOS = [('individual','Individual'), ('grupal','Grupal')]
    fecha_hora = models.DateTimeField()
    tipo = models.CharField(max_length=10, choices=TIPOS)
    total_individual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_mesa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    propina_sugerida = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sesion = models.ForeignKey(SesionCliente, null=True, blank=True, on_delete=models.SET_NULL)
    mesa = models.ForeignKey(Mesa, null=True, blank=True, on_delete=models.SET_NULL)
    metodo_pago = models.ForeignKey(MetodoPago, null=True, blank=True, on_delete=models.SET_NULL)
    estado_solicitud = models.ForeignKey(EstadoSolicitud, on_delete=models.CASCADE)

class Auditoria(models.Model):
    fecha_hora = models.DateTimeField()
    accion = models.CharField(max_length=100)
    detalle = models.TextField(null=True, blank=True)
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    mesa = models.ForeignKey(Mesa, null=True, blank=True, on_delete=models.SET_NULL)
    pedido = models.ForeignKey(Pedido, null=True, blank=True, on_delete=models.SET_NULL)

