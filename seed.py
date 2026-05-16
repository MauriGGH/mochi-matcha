"""
seed.py — Pobla la BD con histórico jun 2025 – fecha actual.
Ejecutar:
    docker compose exec web python manage.py shell -c "exec(open('seed.py').read())"

ADVERTENCIA: elimina todos los pedidos, sesiones y solicitudes de pago previos.
Los productos, categorías, empleados y modificadores se conservan / actualizan.
"""
import os, uuid, random
from decimal import Decimal
from datetime import timedelta, datetime, date, time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()

from django.utils import timezone
from django.db import transaction
from django.db.models.functions import Upper

from apps.catalogs.models import ModalidadIngreso, MetodoPago, EstadoSolicitud
from apps.accounts.models import Empleado
from apps.mesas.models import Mesa, SesionCliente, UbicacionMesa
from apps.menu.models import (
    Categoria, Producto, GrupoModificador, OpcionModificador,
    Promocion, TipoDescuento,
)
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador, SolicitudPago
from apps.mesas.models import AlertaMesero

# ── Parámetros ────────────────────────────────────────────────────────────────
FECHA_INICIO     = date(2025, 6, 1)
FECHA_FIN        = timezone.now().date()
TICKETS_BASE     = 12   # pedidos en día normal
TICKETS_FINDE    = 20   # pedidos en viernes-domingo

# Demostración "en vivo" del día actual.
# Por defecto el seed deja la app SOLO con histórico (pedidos entregados o
# cancelados, mesas libres, sin sesiones activas ni cobros pendientes). Si
# quieres dejar también unos registros vivos para demostrar el KDS / mesero
# / cobro, súbelos manualmente — pero ten en cuenta que generarán alertas
# y mesas ocupadas en el panel apenas se cargue.
DEMO_PEDIDOS_EN_VIVO = 0   # pedidos activos hoy en el KDS (recibido/preparando/listo)
DEMO_MESAS_OCUPADAS  = 0   # mesas con sesión activa + solicitud de cobro pendiente

ALIAS_CLIENTES = [
    "SOFÍA","DIEGO","VALERIA","MATEO","EMILIO","LUNA","JOAQUÍN","RENATA",
    "GAEL","CAMILA","IKER","NAOMI","LUKA","ZOE","MAX","MÍA","ANA","CARLOS",
    "MIGUEL","DANIELA","FERNANDA","RODRIGO","PAOLA","ALEJANDRO","ISABELLA",
    "SEBASTIÁN","MARIANA","ANDRÉS","GABRIELA","HUGO",
]
NOTAS_POSIBLES = [
    "SIN AZÚCAR", "EXTRA CALIENTE", "SIN HIELO", "POCO AZÚCAR",
    "TEMPERATURA MEDIA", "SIN LACTOSA", "EXTRA SHOT", "MUY CALIENTE",
    "LECHE AL VAPOR", "SIN CANELA",
]
MOTIVOS_CANCELACION = [
    "CLIENTE CANCELÓ", "PRODUCTO AGOTADO", "ERROR EN LA COMANDA",
    "DEMORA EXCESIVA", "MESA SE RETIRÓ ANTES",
]

ahora = timezone.now()
print("🌱 Seed histórico jun 2025 – hoy")
print(f"   Rango: {FECHA_INICIO} → {FECHA_FIN}")

# ── 1. Normalizar texto existente a mayúsculas ────────────────────────────────
print("\n[1/10] Normalizando datos existentes a mayúsculas...")
Categoria.objects.update(nombre=Upper('nombre'))
Producto.objects.update(nombre=Upper('nombre'), descripcion=Upper('descripcion'))
GrupoModificador.objects.update(nombre_grupo=Upper('nombre_grupo'))
OpcionModificador.objects.update(nombre_opcion=Upper('nombre_opcion'))
UbicacionMesa.objects.update(nombre=Upper('nombre'))
Promocion.objects.update(titulo=Upper('titulo'))
for emp in Empleado.objects.exclude(nombre=""):
    Empleado.objects.filter(pk=emp.pk).update(nombre=emp.nombre.upper())
print("  ✓ Mayúsculas aplicadas")

