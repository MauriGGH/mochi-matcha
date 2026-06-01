import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mesas", "0002_remove_unique_together_alias"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertaMesero",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(
                    choices=[("ayuda", "Ayuda"), ("cuenta", "Solicitud de cuenta"), ("personalizado", "Personalizado")],
                    default="ayuda", max_length=15,
                )),
                ("mensaje", models.TextField(blank=True, default="")),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("atendida", models.BooleanField(default=False)),
                ("mesa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alertas", to="mesas.mesa",
                )),
                ("sesion", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="alertas", to="mesas.sesioncliente",
                )),
            ],
            options={
                "verbose_name": "Alerta de mesero",
                "verbose_name_plural": "Alertas de mesero",
                "ordering": ["-fecha_creacion"],
            },
        ),
    ]
