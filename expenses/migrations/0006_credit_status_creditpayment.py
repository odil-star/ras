from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0005_add_credit_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='credit',
            name='status',
            field=models.CharField(
                choices=[('active', 'Активный'), ('paid_off', 'Погашен')],
                default='active',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='CreditPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount',       models.DecimalField(decimal_places=2, max_digits=15)),
                ('principal',    models.DecimalField(decimal_places=2, max_digits=15)),
                ('interest',     models.DecimalField(decimal_places=2, max_digits=15)),
                ('payment_date', models.DateField()),
                ('note',         models.CharField(blank=True, default='', max_length=255)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('credit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payments',
                    to='expenses.credit',
                )),
            ],
            options={
                'ordering': ['payment_date', 'created_at'],
            },
        ),
    ]