# ── 2. Limpiar histórico transaccional ────────────────────────────────────────
print("\n[2/10] Limpiando histórico previo...")
import time as _time_mod
# Se borra en orden de dependencia de FK: SolicitudPago, DetalleModificador y
# DetallePedido referencian a Pedido; Pedido.sesion referencia (PROTECT) a
# SesionCliente. Si la app está corriendo y crea un pedido nuevo entre dos
# DELETE consecutivos, el barrido falla con IntegrityError/ProtectedError.
# Por eso TODO el barrido va dentro del try y se reintenta el ciclo completo.
# Recomendado: detener la app (docker compose stop web) antes de sembrar.
for _intento in range(6):
    try:
        SolicitudPago.objects.all().delete()
        DetalleModificador.objects.all().delete()
        DetallePedido.objects.all().delete()
        Pedido.objects.all().delete()
        # AlertaMesero referencia a SesionCliente y Mesa; borrarlo antes evita
        # que queden alertas vivas en el panel del mesero tras el seed.
        AlertaMesero.objects.all().delete()
        SesionCliente.objects.all().delete()
        break
    except Exception:
        if _intento == 5:
            raise
        _time_mod.sleep(0.5)   # dejar pasar la carrera y reintentar el barrido
print("  ✓ Histórico eliminado")

# ── 3. Catálogos ──────────────────────────────────────────────────────────────
print("\n[3/10] Catálogos...")
qr,       _ = ModalidadIngreso.objects.get_or_create(descripcion="qr")
asistido, _ = ModalidadIngreso.objects.get_or_create(descripcion="asistido")
efectivo, _ = MetodoPago.objects.get_or_create(descripcion="Efectivo")
tarjeta,  _ = MetodoPago.objects.get_or_create(descripcion="Tarjeta")
mixto,    _ = MetodoPago.objects.get_or_create(descripcion="Mixto")
est_pend, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")
est_proc, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
est_canc, _ = EstadoSolicitud.objects.get_or_create(descripcion="cancelada")
print("  ✓ OK")

# ── 4. Empleados ──────────────────────────────────────────────────────────────
print("\n[4/10] Empleados...")
if not Empleado.objects.filter(usuario="admin").exists():
    Empleado.objects.create_superuser(password="admin1234", usuario="admin", nombre="ADMINISTRADOR")

empleados = {}
for usr, nombre, rol, pw in [
    ("maria",    "MARÍA LÓPEZ",    "mesero",  "mesero123"),
    ("carlos",   "CARLOS RUIZ",    "mesero",  "mesero123"),
    ("lucia",    "LUCÍA MENDOZA",  "cocina",  "cocina123"),
    ("roberto",  "ROBERTO SOTO",   "cocina",  "cocina123"),
    ("gerente1", "ANA MARTÍNEZ",   "gerente", "gerente123"),
]:
    emp, created = Empleado.objects.get_or_create(
        usuario=usr,
        defaults={"nombre": nombre, "rol": rol, "activo": True,
                  "is_staff": rol in ("admin", "gerente")},
    )
    if created:
        emp.set_password(pw)
        emp.save()
    else:
        Empleado.objects.filter(pk=emp.pk).update(nombre=nombre)
    empleados[usr] = emp
print("  ✓ OK")

# ── 5. Ubicaciones y mesas ────────────────────────────────────────────────────
print("\n[5/10] Ubicaciones y mesas...")
ubicaciones = {}
for nombre in ["TERRAZA", "INTERIOR", "BARRA", "SALÓN PRIVADO"]:
    obj, _ = UbicacionMesa.objects.get_or_create(nombre=nombre)
    ubicaciones[nombre] = obj

mesas = []
for num, cap, ubic in [
    (1,4,"TERRAZA"),(2,2,"TERRAZA"),(3,6,"INTERIOR"),(4,4,"INTERIOR"),
    (5,2,"BARRA"),(6,4,"BARRA"),(7,8,"SALÓN PRIVADO"),(8,4,"INTERIOR"),
]:
    mesa, _ = Mesa.objects.get_or_create(
        numero_mesa=num,
        defaults={
            "capacidad": cap,
            "ubicacion": ubicaciones[ubic],
            "codigo_qr": f"QR-MESA-{num:03d}",
            "estado": "libre",
            "id_mesero_asignado": empleados["maria"] if num <= 4 else empleados["carlos"],
        },
    )
    mesas.append(mesa)
print("  ✓ OK")

