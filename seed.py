"""
seed.py — Pobla la base de datos de Mochi Matcha con datos de prueba.
Ejecutar desde la raíz del proyecto:
linux:
    python manage.py shell < seed.py
windows:
    docker-compose exec web python manage.py shell -c "exec(open('seed.py').read())"
"""
import uuid
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

print("🌱 Iniciando seed...")

# ── Catálogos ─────────────────────────────────────────────────────────────────
from apps.catalogs.models import ModalidadIngreso, MetodoPago, EstadoSolicitud

qr,       _ = ModalidadIngreso.objects.get_or_create(descripcion="qr")
asistido, _ = ModalidadIngreso.objects.get_or_create(descripcion="asistido")

efectivo, _ = MetodoPago.objects.get_or_create(descripcion="Efectivo")
tarjeta,  _ = MetodoPago.objects.get_or_create(descripcion="Tarjeta")
mixto,    _ = MetodoPago.objects.get_or_create(descripcion="Mixto")

est_pendiente,  _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")
est_procesada,  _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
est_cancelada,  _ = EstadoSolicitud.objects.get_or_create(descripcion="cancelada")

print("  ✓ Catálogos")

# ── Empleados ─────────────────────────────────────────────────────────────────
from apps.accounts.models import Empleado

admin = Empleado.objects.filter(usuario="admin").first()
if not admin:
    admin = Empleado.objects.create_superuser(password="admin1234", usuario="admin", nombre="Administrador")

empleados_data = [
    ("maria",    "Maria López",    "mesero",  "mesero123"),
    ("carlos",   "Carlos Ruiz",    "mesero",  "mesero123"),
    ("lucia",    "Lucia Mendoza",  "cocina",  "cocina123"),
    ("roberto",  "Roberto Soto",   "cocina",  "cocina123"),
    ("gerente1", "Ana Martínez",   "gerente", "gerente123"),
]
empleados = {}
for usuario, nombre, rol, pw in empleados_data:
    emp, _ = Empleado.objects.get_or_create(
        usuario=usuario,
        defaults={"nombre": nombre, "rol": rol, "activo": True, "is_staff": rol in ("admin","gerente")}
    )
    if _:
        emp.set_password(pw)
        emp.save()
    empleados[usuario] = emp

print("  ✓ Empleados")

# ── Mesas ─────────────────────────────────────────────────────────────────────
from apps.mesas.models import Mesa, SesionCliente

mesas = []
mesas_data = [
    (1, 4, "Terraza"),
    (2, 2, "Terraza"),
    (3, 6, "Interior"),
    (4, 4, "Interior"),
    (5, 2, "Barra"),
    (6, 4, "Barra"),
    (7, 8, "Salón privado"),
    (8, 4, "Interior"),
]
for num, cap, ubic in mesas_data:
    mesa, _ = Mesa.objects.get_or_create(
        numero_mesa=num,
        defaults={
            "capacidad": cap,
            "ubicacion": ubic,
            "codigo_qr": f"QR-MESA-{num:03d}",
            "estado": "libre",
            "id_mesero_asignado": empleados["maria"] if num <= 4 else empleados["carlos"],
        }
    )
    mesas.append(mesa)

print("  ✓ Mesas")

# ── Menú ──────────────────────────────────────────────────────────────────────
from apps.menu.models import (
    Categoria, TipoPromocion, Promocion, Producto,
    PromocionProducto, GrupoModificador, OpcionModificador
)

cat_matcha,   _ = Categoria.objects.get_or_create(nombre="Matcha",       defaults={"orden": 1, "area": "bar"})
cat_cafe,     _ = Categoria.objects.get_or_create(nombre="Café",         defaults={"orden": 2, "area": "bar"})
cat_mochi,    _ = Categoria.objects.get_or_create(nombre="Mochi",        defaults={"orden": 3, "area": "cocina"})
cat_postres,  _ = Categoria.objects.get_or_create(nombre="Postres",      defaults={"orden": 4, "area": "cocina"})
cat_snacks,   _ = Categoria.objects.get_or_create(nombre="Snacks",       defaults={"orden": 5, "area": "cocina"})
cat_especial, _ = Categoria.objects.get_or_create(nombre="Especiales",   defaults={"orden": 6, "area": "ambos"})

print("  ✓ Categorías")

