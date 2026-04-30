"""
seed.py — Pobla la base de datos de Mochi Matcha simulando 1 mes de operación.
Ejecutar:
    docker compose exec web python manage.py shell -c "exec(open('seed.py').read())"
"""
import os, sys, uuid, random
from decimal import Decimal
from datetime import timedelta, datetime, time
from django.utils import timezone
from django.contrib.auth.hashers import make_password

# ── Configurar entorno Django ────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.catalogs.models import ModalidadIngreso, MetodoPago, EstadoSolicitud
from apps.accounts.models import Empleado
from apps.mesas.models import Mesa, SesionCliente, UbicacionMesa
from apps.menu.models import (
    Categoria, Producto, GrupoModificador, OpcionModificador,
    Promocion, TipoPromocion, TipoDescuento
)
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador, SolicitudPago

# ── Parámetros de la simulación ──────────────────────────────────────────────
DAYS = 30                   # días hacia atrás
TICKETS_PER_DAY = 12        # pedidos diarios promedio
MESAS_USADAS = [1,2,3,4,5,6,7,8]
ALIAS_CLIENTES = ["Sofía","Diego","Valeria","Mateo","Emilio","Luna","Joaquín","Renata",
                  "Gael","Camila","Iker","Naomi","Luka","Zoe","Max","Mía"]
MESEROS = ["maria","carlos"]   # llaves de empleados

ahora = timezone.now()

print("🌱 Iniciando seed de 1 mes...")

# ── 1. Catálogos ─────────────────────────────────────────────────────────────
qr,       _ = ModalidadIngreso.objects.get_or_create(descripcion="qr")
asistido, _ = ModalidadIngreso.objects.get_or_create(descripcion="asistido")

efectivo, _ = MetodoPago.objects.get_or_create(descripcion="Efectivo")
tarjeta,  _ = MetodoPago.objects.get_or_create(descripcion="Tarjeta")
mixto,    _ = MetodoPago.objects.get_or_create(descripcion="Mixto")

est_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")
est_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
est_cancelada, _ = EstadoSolicitud.objects.get_or_create(descripcion="cancelada")
print("  ✓ Catálogos")

# ── 2. Empleados ─────────────────────────────────────────────────────────────
admin = Empleado.objects.filter(usuario="admin").first()
if not admin:
    Empleado.objects.create_superuser(password="admin1234", usuario="admin", nombre="Administrador")

empleados = {}
for usr, nombre, rol, pw in [
    ("maria","María López","mesero","mesero123"),
    ("carlos","Carlos Ruiz","mesero","mesero123"),
    ("lucia","Lucía Mendoza","cocina","cocina123"),
    ("roberto","Roberto Soto","cocina","cocina123"),
    ("gerente1","Ana Martínez","gerente","gerente123"),
]:
    emp, created = Empleado.objects.get_or_create(
        usuario=usr,
        defaults={"nombre":nombre,"rol":rol,"activo":True,"is_staff":rol in ("admin","gerente")}
    )
    if created:
        emp.set_password(pw)
        emp.save()
    empleados[usr] = emp
print("  ✓ Empleados")

# ── 3. Ubicaciones ───────────────────────────────────────────────────────────
ubicaciones = {}
for nombre in ["Terraza","Interior","Barra","Salón privado"]:
    obj, _ = UbicacionMesa.objects.get_or_create(nombre=nombre)
    ubicaciones[nombre] = obj
print("  ✓ Ubicaciones")

# ── 4. Mesas ─────────────────────────────────────────────────────────────────
mesas = []
for num, cap, nombre_ubic in [
    (1,4,"Terraza"),(2,2,"Terraza"),(3,6,"Interior"),(4,4,"Interior"),
    (5,2,"Barra"),(6,4,"Barra"),(7,8,"Salón privado"),(8,4,"Interior")
]:
    mesa, _ = Mesa.objects.get_or_create(
        numero_mesa=num,
        defaults={
            "capacidad":cap,
            "ubicacion":ubicaciones[nombre_ubic],
            "codigo_qr":f"QR-MESA-{num:03d}",
            "estado":"libre",
            "id_mesero_asignado":empleados["maria"] if num<=4 else empleados["carlos"]
        }
    )
    mesas.append(mesa)
print("  ✓ Mesas")

# ── 5. Menú ──────────────────────────────────────────────────────────────────
# Categorías
cat_matcha  ,_=Categoria.objects.get_or_create(nombre="Matcha",     defaults={"orden":1,"area":"bar"})
cat_cafe    ,_=Categoria.objects.get_or_create(nombre="Café",       defaults={"orden":2,"area":"bar"})
cat_mochi   ,_=Categoria.objects.get_or_create(nombre="Mochi",      defaults={"orden":3,"area":"cocina"})
cat_postres ,_=Categoria.objects.get_or_create(nombre="Postres",    defaults={"orden":4,"area":"cocina"})
cat_snacks  ,_=Categoria.objects.get_or_create(nombre="Snacks",     defaults={"orden":5,"area":"cocina"})
cat_especial,_=Categoria.objects.get_or_create(nombre="Especiales",  defaults={"orden":6,"area":"ambos"})
print("  ✓ Categorías")