# ── 6. Menú: categorías y productos ──────────────────────────────────────────
print("\n[6/10] Menú...")
cat_matcha,  _ = Categoria.objects.get_or_create(nombre="MATCHA",    defaults={"orden":1,"area":"bar"})
cat_cafe,    _ = Categoria.objects.get_or_create(nombre="CAFÉ",      defaults={"orden":2,"area":"bar"})
cat_mochi,   _ = Categoria.objects.get_or_create(nombre="MOCHI",     defaults={"orden":3,"area":"cocina"})
cat_postres, _ = Categoria.objects.get_or_create(nombre="POSTRES",   defaults={"orden":4,"area":"cocina"})
cat_snacks,  _ = Categoria.objects.get_or_create(nombre="SNACKS",    defaults={"orden":5,"area":"cocina"})
cat_esp,     _ = Categoria.objects.get_or_create(nombre="ESPECIALES",defaults={"orden":6,"area":"ambos"})

prod_datos = [
    ("MATCHA LATTE",         "MATCHA CEREMONIAL CON LECHE DE AVENA",       65,  cat_matcha,  "matchalatte.jpg"),
    ("MATCHA FRÍO",          "MATCHA CON LECHE FRÍA Y HIELO",               70,  cat_matcha,  "matchafrio.png"),
    ("MATCHA PURO",          "MATCHA CEREMONIAL SIN AZÚCAR",                55,  cat_matcha,  "matchaceremonial.png"),
    ("HOCHICHA",             "TÉ TOSTADO JAPONÉS CON LECHE",                60,  cat_matcha,  "hochija.png"),
    ("CAFÉ AMERICANO",       "ESPRESSO DOBLE CON AGUA CALIENTE",            45,  cat_cafe,    "americano.png"),
    ("CAPPUCCINO",           "ESPRESSO CON LECHE VAPORIZADA",               55,  cat_cafe,    "capuccinoexpresso.png"),
    ("LATTE DE VAINILLA",    "ESPRESSO, LECHE Y VAINILLA NATURAL",          60,  cat_cafe,    "latevainilla.jpeg"),
    ("COLD BREW",            "CAFÉ EN FRÍO 12 HORAS",                       65,  cat_cafe,    "coldbrew.png"),
    ("MOCHI DE FRESA",       "MOCHI RELLENO DE HELADO DE FRESA",            45,  cat_mochi,   "mochifresa.jpeg"),
    ("MOCHI DE MATCHA",      "MOCHI RELLENO DE CREMA DE MATCHA",            45,  cat_mochi,   "mochimatcha.jpeg"),
    ("MOCHI DE MANGO",       "MOCHI RELLENO DE HELADO DE MANGO",            45,  cat_mochi,   "mochi-helado-de-mango.jpg"),
    ("MOCHI TRIO",           "3 MOCHIS A ELECCIÓN",                         120, cat_mochi,   "3mochi.jpeg"),
    ("BROWNIE",              "BROWNIE DE CHOCOLATE BELGA CON NUEZ",         50,  cat_postres, "brownie.jpg"),
    ("CHOCOLATE ABUELITA",   "CHOCOLATE ESPESO ESTILO TRADICIONAL",         55,  cat_postres, "chocolateabuelita.jpeg"),
    ("WAFFLE JAPONÉS",       "WAFFLE ESTILO MOCHI CON FRUTOS ROJOS",        80,  cat_postres, "wafflejapones.jpg"),
    ("PAY DE MATCHA",        "PAY HORNEADO CON MATCHA PREMIUM",             75,  cat_postres, "pay matcha.png"),
    ("EDAMAME",              "EDAMAME AL VAPOR CON SAL DE MAR",             40,  cat_snacks,  "onigiri.jpeg"),
    ("ONIGIRI ATÚN",         "ARROZ JAPONÉS RELLENO DE ATÚN",               55,  cat_snacks,  "onigiri.jpeg"),
    ("COMBO MATCHA+MOCHI",   "MATCHA LATTE + MOCHI A ELECCIÓN",             100, cat_esp,     "mochimatcha.jpeg"),
]
productos = {}
for nombre, desc, precio, cat, imagen in prod_datos:
    p, _ = Producto.objects.get_or_create(
        nombre=nombre,
        defaults={
            "descripcion": desc,
            "precio": Decimal(str(precio)),
            "categoria": cat,
            "disponible": True,
            "imagen_url": f"/media/images/{imagen}",
        },
    )
    productos[nombre] = p
print(f"  ✓ {len(productos)} productos")

# ── 7. Modificadores ──────────────────────────────────────────────────────────
print("\n[7/10] Modificadores...")

