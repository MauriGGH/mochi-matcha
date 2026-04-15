from django.db import migrations

class Migration(migrations.Migration):
    """FIX: Remove unique_together(mesa, alias) to allow alias reuse after sessions close."""

    dependencies = [
        ('mesas', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='sesioncliente',
            unique_together=set(),
        ),
    ]
