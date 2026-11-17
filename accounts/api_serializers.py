from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from rest_framework import serializers

from courier.forms import PLATE_RE
from courier.models import CourierProfile
from scheduling.forms import MitraProfileForm
from scheduling.models import MitraProfile

from .models import UserProfile


class ProfileUserSerializer(serializers.ModelSerializer):
    """Expose only the non-sensitive User fields used by the profile API."""

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')
        read_only_fields = fields


class MitraProfileReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = MitraProfile
        fields = (
            'business_name',
            'business_type',
            'pic_name',
            'phone_number',
            'operational_hours',
            'courier_notes',
        )
        read_only_fields = fields


class CourierProfileReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierProfile
        fields = ('plate_number', 'vehicle_type')
        read_only_fields = fields


class UserProfileReadSerializer(serializers.ModelSerializer):
    """Read-only representation of a user's profile and associated account."""

    user = ProfileUserSerializer(read_only=True)
    mitra_profile = serializers.SerializerMethodField()
    courier_profile = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ('user', 'role', 'mitra_profile', 'courier_profile')
        read_only_fields = fields

    def get_mitra_profile(self, obj):
        if obj.role != 'mitra':
            return None
        profile = getattr(obj.user, 'profile', None)
        return MitraProfileReadSerializer(profile).data if profile else None

    def get_courier_profile(self, obj):
        if obj.role != 'courier':
            return None
        profile = getattr(obj.user, 'courierprofile', None)
        return CourierProfileReadSerializer(profile).data if profile else None


class UserProfileUpdateSerializer(serializers.Serializer):
    """Update only account and explicitly permitted role-profile fields."""

    username = serializers.CharField(
        max_length=150,
        required=False,
        validators=User._meta.get_field('username').validators,
    )
    email = serializers.EmailField(required=False, allow_blank=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    business_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, allow_null=True,
    )
    business_type = serializers.ChoiceField(
        choices=MitraProfile.JENIS_USAHA_CHOICES,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    pic_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True, allow_null=True,
    )
    phone_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True,
    )
    operational_hours = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True,
    )
    courier_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    plate_number = serializers.CharField(max_length=15, required=False)
    vehicle_type = serializers.ChoiceField(
        choices=CourierProfile.VehicleType.choices,
        required=False,
    )

    COMMON_FIELDS = {'username', 'email', 'first_name', 'last_name'}
    MITRA_FIELDS = {
        'business_name', 'business_type', 'pic_name', 'phone_number',
        'operational_hours', 'courier_notes',
    }
    COURIER_FIELDS = {'plate_number', 'vehicle_type'}

    def to_internal_value(self, data):
        if not hasattr(data, 'keys'):
            return super().to_internal_value(data)

        allowed_fields = set(self.COMMON_FIELDS)
        if self.instance.role == 'mitra':
            allowed_fields.update(self.MITRA_FIELDS)
        elif self.instance.role == 'courier':
            allowed_fields.update(self.COURIER_FIELDS)

        forbidden_fields = set(data.keys()) - allowed_fields
        if forbidden_fields:
            raise serializers.ValidationError({
                field: ['Field ini tidak dapat diubah untuk profil ini.']
                for field in sorted(forbidden_fields)
            })
        return super().to_internal_value(data)

    def validate_username(self, value):
        taken = User.objects.filter(username__iexact=value).exclude(
            pk=self.instance.user_id,
        )
        if taken.exists():
            raise serializers.ValidationError('Username sudah dipakai akun lain.')
        return value

    def validate_email(self, value):
        email = value.strip().lower()
        taken = User.objects.filter(email__iexact=email).exclude(
            pk=self.instance.user_id,
        )
        if taken.exists():
            raise serializers.ValidationError('Email sudah dipakai akun lain.')
        return email

    def validate_plate_number(self, value):
        plate = ' '.join(value.upper().split())
        if not PLATE_RE.fullmatch(plate):
            raise serializers.ValidationError(
                'Format plat nomor tidak valid. Contoh: B 1234 KZT.'
            )
        return plate

    def validate(self, attrs):
        mitra_fields = self.MITRA_FIELDS.intersection(attrs)
        if mitra_fields:
            try:
                profile = self.instance.user.profile
            except ObjectDoesNotExist:
                raise serializers.ValidationError({
                    field: ['Profil Mitra tidak tersedia.']
                    for field in sorted(mitra_fields)
                })

            form_data = {
                field: getattr(profile, field) or ''
                for field in MitraProfileForm.Meta.fields
            }
            form_data.update({field: attrs[field] for field in mitra_fields})
            form = MitraProfileForm(data=form_data, instance=profile)
            if not form.is_valid():
                raise serializers.ValidationError(form.errors)
            self._mitra_form = form

        courier_fields = self.COURIER_FIELDS.intersection(attrs)
        if courier_fields:
            try:
                self._courier_profile = self.instance.user.courierprofile
            except ObjectDoesNotExist:
                raise serializers.ValidationError({
                    field: ['Profil Courier tidak tersedia.']
                    for field in sorted(courier_fields)
                })

        return attrs

    def update(self, instance, validated_data):
        user = instance.user
        user_fields = self.COMMON_FIELDS.intersection(validated_data)
        for field in user_fields:
            setattr(user, field, validated_data[field])
        if user_fields:
            user.save(update_fields=sorted(user_fields))

        mitra_fields = self.MITRA_FIELDS.intersection(validated_data)
        if mitra_fields:
            profile = self._mitra_form.save(commit=False)
            profile.save(update_fields=sorted(mitra_fields))

        courier_fields = self.COURIER_FIELDS.intersection(validated_data)
        if courier_fields:
            profile = self._courier_profile
            for field in courier_fields:
                setattr(profile, field, validated_data[field])
            profile.save(update_fields=sorted(courier_fields))

        return instance