def add_grupo(producto, nombre_grupo, tipo, obligatorio, max_sel, opciones):
    g, _ = GrupoModificador.objects.get_or_create(
        nombre_grupo=nombre_grupo,
        defaults={"tipo": tipo, "es_obligatorio": obligatorio, "max_selecciones": max_sel},
    )
    g.productos.add(producto)
    for nom_op, extra in opciones:
        OpcionModificador.objects.get_or_create(
            grupo=g, nombre_opcion=nom_op,
            defaults={"precio_extra": Decimal(str(extra))},
        )

TAMANO_OPCIONES = [("CHICO (250ML)", 0), ("MEDIANO (350ML)", 10), ("GRANDE (450ML)", 20)]
LECHE_OPCIONES  = [("ENTERA", 0), ("AVENA", 10), ("ALMENDRA", 10), ("DESLACTOSADA", 0)]
TEMP_OPCIONES   = [("CALIENTE", 0), ("FRÍO", 0)]

bebidas_leche = ["MATCHA LATTE","HOCHICHA","CAPPUCCINO","LATTE DE VAINILLA","MATCHA FRÍO"]
bebidas_temp  = ["MATCHA LATTE","HOCHICHA","CAFÉ AMERICANO","CAPPUCCINO","LATTE DE VAINILLA"]
bebidas_todas = bebidas_leche + ["MATCHA PURO","CAFÉ AMERICANO","COLD BREW"]

for key in bebidas_todas:
    if key not in productos: continue
    add_grupo(productos[key], "TAMAÑO", "única", True, None, TAMANO_OPCIONES)
    if key in bebidas_leche:
        add_grupo(productos[key], "TIPO DE LECHE", "única", False, None, LECHE_OPCIONES)
    if key in bebidas_temp:
        add_grupo(productos[key], "TEMPERATURA", "única", True, None, TEMP_OPCIONES)
print("  ✓ OK")

# ── 8. Promociones ────────────────────────────────────────────────────────────
print("\n[8/10] Promociones...")
tipos_desc = {
    k: TipoDescuento.objects.get_or_create(descripcion=v)[0]
    for k, v in [
        ("pct", "Porcentaje"), ("2x1", "2x1"),
        ("fijo", "Monto fijo"), ("combo", "Combo precio fijo"), ("llevax", "Lleva X paga Y"),
    ]
}
fecha_promo_ini = ahora - timedelta(days=400)
fecha_promo_fin = ahora + timedelta(days=365)

def upsert_promo(titulo, tipo_key, valor, aplicacion, desc_corta, orden):
    promo, _ = Promocion.objects.get_or_create(
        titulo=titulo,
        defaults={
            "tipo_descuento": tipos_desc[tipo_key],
            "valor_descuento": Decimal(str(valor)),
            "aplicacion": aplicacion,
            "fecha_inicio": fecha_promo_ini,
            "fecha_fin": fecha_promo_fin,
            "activa": True,
            # imagen_url vacío → el carrusel cae a la imagen del producto asociado
            "imagen_url": "",
            "descripcion_corta": desc_corta,
            "orden": orden,
        },
    )
    # Si la promo ya existía con banner genérico, lo limpiamos
    if promo.imagen_url and "banner" in promo.imagen_url.lower():
        promo.imagen_url = ""
        promo.save(update_fields=["imagen_url"])
    return promo

promo_matcha = upsert_promo("MATCHA LOVER 10%",        "pct",  10, "item",  "10% DE DESCUENTO EN MATCHAS",        1)
promo_2x1    = upsert_promo("2×1 EN MOCHIS",           "2x1",   0, "item",  "COMPRA 2 MOCHIS Y PAGA 1",           2)
promo_combo  = upsert_promo("COMBO MATCHA+POSTRE 15%", "pct",  15, "item",  "MATCHA + POSTRE CON 15% DESCUENTO",  3)
promo_cafe   = upsert_promo("DESCUENTO CAFÉ 20%",      "pct",  20, "item",  "20% OFF EN CAFÉS PREMIUM",           4)

for n in ["MATCHA LATTE","MATCHA FRÍO"]:
    if n in productos: promo_matcha.productos_aplicables.add(productos[n])
for n in ["MOCHI DE FRESA","MOCHI DE MATCHA","MOCHI DE MANGO"]:
    if n in productos: promo_2x1.productos_aplicables.add(productos[n])
# Combo: aplicables = matchas (condición disparadora), beneficiados = postres
# (productos con descuento). Elegible cuando el carrito tiene ≥1 de cada grupo.
promo_combo.productos_aplicables.clear()
promo_combo.productos_beneficiados.clear()
for n in ["MATCHA LATTE","MATCHA FRÍO"]:
    if n in productos: promo_combo.productos_aplicables.add(productos[n])
