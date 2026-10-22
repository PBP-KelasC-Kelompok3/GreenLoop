import secrets

from django.conf import settings
from django.db import models


class RewardVoucher(models.Model):
    class Kind(models.TextChoices):
        DISCOUNT = 'discount', 'Diskon'
        SHIPPING = 'shipping', 'Gratis ongkir'
        WHOLESALE = 'wholesale', 'Diskon grosir B2B'

    code = models.SlugField(max_length=40, unique=True)
    title = models.CharField(max_length=100)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    value_label = models.CharField(max_length=40)
    points_cost = models.PositiveIntegerField()
    description = models.CharField(max_length=160, blank=True)
    valid_days = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'points_cost')

    def __str__(self):
        return f'{self.title} ({self.points_cost} poin)'


class UserVoucher(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='greenloop_vouchers',
    )
    voucher = models.ForeignKey(
        RewardVoucher,
        on_delete=models.PROTECT,
        related_name='redemptions',
    )
    code = models.CharField(max_length=16, unique=True, default='')
    points_spent = models.PositiveIntegerField()
    acquired_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-acquired_at',)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f'GLV-{secrets.token_hex(3).upper()}'
        super().save(*args, **kwargs)

    @property
    def is_available(self):
        from django.utils import timezone

        return self.used_at is None and self.expires_at > timezone.now()


class RewardTransaction(models.Model):
    class Kind(models.TextChoices):
        PICKUP = 'pickup', 'Setoran limbah'
        REDEMPTION = 'redemption', 'Penukaran voucher'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reward_transactions',
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    points_delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=160)
    source_reference = models.CharField(
        max_length=80,
        unique=True,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')

    def __str__(self):
        return f'{self.user} · {self.points_delta:+d} poin'
