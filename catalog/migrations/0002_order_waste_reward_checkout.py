from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0001_initial'),
        ('waste_reward', '0002_uservoucher_used_order_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='product', name='weight_grams',
            field=models.PositiveIntegerField(default=1000, help_text='Berat produk untuk menghitung ongkir'),
        ),
        migrations.AddField(
            model_name='order', name='product_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='order', name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='order', name='unit_price',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order', name='subtotal',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order', name='shipping_cost',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order', name='goods_discount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order', name='shipping_discount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order', name='recipient_name',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='order', name='phone',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='order', name='address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='order', name='destination_id',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='order', name='courier_code',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='order', name='courier_service',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='order', name='voucher',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='waste_reward.uservoucher'),
        ),
        migrations.AddField(
            model_name='order', name='payment_token',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AlterField(
            model_name='order', name='status',
            field=models.CharField(choices=[('PENDING', 'Menunggu Pembayaran'), ('PAID', 'Dibayar - Sedang Diproses'), ('DELIVERED', 'Terkirim'), ('CANCELLED', 'Dibatalkan')], default='PENDING', max_length=20),
        ),
    ]