for n in ["BROWNIE","WAFFLE JAPONÉS","PAY DE MATCHA"]:
    if n in productos: promo_combo.productos_beneficiados.add(productos[n])
promo_combo.requiere_todos_productos = False
promo_combo.save(update_fields=["requiere_todos_productos"])
for n in ["CAPPUCCINO","LATTE DE VAINILLA","COLD BREW","CAFÉ AMERICANO"]:
    if n in productos: promo_cafe.productos_aplicables.add(productos[n])
print("  ✓ OK")

# ── 9. Generar histórico de pedidos (100% cerrado) ───────────────────────────
print("\n[9/10] Generando histórico de pedidos...")

# Regla de diseño: TODO el histórico — incluido el día de hoy — queda en estado
# terminal (entregado / cancelado) con fechas COHERENTES:
#   · entregado → tiene fecha_hora_ingreso Y fecha_hora_entrega (tiempo de
#     preparación realista de 4–22 min) + SolicitudPago procesada. Esto hace que
#     el reporte de "tiempo de atención" tenga datos reales en lugar de salir
#     vacío, y que nada quede pendiente de cobro.
#   · cancelado → con motivo; sesión cerrada.
# Los únicos pedidos en estados activos se crean aparte en el paso 10, con
# tiempos recientes — así el KDS nunca muestra pedidos de "hace miles de minutos".
estados_historico = ["entregado", "cancelado"]
pesos_historico   = [0.94, 0.06]
metodos_pago      = [efectivo, tarjeta, mixto]
pesos_metodo      = [0.55, 0.35, 0.10]

# mapa producto → (promo, factor_precio)
promos_map = {
    "MATCHA LATTE":      (promo_matcha, Decimal("0.90")),
    "MATCHA FRÍO":       (promo_matcha, Decimal("0.90")),
    "CAPPUCCINO":        (promo_cafe,   Decimal("0.80")),
    "LATTE DE VAINILLA": (promo_cafe,   Decimal("0.80")),
    "COLD BREW":         (promo_cafe,   Decimal("0.80")),
    "CAFÉ AMERICANO":    (promo_cafe,   Decimal("0.80")),
    "BROWNIE":           (promo_combo,  Decimal("0.85")),
    "WAFFLE JAPONÉS":    (promo_combo,  Decimal("0.85")),
    "PAY DE MATCHA":     (promo_combo,  Decimal("0.85")),
}

# Pre-cargar grupos de modificadores por producto
grupos_por_producto = {}
for key in bebidas_todas:
    if key in productos:
        grupos_por_producto[key] = list(
            GrupoModificador.objects.filter(productos=productos[key]).prefetch_related("opciones")
        )


def momento_aleatorio(d: date) -> datetime:
    """Datetime aleatorio dentro del horario de operación (08:00–21:00).
    Para el día actual nunca devuelve una hora futura."""
    inicio = timezone.make_aware(datetime.combine(d, time(8, 0, 0)))
    fin = ahora if d == FECHA_FIN else timezone.make_aware(datetime.combine(d, time(21, 0, 0)))
    if fin <= inicio:
        fin = inicio + timedelta(minutes=30)
    return inicio + timedelta(seconds=random.uniform(0, (fin - inicio).total_seconds()))


def crear_detalles(pedido, items, marcar_listos):
    """Crea los DetallePedido (+ modificadores) de un pedido y devuelve el total.

    marcar_listos: True para pedidos ya terminados (entregado/listo) — sus ítems
    quedan con listo=True; False para pedidos aún en preparación."""
    total = Decimal("0")
    for prod in items:
        cant     = random.randint(1, 3)
        subtotal = prod.precio * cant
        promo_ap = None
        if prod.nombre in promos_map and random.random() < 0.28:
            promo_obj, factor = promos_map[prod.nombre]
            subtotal = (prod.precio * factor * cant).quantize(Decimal("0.01"))
            promo_ap = promo_obj
        nota = random.choice(NOTAS_POSIBLES) if random.random() < 0.22 else ""
        det  = DetallePedido.objects.create(
            pedido=pedido, producto=prod, cantidad=cant,
            subtotal_calculado=subtotal, promocion=promo_ap, notas=nota,
            listo=marcar_listos,
        )
        total += subtotal
        for g in grupos_por_producto.get(prod.nombre, []):
            ops = list(g.opciones.all())
            if ops:
                op = random.choice(ops)
                DetalleModificador.objects.create(
                    detalle=det, opcion=op,
                    precio_extra_aplicado=op.precio_extra,
                    nombre_opcion_historico=op.nombre_opcion,
                )
    return total


