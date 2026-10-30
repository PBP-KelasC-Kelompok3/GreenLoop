from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from accounts.models import UserProfile
from courier.models import CourierAssignment, CourierProfile, PickupRecord, WeightLog
from scheduling.models import MitraProfile, PickupSchedule
from waste_reward.models import RewardVoucher


class Command(BaseCommand):
    help = "Create repeatable demo accounts and operational data for GreenLoop."

    password = "Greenloop123!"
    depok_locations = [
        ("Beji", "Kukusan", -6.3692, 106.8319),
        ("Cimanggis", "Tugu", -6.3656, 106.8613),
        ("Pancoran Mas", "Depok", -6.4025, 106.7942),
        ("Sukmajaya", "Mekarjaya", -6.3864, 106.8381),
        ("Tapos", "Sukatani", -6.4494, 106.8737),
        ("Sawangan", "Bedahan", -6.4238, 106.7637),
        ("Cinere", "Cinere", -6.3334, 106.7842),
        ("Limo", "Grogol", -6.3547, 106.7696),
    ]
    business_types = [
        "Kafe / Coffee Shop",
        "Restoran",
        "Hotel",
        "Katering",
    ]
    time_slots = ["08:00-10:00 WIB", "10:00-12:00 WIB", "13:00-15:00 WIB"]

    def handle(self, *args, **options):
        admin = self.create_user("admin.greenloop", "admin", "Admin GreenLoop")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=["is_staff", "is_superuser"])

        mitras = []
        for index in range(1, 21):
            user = self.create_user(
                f"mitra{index:02d}",
                "mitra",
                f"Mitra GreenLoop {index:02d}",
            )
            location = self.depok_locations[(index - 1) % len(self.depok_locations)]
            kecamatan, kelurahan, latitude, longitude = location
            profile, _ = MitraProfile.objects.update_or_create(
                user=user,
                defaults={
                    "business_name": f"{self.business_types[(index - 1) % 4]} GreenLoop {index:02d}",
                    "business_type": self.business_types[(index - 1) % 4],
                    "pic_name": f"PIC Mitra {index:02d}",
                    "phone_number": f"08123456{index:04d}",
                    "operational_hours": "07:00-21:00",
                    "provinsi": "Jawa Barat",
                    "kota": "Depok",
                    "kecamatan": kecamatan,
                    "kelurahan": kelurahan,
                    "address_detail": f"Jl. GreenLoop No. {index}, {kelurahan}",
                    "latitude": latitude + (index % 4) * 0.0012,
                    "longitude": longitude + (index % 3) * 0.0011,
                    "location_locked": True,
                    "courier_notes": "Limbah organik dipisahkan di area belakang gedung.",
                },
            )
            mitras.append((user, profile))

        couriers = []
        for index in range(1, 11):
            user = self.create_user(
                f"kurir{index:02d}",
                "courier",
                f"Kurir GreenLoop {index:02d}",
            )
            profile, _ = CourierProfile.objects.update_or_create(
                user=user,
                defaults={
                    "plate_number": f"B {1000 + index} GL",
                    "vehicle_type": (
                        CourierProfile.VehicleType.MOTOR_BOX
                        if index % 2
                        else CourierProfile.VehicleType.PICKUP_BAK
                    ),
                    "is_on_duty": index <= 5,
                    "is_approved": True,
                },
            )
            couriers.append((user, profile))

        for index in range(1, 21):
            self.create_user(
                f"konsumen{index:02d}",
                "consumer",
                f"Konsumen GreenLoop {index:02d}",
            )

        today = date.today()
        schedules = []
        for index, (mitra, profile) in enumerate(mitras, start=1):
            courier, courier_profile = couriers[(index - 1) % len(couriers)]
            status = "COMPLETED" if index <= 4 else "SCHEDULED"
            actual_weight = Decimal(str(2 + (index % 8))) if status == "COMPLETED" else None
            schedule, _ = PickupSchedule.objects.update_or_create(
                mitra=mitra,
                notes=f"[SEED] Jadwal demo mitra {index:02d}",
                defaults={
                    "pickup_date": today,
                    "waste_type": [
                        "ORGANIC_FOOD",
                        "COFFEE_GROUNDS",
                        "FRUIT_VEG",
                        "MIXED_ORGANIC",
                    ][(index - 1) % 4],
                    "estimated_weight": 3 + (index % 7),
                    "pickup_time_slot": self.time_slots[(index - 1) % 3],
                    "armada": courier_profile.get_vehicle_type_display(),
                    "status": status,
                    "actual_weight": actual_weight,
                    "points": int(actual_weight * 5) if actual_weight else 0,
                },
            )
            CourierAssignment.objects.update_or_create(
                pickup_schedule=schedule,
                defaults={"courier": courier},
            )
            schedules.append((schedule, courier, mitra, actual_weight))

        for index, (schedule, courier, mitra, actual_weight) in enumerate(schedules[:4], start=1):
            PickupRecord.objects.update_or_create(
                pickup_schedule=schedule,
                defaults={
                    "courier": courier,
                    "code": f"SEED-{index:04d}",
                    "date": today,
                    "slot": schedule.pickup_time_slot,
                    "partner_name": mitra.profile.business_name or mitra.username,
                    "area": mitra.profile.kecamatan or "Depok",
                    "est_kg": int(schedule.estimated_weight),
                    "actual_kg": actual_weight,
                    "vehicle": schedule.armada,
                    "status": PickupRecord.Status.DONE,
                    "note": "Data demo seeder",
                },
            )
            WeightLog.objects.update_or_create(
                pickup_schedule=schedule,
                defaults={
                    "courier": courier,
                    "partner_name": mitra.profile.business_name or mitra.username,
                    "collected_at": today,
                    "weight_kg": actual_weight,
                    "notes": "Data demo seeder",
                },
            )

        vouchers = [
            ("Hemat 10K", "discount", "Rp10.000", 100),
            ("Hemat 25K", "discount", "Rp25.000", 250),
            ("Gratis Ongkir", "shipping", "Gratis ongkir", 150),
            ("Diskon Grosir", "wholesale", "15%", 500),
        ]
        for index, (title, kind, value_label, points_cost) in enumerate(vouchers, start=1):
            RewardVoucher.objects.update_or_create(
                code=f"SEED-VOUCHER-{index}",
                defaults={
                    "title": title,
                    "kind": kind,
                    "value_label": value_label,
                    "points_cost": points_cost,
                    "description": "Voucher demo GreenLoop.",
                    "valid_days": 30,
                    "is_active": True,
                    "sort_order": index,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            "Initial data siap: 1 admin, 20 mitra, 10 kurir, 20 konsumen, "
            "20 jadwal, 4 riwayat pikap, dan 4 voucher."
        ))

    def create_user(self, username, role, full_name):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": full_name,
                "email": f"{username}@greenloop.local",
            },
        )
        if created:
            user.set_password(self.password)
            user.save(update_fields=["password"])
        else:
            changed = []
            if user.first_name != full_name:
                user.first_name = full_name
                changed.append("first_name")
            if not user.email:
                user.email = f"{username}@greenloop.local"
                changed.append("email")
            if changed:
                user.save(update_fields=changed)
        UserProfile.objects.update_or_create(user=user, defaults={"role": role})
        return user