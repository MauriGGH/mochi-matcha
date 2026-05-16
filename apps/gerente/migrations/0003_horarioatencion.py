from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gerente", "0002_configuracion_valor_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="HorarioAtencion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dia_semana", models.IntegerField(choices=[
                    (0, "Lunes"), (1, "Martes"), (2, "Miércoles"),
                    (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
                ])),
                ("abre", models.TimeField(help_text="Hora de apertura (formato 24h, ej. 08:00)")),
                ("cierra", models.TimeField(help_text="Hora de cierre (formato 24h, ej. 22:00)")),
                ("activo", models.BooleanField(default=True, help_text="Si está desactivado, este día se considera cerrado.")),
            ],
            options={
                "verbose_name": "Horario de atención",
                "verbose_name_plural": "Horarios de atención",
                "ordering": ["dia_semana", "abre"],
            },
        ),
    ]