# Productos
productos_data = [
    # (nombre, desc, precio, categoria, imagen_url)
    ("Matcha Latte",        "Matcha ceremonial con leche de avena",        65.00, cat_matcha,   None),
    ("Matcha Frío",         "Matcha con leche fría y hielo",               70.00, cat_matcha,   None),
    ("Matcha Puro",         "Matcha ceremonial sin azúcar",                55.00, cat_matcha,   None),
    ("Hojicha Latte",       "Té tostado japonés con leche",                60.00, cat_matcha,   None),
    ("Café Americano",      "Espresso doble con agua caliente",            45.00, cat_cafe,     None),
    ("Cappuccino",          "Espresso con leche vaporizada",               55.00, cat_cafe,     None),
    ("Latte de Vainilla",   "Espresso, leche y vainilla natural",          60.00, cat_cafe,     None),
    ("Cold Brew",           "Café en frío 12 horas, sin filtro",          65.00, cat_cafe,     None),
    ("Mochi de Fresa",      "Mochi relleno de helado de fresa",            45.00, cat_mochi,    None),
    ("Mochi de Matcha",     "Mochi relleno de crema de matcha",           45.00, cat_mochi,    None),
    ("Mochi de Mango",      "Mochi relleno de helado de mango",           45.00, cat_mochi,    None),
    ("Mochi Trio",          "3 mochis a elección",                        120.00, cat_mochi,   None),
    ("Brownie",             "Brownie de chocolate belga con nuez",         50.00, cat_postres,  None),
    ("Cheesecake Matcha",   "Cheesecake horneado con polvo de matcha",     75.00, cat_postres,  None),
    ("Waffle Japonés",      "Waffle estilo mochi con frutos rojos",        80.00, cat_postres,  None),
    ("Edamame",             "Edamame al vapor con sal de mar",             40.00, cat_snacks,   None),
    ("Onigiri Atún",        "Arroz japonés relleno de atún",               55.00, cat_snacks,   None),
    ("Combo Matcha+Mochi",  "Matcha latte + mochi a elección",            100.00, cat_especial, None),
]

productos = {}
for nombre, desc, precio, cat, img in productos_data:
    p, _ = Producto.objects.get_or_create(
        nombre=nombre,
        defaults={"descripcion": desc, "precio": Decimal(str(precio)),
                  "categoria": cat, "disponible": True, "imagen_url": img}
    )
    productos[nombre] = p

print("  ✓ Productos")

# Modificadores
def add_grupo(producto, nombre, tipo, obligatorio, max_sel, opciones):
    g, _ = GrupoModificador.objects.get_or_create(
        producto=producto, nombre_grupo=nombre,
        defaults={"tipo": tipo, "es_obligatorio": obligatorio, "max_selecciones": max_sel}
    )
    for nombre_op, extra in opciones:
        OpcionModificador.objects.get_or_create(
            grupo=g, nombre_opcion=nombre_op,
            defaults={"precio_extra": Decimal(str(extra))}
        )

# Tamaño para bebidas
for key in ["Matcha Latte", "Matcha Frío", "Hojicha Latte", "Café Americano",
            "Cappuccino", "Latte de Vainilla", "Cold Brew", "Matcha Puro"]:
    add_grupo(productos[key], "Tamaño", "única", True, None,
              [("Chico (250 ml)", 0), ("Mediano (350 ml)", 10), ("Grande (450 ml)", 20)])

# Tipo de leche para bebidas con leche
for key in ["Matcha Latte", "Matcha Frío", "Hojicha Latte", "Cappuccino",
            "Latte de Vainilla", "Combo Matcha+Mochi"]:
    add_grupo(productos[key], "Tipo de leche", "única", False, None,
              [("Leche entera", 0), ("Leche de avena", 10),
               ("Leche de almendra", 10), ("Leche deslactosada", 0)])

# Temperatura
for key in ["Matcha Latte", "Hojicha Latte", "Café Americano", "Cappuccino", "Latte de Vainilla"]:
    add_grupo(productos[key], "Temperatura", "única", True, None,
              [("Caliente", 0), ("Frío", 0)])

# Azúcar
for key in ["Matcha Latte", "Matcha Frío", "Hojicha Latte", "Latte de Vainilla"]:
    add_grupo(productos[key], "Nivel de azúcar", "única", False, None,
              [("Sin azúcar", 0), ("Poco dulce", 0), ("Normal", 0), ("Extra dulce", 0)])

# Extras café
add_grupo(productos["Cappuccino"], "Extras", "múltiple", False, 3,
          [("Shot extra", 15), ("Canela", 0), ("Cacao en polvo", 0)])