# Productos
prod_list = [
    ("Matcha Latte","Matcha ceremonial con leche de avena",65,cat_matcha),
    ("Matcha Frío","Matcha con leche fría y hielo",70,cat_matcha),
    ("Matcha Puro","Matcha ceremonial sin azúcar",55,cat_matcha),
    ("Hojicha Latte","Té tostado japonés con leche",60,cat_matcha),
    ("Café Americano","Espresso doble con agua caliente",45,cat_cafe),
    ("Cappuccino","Espresso con leche vaporizada",55,cat_cafe),
    ("Latte de Vainilla","Espresso, leche y vainilla natural",60,cat_cafe),
    ("Cold Brew","Café en frío 12 horas",65,cat_cafe),
    ("Mochi de Fresa","Mochi relleno de helado de fresa",45,cat_mochi),
    ("Mochi de Matcha","Mochi relleno de crema de matcha",45,cat_mochi),
    ("Mochi de Mango","Mochi relleno de helado de mango",45,cat_mochi),
    ("Mochi Trio","3 mochis a elección",120,cat_mochi),
    ("Brownie","Brownie de chocolate belga con nuez",50,cat_postres),
    ("Cheesecake Matcha","Cheesecake horneado con polvo de matcha",75,cat_postres),
    ("Waffle Japonés","Waffle estilo mochi con frutos rojos",80,cat_postres),
    ("Edamame","Edamame al vapor con sal de mar",40,cat_snacks),
    ("Onigiri Atún","Arroz japonés relleno de atún",55,cat_snacks),
    ("Combo Matcha+Mochi","Matcha latte + mochi a elección",100,cat_especial),
]
productos = {}
for nombre, desc, precio, cat in prod_list:
    p,_ = Producto.objects.get_or_create(
        nombre=nombre,
        defaults={"descripcion":desc,"precio":Decimal(str(precio)),"categoria":cat,"disponible":True}
    )
    productos[nombre] = p
print("  ✓ Productos")

# Modificadores (reutilizables M2M)
def add_grupo(producto, nombre_grupo, tipo, obligatorio, max_sel, opciones):
    g,_ = GrupoModificador.objects.get_or_create(
        nombre_grupo=nombre_grupo,
        defaults={"tipo":tipo,"es_obligatorio":obligatorio,"max_selecciones":max_sel}
    )
    g.productos.add(producto)
    for nombre_op, extra in opciones:
        OpcionModificador.objects.get_or_create(
            grupo=g, nombre_opcion=nombre_op,
            defaults={"precio_extra":Decimal(str(extra))}
        )
# Aplica modificadores igual que antes (solo a los primeros productos para simular)
for key in ["Matcha Latte","Matcha Frío","Hojicha Latte","Café Americano","Cappuccino","Latte de Vainilla","Cold Brew","Matcha Puro"]:
    if key in productos:
        add_grupo(productos[key],"Tamaño","única",True,None,[("Chico (250ml)",0),("Mediano (350ml)",10),("Grande (450ml)",20)])
        if key in ["Matcha Latte","Matcha Frío","Hojicha Latte","Cappuccino","Latte de Vainilla"]:
            add_grupo(productos[key],"Tipo de leche","única",False,None,[("Entera",0),("Avena",10),("Almendra",10),("Deslactosada",0)])
        if key in ["Matcha Latte","Hojicha Latte","Café Americano","Cappuccino","Latte de Vainilla"]:
            add_grupo(productos[key],"Temperatura","única",True,None,[("Caliente",0),("Frío",0)])
print("  ✓ Modificadores")

# Tipos de descuento
tipos_desc = {
    "porcentaje": TipoDescuento.objects.get_or_create(descripcion="Porcentaje")[0],
    "monto_fijo": TipoDescuento.objects.get_or_create(descripcion="Monto fijo")[0],
    "2x1": TipoDescuento.objects.get_or_create(descripcion="2x1")[0],
    "combo": TipoDescuento.objects.get_or_create(descripcion="Combo precio fijo")[0],
    "lleva_x": TipoDescuento.objects.get_or_create(descripcion="Lleva X paga Y")[0],
}

# Crear una promoción activa que cubra todo el mes simulado
promo_activa, _ = Promocion.objects.get_or_create(
    titulo="Matcha Lover 10%",
    defaults={
        "tipo_descuento": tipos_desc["porcentaje"],
        "valor_descuento": Decimal("10.00"),
        "aplicacion":"item",
        "fecha_inicio": ahora - timedelta(days=DAYS+1),
        "fecha_fin": ahora + timedelta(days=1),
        "activa":True,
    }
)
if productos.get("Matcha Latte"):
    promo_activa.productos_aplicables.add(productos["Matcha Latte"])
