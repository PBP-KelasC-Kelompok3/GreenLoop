from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('consumer', 'Consumer'),
        ('mitra', 'Mitra'),
        ('courier', 'Courier'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='consumer'
    )

    def __str__(self):
        return self.user.username