# Sabor mochi individual
for key in ["Mochi de Fresa", "Mochi de Matcha", "Mochi de Mango"]:
    add_grupo(productos[key], "Temperatura de servicio", "única", False, None,
              [("Normal", 0), ("Extra frío", 0)])

# Trio — elección de 3 sabores
add_grupo(productos["Mochi Trio"], "Sabores (elige 3)", "múltiple", True, 3,
          [("Fresa", 0), ("Matcha", 0), ("Mango", 0), ("Vainilla", 5), ("Chocolate", 5)])

# Waffle extras
add_grupo(productos["Waffle Japonés"], "Toppings", "múltiple", False, 4,
          [("Crema batida", 0), ("Frutos rojos", 0), ("Miel de maple", 10), ("Helado de vainilla", 20)])

# Brownie
add_grupo(productos["Brownie"], "Servir con", "única", False, None,
          [("Solo", 0), ("Con helado de vainilla", 20), ("Con crema batida", 10)])

print("  ✓ Modificadores y opciones")

# Promociones
tipo_desc, _ = TipoPromocion.objects.get_or_create(descripcion="Descuento porcentual")
tipo_combo,_ = TipoPromocion.objects.get_or_create(descripcion="Combo")

ahora = timezone.now()
promo1, _ = Promocion.objects.get_or_create(
    titulo="Happy Hour Matcha",
    defaults={
        "tipo_promocion": tipo_desc,
        "valor": Decimal("15.00"),
        "fecha_inicio": ahora - timedelta(hours=1),
        "fecha_fin": ahora + timedelta(hours=3),
        "activa": True,
        "codigo_cupon": None,
        "limite_usos": None,
    }
)
promo2, _ = Promocion.objects.get_or_create(
    titulo="Combo Fin de Semana",
    defaults={
        "tipo_promocion": tipo_combo,
        "valor": Decimal("20.00"),
        "fecha_inicio": ahora,
        "fecha_fin": ahora + timedelta(days=2),
        "activa": True,
        "codigo_cupon": "FINDE20",
        "limite_usos": 50,
    }
)
PromocionProducto.objects.get_or_create(promocion=promo1, producto=productos["Matcha Latte"])
PromocionProducto.objects.get_or_create(promocion=promo1, producto=productos["Matcha Frío"])
PromocionProducto.objects.get_or_create(promocion=promo2, producto=productos["Combo Matcha+Mochi"])

print("  ✓ Promociones")

# ── Sesiones y pedidos de ejemplo ─────────────────────────────────────────────
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador

mesa_ocupada = mesas[0]  # Mesa 1
mesa_ocupada.pin_actual = "4821"
mesa_ocupada.estado = "ocupada"
mesa_ocupada.save()

sesion1, _ = SesionCliente.objects.get_or_create(
    token_cookie="seed-token-001",
    defaults={
        "alias": "Sofia",
        "estado": "activa",
        "mesa": mesa_ocupada,
        "modalidad_ingreso": qr,
    }
)
sesion2, _ = SesionCliente.objects.get_or_create(
    token_cookie="seed-token-002",
    defaults={
        "alias": "Diego",
        "estado": "activa",
        "mesa": mesa_ocupada,
        "modalidad_ingreso": qr,
    }
)

def crear_pedido(sesion, items):
    """items = [(producto, cantidad, notas, subtotal)]"""
    pedido = Pedido.objects.create(sesion=sesion, modalidad=qr, estado="recibido")
    for prod, cant, notas, subtotal in items:
        DetallePedido.objects.create(
            pedido=pedido, producto=prod, cantidad=cant,
            notas=notas, subtotal_calculado=Decimal(str(subtotal))
        )
    return pedido

crear_pedido(sesion1, [
    (productos["Matcha Latte"],  1, "extra caliente",  65),
    (productos["Mochi de Fresa"], 2, "",              90),
])
crear_pedido(sesion2, [
    (productos["Cold Brew"],    1, "sin hielo",       65),
    (productos["Brownie"],      1, "con helado",      70),
])

print("  ✓ Sesiones y pedidos de ejemplo")
print()
print("✅ Seed completado exitosamente.")
print()
print("Usuarios creados:")
print("  admin     / admin1234   (superusuario)")
print("  maria     / mesero123   (mesero)")
print("  carlos    / mesero123   (mesero)")
print("  lucia     / cocina123   (cocina)")
print("  roberto   / cocina123   (cocina)")
print("  gerente1  / gerente123  (gerente)")
print()
print("Mesa 1 ocupada con PIN 4821 y dos sesiones activas (Sofia, Diego).")