if productos.get("Matcha Frío"):
    promo_activa.productos_aplicables.add(productos["Matcha Frío"])
print("  ✓ Promociones (Matcha Lover 10%)")

# ── 6. Generar pedidos diarios ───────────────────────────────────────────────
estados_pedido = ["recibido","preparando","listo","entregado","cancelado"]
pesos_estado   = [0.05, 0.10, 0.15, 0.65, 0.05]  # probabilidades

def hora_aleatoria(dia):
    """Devuelve un datetime en 'dia' entre 08:00 y 22:00."""
    h = random.randint(8,21)
    m = random.randint(0,59)
    return timezone.make_aware(datetime.combine(dia, time(h, m)))

pedidos_creados = 0
for d in range(DAYS):
    dia = (ahora - timedelta(days=d)).date()
    for _ in range(random.randint(8, TICKETS_PER_DAY)):
        mesa = random.choice(mesas)
        alias = random.choice(ALIAS_CLIENTES)
        # Sesión temporal para el pedido
        sesion = SesionCliente.objects.create(
            alias=alias,
            token_cookie=uuid.uuid4().hex,
            estado="activa",
            mesa=mesa,
            modalidad_ingreso=qr
        )
        # Elegir productos al azar
        items = random.sample(list(productos.values()), random.randint(1,4))
        estado = random.choices(estados_pedido, weights=pesos_estado, k=1)[0]
        pedido = Pedido.objects.create(
            sesion=sesion,
            modalidad=qr,
            estado=estado,
            fecha_hora_ingreso=hora_aleatoria(dia),
            empleado_entrega=empleados["maria"] if random.random()<0.5 else empleados["carlos"]
        )
        for prod in items:
            cant = random.randint(1,3)
            subtotal = prod.precio * cant
            # Aplica promoción si es Matcha Latte/Frío y random 30%
            promo_aplicada = None
            if prod.nombre in ("Matcha Latte","Matcha Frío") and random.random()<0.3:
                subtotal = (prod.precio * Decimal("0.9")) * cant
                promo_aplicada = promo_activa
            det = DetallePedido.objects.create(
                pedido=pedido,
                producto=prod,
                cantidad=cant,
                subtotal_calculado=subtotal,
                promocion=promo_aplicada,
                notas="" if random.random()<0.8 else random.choice(["sin azúcar","extra caliente","sin hielo"])
            )
            # Agregar modificadores aleatorios (tamaño, leche)
            if prod.nombre in ["Matcha Latte","Matcha Frío","Hojicha Latte","Café Americano","Cappuccino","Latte de Vainilla","Cold Brew","Matcha Puro"]:
                grupos = GrupoModificador.objects.filter(productos=prod)
                for g in grupos:
                    ops = list(g.opciones.all())
                    if ops:
                        op = random.choice(ops)
                        DetalleModificador.objects.create(
                            detalle=det,
                            opcion=op,
                            precio_extra_aplicado=op.precio_extra
                        )
        # Si el estado es "entregado" o "cancelado", cerramos la sesión
        if estado in ("entregado","cancelado"):
            sesion.estado = "pagada" if estado == "entregado" else "cerrada"
            sesion.save()
        pedidos_creados += 1
    print(f"  Día {dia}: generados pedidos")

print(f"  ✓ {pedidos_creados} pedidos generados en {DAYS} días")

# ── 7. Crear algunas solicitudes de pago pendientes ─────────────────────────
mesas_activas = Mesa.objects.filter(sesiones__estado="activa").distinct()[:4]
for mesa in mesas_activas:
    sesion_activa = mesa.sesiones.filter(estado="activa").first()
    if sesion_activa:
        SolicitudPago.objects.get_or_create(
            sesion=sesion_activa,
            estado_solicitud=est_pendiente,
            defaults={
                "tipo":"individual",
                "mesa":mesa,
                "total_individual":Decimal("120.00"),
                "total_mesa":Decimal("250.00"),
                "propina_sugerida":Decimal("12.00")
            }
        )
print("  ✓ Solicitudes de pago de ejemplo")

# ── 8. Ajustar estados reales de mesas ───────────────────────────────────────
for mesa in mesas:
    activas = mesa.sesiones.filter(estado="activa").count()
    mesa.estado = "ocupada" if activas > 0 else "libre"
    if activas > 0 and not mesa.pin_actual:
        mesa.pin_actual = str(random.randint(1000,9999))
    mesa.save()
print("  ✓ Estados de mesas actualizados")

print("\n✅ Seed de 1 mes completado exitosamente.")
print(f"   {pedidos_creados} pedidos creados entre {ahora.date()-timedelta(days=DAYS)} y {ahora.date()}")