# El histórico se genera con operaciones MASIVAS (bulk_create/bulk_update) dentro
# de UNA sola transacción. Antes se hacía un INSERT/UPDATE por registro (~30 000
# queries para ~3 500 pedidos), lo que tardaba minutos: en un entorno Docker
# inestable la conexión se perdía a mitad. Con bulk son ~15 queries y termina en
# segundos. Los campos auto_now_add (fecha_inicio, fecha_hora_ingreso,
# fecha_hora) se corrigen después con bulk_update porque bulk_create los ignora.
total_dias  = (FECHA_FIN - FECHA_INICIO).days + 1
lista_prods = list(productos.values())
BATCH       = 500

# ── Fase A: armar TODO el plan en memoria (sin tocar la BD) ──────────────────
print("  → Planificando pedidos...")
plan = []   # un dict por pedido con todos sus datos ya calculados
for idx in range(total_dias):
    dia = FECHA_INICIO + timedelta(days=idx)
    es_finde = dia.weekday() >= 4   # vie, sáb, dom
    n_pedidos = random.randint(14, TICKETS_FINDE) if es_finde else random.randint(7, TICKETS_BASE)

    for _ in range(n_pedidos):
        estado     = random.choices(estados_historico, weights=pesos_historico, k=1)[0]
        fecha_hora = momento_aleatorio(dia)

        # Ítems: (producto, cantidad, subtotal, promo, nota, [opciones_modificador])
        items_plan = []
        total      = Decimal("0")
        for prod in random.sample(lista_prods, random.randint(1, 4)):
            cant     = random.randint(1, 3)
            subtotal = prod.precio * cant
            promo_ap = None
            if prod.nombre in promos_map and random.random() < 0.28:
                promo_obj, factor = promos_map[prod.nombre]
                subtotal = (prod.precio * factor * cant).quantize(Decimal("0.01"))
                promo_ap = promo_obj
            nota = random.choice(NOTAS_POSIBLES) if random.random() < 0.22 else ""
            mods = []
            for g in grupos_por_producto.get(prod.nombre, []):
                ops = list(g.opciones.all())
                if ops:
                    mods.append(random.choice(ops))
            items_plan.append((prod, cant, subtotal, promo_ap, nota, mods))
            total += subtotal

        registro = {
            "mesa":       random.choice(mesas),
            "alias":      random.choice(ALIAS_CLIENTES),   # ya en MAYÚSCULAS
            "fecha_hora": fecha_hora,
            "estado":     estado,
            "mesero":     random.choice([empleados["maria"], empleados["carlos"]]),
            "items":      items_plan,
            "total":      total,
        }
        if estado == "entregado":
            # Tiempos coherentes; nunca en el futuro.
            registro["entrega"] = min(fecha_hora + timedelta(minutes=random.randint(4, 22)), ahora)
            registro["cobro"]   = min(registro["entrega"] + timedelta(minutes=random.randint(2, 15)), ahora)
            registro["metodo"]  = random.choices(metodos_pago, weights=pesos_metodo, k=1)[0]
        else:  # cancelado
            registro["motivo"]  = random.choice(MOTIVOS_CANCELACION)   # ya en MAYÚSCULAS
        plan.append(registro)

pedidos_creados = len(plan)
print(f"  → {pedidos_creados} pedidos planificados; insertando en bloque...")

