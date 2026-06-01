"""
FIX #3 — Agrega PayPal al catálogo de MetodoPago.

Es una migración de datos idempotente: si PayPal ya existe (porque el seed
se corrió primero), no la duplica. Si el seed nunca se corrió, esta migración
deja al menos PayPal disponible en el modal de cobro.
"""
from django.db import migrations


def agregar_paypal(apps, schema_editor):
    MetodoPago = apps.get_model("catalogs", "MetodoPago")
    MetodoPago.objects.get_or_create(descripcion="PayPal")


def quitar_paypal(apps, schema_editor):
    MetodoPago = apps.get_model("catalogs", "MetodoPago")
    MetodoPago.objects.filter(descripcion="PayPal").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(agregar_paypal, quitar_paypal),
    ]
