from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_vouchers(apps, schema_editor):
    RewardVoucher = apps.get_model('waste_reward', 'RewardVoucher')
    vouchers = [
        {
            'code': 'diskon-10000', 'title': 'Diskon', 'kind': 'discount',
            'value_label': 'Rp 10.000', 'points_cost': 200,
            'description': 'Diskon untuk belanja produk GreenLoop.', 'sort_order': 1,
        },
        {
            'code': 'diskon-25000', 'title': 'Diskon', 'kind': 'discount',
            'value_label': 'Rp 25.000', 'points_cost': 450,
            'description': 'Diskon untuk belanja produk GreenLoop.', 'sort_order': 2,
        },
        {
            'code': 'gratis-ongkir', 'title': 'Gratis Ongkir', 'kind': 'shipping',
            'value_label': 's.d. Rp 15.000', 'points_cost': 300,
            'description': 'Potongan ongkir hingga Rp 15.000.', 'sort_order': 3,
        },
        {
            'code': 'diskon-grosir-b2b', 'title': 'Diskon Grosir B2B', 'kind': 'wholesale',
            'value_label': '15%', 'points_cost': 1000,
            'description': 'Untuk pembelian grosir mitra B2B.', 'sort_order': 4,
        },
    ]
    for voucher in vouchers:
        RewardVoucher.objects.get_or_create(code=voucher['code'], defaults=voucher)


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='RewardVoucher',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=40, unique=True)),
                ('title', models.CharField(max_length=100)),
                ('kind', models.CharField(choices=[('discount', 'Diskon'), ('shipping', 'Gratis ongkir'), ('wholesale', 'Diskon grosir B2B')], max_length=16)),
                ('value_label', models.CharField(max_length=40)),
                ('points_cost', models.PositiveIntegerField()),
                ('description', models.CharField(blank=True, max_length=160)),
                ('valid_days', models.PositiveSmallIntegerField(default=30)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'ordering': ('sort_order', 'points_cost')},
        ),
        migrations.CreateModel(
            name='UserVoucher',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(default='', max_length=16, unique=True)),
                ('points_spent', models.PositiveIntegerField()),
                ('acquired_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='greenloop_vouchers', to=settings.AUTH_USER_MODEL)),
                ('voucher', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='redemptions', to='waste_reward.rewardvoucher')),
            ],
            options={'ordering': ('-acquired_at',)},
        ),
        migrations.CreateModel(
            name='RewardTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('pickup', 'Setoran limbah'), ('redemption', 'Penukaran voucher')], max_length=16)),
                ('points_delta', models.IntegerField()),
                ('balance_after', models.PositiveIntegerField()),
                ('weight_kg', models.DecimalField(blank=True, decimal_places=1, max_digits=8, null=True)),
                ('description', models.CharField(max_length=160)),
                ('source_reference', models.CharField(blank=True, max_length=80, null=True, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reward_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-pk')},
        ),
        migrations.RunPython(create_default_vouchers, migrations.RunPython.noop),
    ]