# ── Fase B: inserción por LOTES con commit progresivo ────────────────────────
# Se inserta en bloques de LOTE_PEDIDOS, cada bloque en su propia transacción.
# Esto: (1) acota la memoria — no se acumulan decenas de miles de objetos Django
# a la vez, evitando que Docker mate el proceso por falta de RAM (OOM); (2) si el
# entorno corta el proceso a mitad, lo ya commiteado se conserva — al re-ejecutar
# el seed, la limpieza del paso 2 borra lo parcial y vuelve a empezar.
LOTE_PEDIDOS = 400
for inicio in range(0, len(plan), LOTE_PEDIDOS):
    lote = plan[inicio:inicio + LOTE_PEDIDOS]
    with transaction.atomic():
        # 1) Sesiones — bulk_create ignora auto_now_add y save() (el alias ya
        #    viene en mayúsculas); fecha_inicio y estado se corrigen con bulk_update.
        sesiones = [
            SesionCliente(alias=r["alias"], token_cookie=uuid.uuid4().hex,
                          estado="activa", mesa=r["mesa"], modalidad_ingreso=qr)
            for r in lote
        ]
        SesionCliente.objects.bulk_create(sesiones, batch_size=BATCH)
        for r, s in zip(lote, sesiones):
            r["_sesion"]   = s
            s.fecha_inicio = r["fecha_hora"]
            s.estado       = "pagada" if r["estado"] == "entregado" else "cerrada"
        SesionCliente.objects.bulk_update(sesiones, ["fecha_inicio", "estado"], batch_size=BATCH)

        # 2) Pedidos
        pedidos = [
            Pedido(sesion=r["_sesion"], modalidad=qr, estado=r["estado"],
                   empleado_entrega=r["mesero"])
            for r in lote
        ]
        Pedido.objects.bulk_create(pedidos, batch_size=BATCH)
        for r, p in zip(lote, pedidos):
            r["_pedido"]         = p
            p.fecha_hora_ingreso = r["fecha_hora"]
            if r["estado"] == "entregado":
                p.fecha_hora_entrega = r["entrega"]
            else:
                p.motivo_cancelacion = r["motivo"]
        Pedido.objects.bulk_update(
            pedidos, ["fecha_hora_ingreso", "fecha_hora_entrega", "motivo_cancelacion"],
            batch_size=BATCH,
        )

        # 3) DetallePedido — notas ya en mayúsculas; listo=True si se entregó.
        detalles = []
        for r in lote:
            marcar = (r["estado"] == "entregado")
            for (prod, cant, subtotal, promo_ap, nota, mods) in r["items"]:
                d = DetallePedido(
                    pedido=r["_pedido"], producto=prod, cantidad=cant,
                    subtotal_calculado=subtotal, promocion=promo_ap, notas=nota,
                    listo=marcar,
                )
                d._mods = mods   # se usa en el paso 4
                detalles.append(d)
        DetallePedido.objects.bulk_create(detalles, batch_size=BATCH)

        # 4) DetalleModificador — snapshot histórico del nombre de la opción.
        modificadores = [
            DetalleModificador(
                detalle=d, opcion=op,
                precio_extra_aplicado=op.precio_extra,
                nombre_opcion_historico=op.nombre_opcion,
            )
            for d in detalles for op in d._mods
        ]
        if modificadores:
            DetalleModificador.objects.bulk_create(modificadores, batch_size=BATCH)

        # 5) SolicitudPago de los pedidos entregados. Todas son individuales y con
        #    sesión poblada → el ticket las reconstruye vía el fallback sol.sesion,
        #    sin necesitar el M2M sesiones_cubiertas (que no admite bulk).
        solicitudes = []
        for r in lote:
            if r["estado"] != "entregado":
                continue
            total     = r["total"]
            metodo    = r["metodo"]
            monto_rec = total + Decimal(str(random.choice([0, 5, 10, 20, 50])))
            sp = SolicitudPago(
                sesion=r["_sesion"], mesa=r["mesa"], tipo="individual",
                total_individual=total, total_mesa=total,
                propina_sugerida=(total * Decimal("0.10")).quantize(Decimal("0.01")),
                metodo_pago=metodo, estado_solicitud=est_proc,
                monto_recibido=monto_rec if metodo == efectivo else None,
                cambio=(monto_rec - total) if metodo == efectivo else None,
                detalle_pago=f"PAGO {metodo.descripcion.upper()} - ${total}",
            )
            r["_sp"] = sp
            solicitudes.append(sp)
        if solicitudes:
            SolicitudPago.objects.bulk_create(solicitudes, batch_size=BATCH)
            for r in lote:
                if r["estado"] == "entregado":
                    r["_sp"].fecha_hora = r["cobro"]
            SolicitudPago.objects.bulk_update(solicitudes, ["fecha_hora"], batch_size=BATCH)

    print(f"  → {min(inicio + LOTE_PEDIDOS, len(plan))}/{len(plan)} pedidos insertados")

print(f"  ✓ {pedidos_creados} pedidos históricos en {total_dias} días (todos cerrados)")

# ── 10. Demostración "en vivo" del día actual ────────────────────────────────
print("\n[10/10] Datos de demostración en vivo...")
# Reset completo: además de libre + sin PIN, limpiar la `nota_cierre` (1.1)
# para que el mapa del mesero arranque sin banners amarillos heredados.
Mesa.objects.update(estado="libre", pin_actual=None, nota_cierre="")

# 10a. Pedidos activos en el KDS con tiempos RECIENTES y coherentes con su estado:
#      recibido → ingresó hace 1-6 min · preparando → 7-15 min · listo → 16-28 min.
#      Así el semáforo del KDS muestra verde/amarillo/rojo de forma realista.
plan_vivo = (
    [("recibido",    1,  6, False)] * 2 +
    [("preparando",  7, 15, False)] * 2 +
    [("listo",      16, 28, True)]  * 2
)
random.shuffle(plan_vivo)
demo_alias = random.sample(ALIAS_CLIENTES, min(max(DEMO_PEDIDOS_EN_VIVO, 1), len(ALIAS_CLIENTES)))
for i in range(DEMO_PEDIDOS_EN_VIVO):
    estado, min_lo, min_hi, listos = plan_vivo[i % len(plan_vivo)]
    mesa    = random.choice(mesas)
    alias   = demo_alias[i % len(demo_alias)]
    ingreso = ahora - timedelta(minutes=random.randint(min_lo, min_hi),
                                seconds=random.randint(0, 59))
    with transaction.atomic():
        sesion = SesionCliente.objects.create(
            alias=alias, token_cookie=uuid.uuid4().hex, estado="activa",
            mesa=mesa, modalidad_ingreso=qr,
        )
        SesionCliente.objects.filter(pk=sesion.pk).update(fecha_inicio=ingreso)
        pedido = Pedido.objects.create(sesion=sesion, modalidad=qr, estado=estado)
        items  = random.sample(list(productos.values()), random.randint(1, 3))
        crear_detalles(pedido, items, marcar_listos=listos)
        Pedido.objects.filter(pk=pedido.pk).update(fecha_hora_ingreso=ingreso)
        mesa.estado = "ocupada"
        mesa.save(update_fields=["estado"])
if DEMO_PEDIDOS_EN_VIVO:
    print(f"  ✓ {DEMO_PEDIDOS_EN_VIVO} pedidos activos en el KDS (tiempos recientes)")

# 10b. Mesas con sesión activa y solicitud de cobro PENDIENTE — para demostrar el
#      flujo de cobro del mesero. El total se calcula de un pedido entregado real.
mesas_cobro = random.sample(mesas, min(DEMO_MESAS_OCUPADAS, len(mesas)))
for mesa in mesas_cobro:
    pin     = str(random.randint(1000, 9999))
    alias   = random.choice(ALIAS_CLIENTES)
    ingreso = ahora - timedelta(minutes=random.randint(20, 60))
    with transaction.atomic():
        sesion  = SesionCliente.objects.create(
            alias=alias, token_cookie=uuid.uuid4().hex, estado="activa",
            mesa=mesa, modalidad_ingreso=qr,
        )
        SesionCliente.objects.filter(pk=sesion.pk).update(fecha_inicio=ingreso)
        # Pedido entregado real → el total a cobrar es coherente con su consumo.
        pedido = Pedido.objects.create(sesion=sesion, modalidad=qr, estado="entregado")
        items  = random.sample(list(productos.values()), random.randint(1, 3))
        total_sesion = crear_detalles(pedido, items, marcar_listos=True)
        Pedido.objects.filter(pk=pedido.pk).update(
            fecha_hora_ingreso=ingreso,
            fecha_hora_entrega=min(ingreso + timedelta(minutes=random.randint(5, 18)), ahora),
        )
        SolicitudPago.objects.create(
            sesion=sesion, mesa=mesa, tipo="individual",
            total_individual=total_sesion, total_mesa=total_sesion,
            propina_sugerida=(total_sesion * Decimal("0.10")).quantize(Decimal("0.01")),
            metodo_pago=efectivo, estado_solicitud=est_pend,
        )
        mesa.estado     = "ocupada"
        mesa.pin_actual = pin
        mesa.save(update_fields=["estado", "pin_actual"])
if DEMO_MESAS_OCUPADAS:
    print(f"  ✓ {DEMO_MESAS_OCUPADAS} mesas con cobro pendiente (demo del flujo de cobro)")

print(f"""
✅ Seed completado exitosamente
   Período          : {FECHA_INICIO} → {FECHA_FIN}  ({total_dias} días)
   Pedidos históricos: {pedidos_creados}  (todos entregados/cancelados, con fechas coherentes)
   Demo en vivo      : {DEMO_PEDIDOS_EN_VIVO} pedidos en KDS · {DEMO_MESAS_OCUPADAS} mesas por cobrar
   Productos         : {Producto.objects.count()}
   Empleados         : {Empleado.objects.count()}
""")
