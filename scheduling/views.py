from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import PickupSchedule, MitraProfile
from .forms import PickupScheduleForm
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models import Q
from django.contrib.auth.models import User
from waste_reward.services import award_verified_pickup, get_balance
from courier.models import CourierProfile


def _can_manage_pickups(user):
    profile = getattr(user, 'userprofile', None)
    return bool(
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name='Petugas GreenLoop').exists()
        or (profile and profile.role == 'admin')
    )


@login_required
def mitra_dashboard(request):
    """Dashboard Mitra B2B dengan agregasi statistik, poin, dan grafik dinamis."""
    user_pickups = PickupSchedule.objects.filter(mitra=request.user).order_by('-created_at')
    completed_pickups = user_pickups.filter(status='COMPLETED')

    # 1. Total Limbah Disetor (kg)
    total_waste = (
        completed_pickups.aggregate(Sum('actual_weight'))['actual_weight__sum'] or 0
    )

    # 2. Penjemputan selesai pada bulan berjalan.
    today = timezone.localdate()
    pickups_this_month = completed_pickups.filter(
        pickup_date__year=today.year,
        pickup_date__month=today.month,
    ).count()

    # 3. Estimasi CO2e Dicegah (0.5 kg CO2e per kg limbah)
    co2_saved = round(total_waste * 0.5, 1)

    # Reward ledger is the single source of truth for member points.
    calculated_points = get_balance(request.user)

    # 5. Penjemputan Terdekat
    next_pickup = (
        user_pickups.filter(status__in=['PENDING', 'IN_PROGRESS'])
        .order_by('pickup_date')
        .first()
    )

    # 6. Hitung Stepper Progress Penjemputan Berikutnya
    stepper_progress = 0
    if next_pickup:
        if next_pickup.status == 'PENDING':
            stepper_progress = 25
        elif next_pickup.status == 'IN_PROGRESS':
            stepper_progress = 75
        elif next_pickup.status == 'COMPLETED':
            stepper_progress = 100

    # 7. Logika Tier/Level Membership Dinamis
    if calculated_points < 1000:
        current_tier = 'Bronze'
        next_tier = 'Silver'
        target_points = 1000
    elif calculated_points < 3000:
        current_tier = 'Silver'
        next_tier = 'Gold'
        target_points = 3000
    elif calculated_points < 5000:
        current_tier = 'Gold'
        next_tier = 'Platinum'
        target_points = 5000
    else:
        current_tier = 'Platinum'
        next_tier = 'Max Level'
        target_points = calculated_points

    points_needed = max(0, target_points - calculated_points)
    kg_needed = round(points_needed / 5, 1)
    level_progress_pct = (
        min(100, int((calculated_points / target_points) * 100))
        if target_points > 0
        else 100
    )

    # 8. Agregasi Grafik 8 Minggu Terakhir
    weekly_labels = []
    weekly_data = []

    for i in range(7, -1, -1):
        start_of_week = today - timedelta(days=today.weekday() + (i * 7))
        end_of_week = start_of_week + timedelta(days=6)

        sum_weight = (
            completed_pickups.filter(
                pickup_date__range=[start_of_week, end_of_week]
            ).aggregate(Sum('actual_weight'))['actual_weight__sum'] or 0
        )

        weekly_labels.append(f'M{8-i}')
        weekly_data.append(float(sum_weight))

    context = {
        'pickups': user_pickups,
        'total_waste': total_waste,
        'pickups_this_month': pickups_this_month,
        'co2_saved': co2_saved,
        'user_points': calculated_points,
        'user_points_display': f'{calculated_points:,}'.replace(',', '.'),
        'weekly_labels': json.dumps(weekly_labels),
        'weekly_data': json.dumps(weekly_data),
        'title': 'Dashboard Mitra',
        'next_pickup': next_pickup,
        'stepper_progress': stepper_progress,
        'current_tier': current_tier,
        'next_tier': next_tier,
        'target_points': target_points,
        'target_points_display': f'{target_points:,}'.replace(',', '.'),
        'kg_needed': kg_needed,
        'level_progress_pct': level_progress_pct,
    }
    return render(request, 'scheduling/mitra_dashboard.html', context)


def create_pickup(request):
    if request.method == 'POST':
        form = PickupScheduleForm(request.POST, request.FILES)
        if form.is_valid():
            # Ambil tanggal dan slot waktu yang dipilih user
            pickup_date = form.cleaned_data.get('pickup_date')
            time_slot = form.cleaned_data.get('pickup_time_slot')
            
            # Batas kuota per slot (misalnya maksimal 3 mitra)
            MAX_QUOTA = 3
            existing_count = PickupSchedule.objects.filter(
                pickup_date=pickup_date, 
                pickup_time_slot=time_slot
            ).exclude(status='REJECTED').count()
            
            if existing_count >= MAX_QUOTA:
                messages.error(request, f"Maaf, slot waktu {time_slot} pada tanggal tersebut sudah penuh (maksimal {MAX_QUOTA} mitra). Silakan pilih slot lain.")
            else:
                # Simpan data jika kuota masih tersedia
                pickup = form.save(commit=False)
                pickup.mitra = request.user
                pickup.status = 'PENDING' # Status awal
                pickup.save()
                messages.success(request, "Pengajuan penjemputan berhasil dikirim!")
                return redirect('mitra_dashboard')
    else:
        form = PickupScheduleForm()
        
    context = {
        'form': form,
    }
    return render(request, 'scheduling/create_pickup.html', context)


@login_required
def edit_pickup(request, pickup_id):
  pickup = get_object_or_404(
      PickupSchedule, id=pickup_id, mitra=request.user
  )

  # Keamanan: Jika sudah di-process/acc Admin, tidak boleh di-edit lagi
  if pickup.status != 'PENDING':
    messages.error(
        request, 'Jadwal penjemputan yang sudah diproses tidak dapat diubah.'
    )
    return redirect('mitra_dashboard')

  if request.method == 'POST':
    pickup.pickup_date = request.POST.get('pickup_date')
    pickup.pickup_time_slot = request.POST.get('time_slot')
    pickup.notes = request.POST.get('notes')
    pickup.save()

    messages.success(request, 'Jadwal penjemputan berhasil diperbarui.')
    return redirect('mitra_dashboard')

  return render(request, 'scheduling/edit_pickup.html', {'pickup': pickup})


@login_required
def admin_dashboard(request):
    if not _can_manage_pickups(request.user):
        messages.error(
            request,
            "Anda tidak memiliki hak akses ke Halaman Admin."
        )
        return redirect('home')

    # Ambil kata kunci pencarian dari URL (?q=nama)
    search_query = request.GET.get('q', '')

    all_pickups = PickupSchedule.objects.select_related(
        'mitra'
    ).all().order_by('-created_at')

    # Jika admin mengetik sesuatu di kolom pencarian
    if search_query:
        all_pickups = all_pickups.filter(
            Q(mitra__username__icontains=search_query) |
            Q(mitra__email__icontains=search_query) |
            Q(id__icontains=search_query)
        )

    pending_count = all_pickups.filter(
        status='PENDING'
    ).count()

    in_progress_count = all_pickups.filter(
        status__in=['IN_PROGRESS', 'SCHEDULED']
    ).count()

    completed_count = all_pickups.filter(
        status='COMPLETED'
    ).count()

    context = {
        'all_pickups': all_pickups,
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'search_query': search_query,
    }

    return render(
        request,
        'scheduling/admin_dashboard.html',
        context
    )


def assign_next_courier(pickup):
    """Memilih kurir aktif berikutnya secara bergiliran."""

    couriers = list(
        User.objects.filter(
            is_active=True,
            userprofile__role='courier'
        ).order_by('id')
    )

    if not couriers:
        return None

    last_courier_id = (
        PickupSchedule.objects
        .filter(courier__isnull=False)
        .exclude(id=pickup.id)
        .order_by('-created_at', '-id')
        .values_list('courier_id', flat=True)
        .first()
    )

    if last_courier_id is None:
        return couriers[0]

    for courier in couriers:
        if courier.id > last_courier_id:
            return courier

    return couriers[0]


@login_required
def update_pickup_status(request, pickup_id, new_status=None):
    is_admin = _can_manage_pickups(request.user)

    profile = getattr(request.user, 'userprofile', None)
    is_courier = bool(
        profile and profile.role == 'courier'
    )

    if not (is_admin or is_courier):
        messages.error(
            request,
            "Anda tidak memiliki hak akses untuk mengubah penjemputan."
        )
        return redirect('home')

    pickup = get_object_or_404(PickupSchedule, id=pickup_id)

    allowed_statuses = ['IN_PROGRESS', 'SCHEDULED', 'REJECTED']

    # 1. Kurir menyelesaikan penjemputan melalui POST.
    if request.method == 'POST':
        if is_courier:
            # Kurir hanya boleh menyelesaikan tugas miliknya.
            if pickup.courier_id != request.user.id:
                messages.error(
                    request,
                    "Penjemputan ini bukan tugas yang ditugaskan kepada Anda."
                )
                return redirect('courier_dashboard')

            if pickup.status not in ['IN_PROGRESS', 'SCHEDULED']:
                messages.error(
                    request,
                    "Penjemputan ini tidak tersedia untuk diselesaikan."
                )
                return redirect('courier_dashboard')

        elif not is_admin:
            messages.error(request, "Akses ditolak.")
            return redirect('home')

        actual_weight = request.POST.get(
            'actual_weight', ''
        ).strip()

        if not actual_weight:
            messages.error(
                request,
                "Berat aktual wajib diisi."
            )
            return redirect(
                'courier_dashboard' if is_courier
                else 'admin_dashboard'
            )

        try:
            from decimal import Decimal, InvalidOperation

            weight = Decimal(actual_weight)

            if not weight.is_finite() or weight <= 0:
                raise InvalidOperation

        except (InvalidOperation, ValueError):
            messages.error(
                request,
                "Berat aktual harus lebih dari 0 kg."
            )
            return redirect(
                'courier_dashboard' if is_courier
                else 'admin_dashboard'
            )

        with transaction.atomic():
            reward_transaction = award_verified_pickup(
                pickup.mitra,
                weight,
                f'pickup-{pickup.pk}',
            )
            pickup.actual_weight = weight
            pickup.points = reward_transaction.points_delta
            pickup.status = 'COMPLETED'

            completed_count = PickupSchedule.objects.filter(
                mitra=pickup.mitra,
                status='COMPLETED'
            ).exclude(id=pickup.id).count() + 1

            if completed_count >= 10:
                pickup.certificate = 'certificates/Certificate.png'

            pickup.save()

        messages.success(
            request,
            f"Penjemputan PK-00{pickup.id} berhasil diselesaikan. "
            f"Berat aktual: {pickup.actual_weight} kg tercatat, "
            f"{pickup.points} poin ditambahkan."
        )

        if is_courier:
            return redirect('courier_dashboard')

        return redirect('admin_dashboard')

    # 2. Admin/petugas mengubah status melalui URL.
    if new_status:
        if not is_admin:
            messages.error(
                request,
                "Hanya admin/petugas yang boleh mengubah status ini."
            )
            return redirect('courier_dashboard')

        if new_status not in allowed_statuses:
            messages.error(
                request,
                "Status penjemputan tidak valid."
            )
            return redirect('admin_dashboard')

        # Tetapkan kurir jika belum ada penugasan.
        if (
            new_status in ['IN_PROGRESS', 'SCHEDULED']
            and pickup.courier_id is None
        ):
            courier = assign_next_courier(pickup)

            if courier is None:
                messages.error(
                    request,
                    "Belum ada akun kurir aktif. "
                    "Status penjemputan belum diubah."
                )
                return redirect('admin_dashboard')

            pickup.courier = courier

            messages.info(
                request,
                f"Kurir {courier.username} ditugaskan "
                f"untuk penjemputan PK-00{pickup.id}."
            )

        pickup.status = new_status
        pickup.save()

        messages.success(
            request,
            f"Status penjemputan PK-00{pickup.id} "
            f"diubah menjadi {new_status}!"
        )

        return redirect('admin_dashboard')

    return redirect(
        'admin_dashboard' if is_admin
        else 'courier_dashboard'
    )

@login_required
def pickup_history(request):
    status_filter = request.GET.get('status', 'ALL')
    
    # Ambil data penjemputan milik user yang sedang login
    user_pickups = PickupSchedule.objects.filter(mitra=request.user)
    
    # Hitung jumlah dinamis untuk masing-masing status
    total_count = user_pickups.count()
    pending_count = user_pickups.filter(status='PENDING').count()
    approved_count = user_pickups.filter(status='APPROVED').count()
    in_progress_count = user_pickups.filter(status__in=['IN_PROGRESS', 'SCHEDULED']).count()
    completed_count = user_pickups.filter(status='COMPLETED').count()
    rejected_count = user_pickups.filter(status='REJECTED').count()
    
    # Ambil data yang ditolak untuk ditampilkan di card khusus penolakan
    rejected_pickups = user_pickups.filter(status='REJECTED')
    
    # Filter data tabel berdasarkan tab yang aktif
    if status_filter != 'ALL':
        if status_filter == 'IN_PROGRESS':
            pickups = user_pickups.filter(status__in=['IN_PROGRESS', 'SCHEDULED'])
        else:
            pickups = user_pickups.filter(status=status_filter)
    else:
        pickups = user_pickups
        
    context = {
        'pickups': pickups,
        'current_status': status_filter,
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'rejected_count': rejected_count,
        'rejected_pickups': rejected_pickups,
    }
    return render(request, 'scheduling/pickup_history.html', context)


@login_required
def courier_dashboard(request):
    """Dashboard kurir hanya menampilkan tugas yang ditugaskan kepadanya."""

    profile = getattr(request.user, 'userprofile', None)

    if not profile or profile.role != 'courier':
        messages.error(
            request,
            "Halaman ini hanya dapat diakses oleh akun kurir."
        )
        return redirect('home')

    active_pickups = PickupSchedule.objects.filter(
        courier=request.user,
        status__in=['IN_PROGRESS', 'SCHEDULED']
    ).select_related('mitra').order_by('-created_at')

    context = {
        'pickups': active_pickups,
    }

    return render(
        request,
        'scheduling/courier_dashboard.html',
        context
    )

@login_required
def mitra_profile(request):
    profile, _ = MitraProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        text_fields = [
            'business_name', 'business_type', 'pic_name', 'phone_number',
            'operational_hours', 'provinsi', 'kota', 'kecamatan',
            'kelurahan', 'address_detail', 'courier_notes',
        ]
        for field in text_fields:
            setattr(profile, field, request.POST.get(field, '').strip())

        lat_raw = request.POST.get('latitude', '').strip()
        lng_raw = request.POST.get('longitude', '').strip()

        if lat_raw and lng_raw:
            try:
                lat, lng = float(lat_raw), float(lng_raw)
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    profile.latitude = lat
                    profile.longitude = lng
                    profile.location_locked = True   # lokasi jadi permanen
                else:
                    messages.error(request, 'Koordinat di luar jangkauan yang valid.')
                    return redirect('mitra_profile')
            except ValueError:
                messages.error(request, 'Format koordinat tidak valid.')
                return redirect('mitra_profile')
        elif not profile.location_locked:
            # mitra belum pernah menentukan titik dan tidak mengirim koordinat
            messages.error(request, 'Tentukan titik lokasi di peta terlebih dahulu.')
            return redirect('mitra_profile')
        # kalau sudah locked dan tidak kirim koordinat: titik lama dipertahankan

        profile.save()
        messages.success(request, 'Profil berhasil diperbarui.')
        return redirect('mitra_profile')

    # ---- Statistik dinamis ----
    completed = PickupSchedule.objects.filter(mitra=request.user, status='COMPLETED')
    total_limbah = completed.aggregate(Sum('actual_weight'))['actual_weight__sum'] or 0
    total_poin = completed.aggregate(Sum('points'))['points__sum'] or 0

    context = {
        'profile': profile,
        'total_limbah': total_limbah,
        'total_penjemputan': completed.count(),
        'total_poin': total_poin,
        'co2e_dicegah': round(float(total_limbah) * 0.75, 1),
        'map_data': {
            'lat': profile.latitude,
            'lng': profile.longitude,
            'locked': profile.location_locked,
        },
    }
    return render(request, 'scheduling/mitra_profile.html', context)

@login_required
def admin_verify_couriers(request):
    """Halaman admin untuk melihat daftar kurir yang mendaftar dan menunggu verifikasi."""
    if not _can_manage_pickups(request.user):
        return redirect('home')
    
    pending_couriers = CourierProfile.objects.filter(is_approved=False)
    approved_couriers = CourierProfile.objects.filter(is_approved=True)
    
    context = {
        'pending_couriers': pending_couriers,
        'approved_couriers': approved_couriers,
    }
    return render(request, 'scheduling/admin_verify_couriers.html', context)


@login_required
def approve_courier(request, courier_id):
    """Fungsi saat admin menekan tombol 'Setujui' untuk akun kurir."""
    if not _can_manage_pickups(request.user):
        return redirect('home')
    
    courier_profile = get_object_or_404(CourierProfile, id=courier_id)
    courier_profile.is_approved = True
    courier_profile.save()
    
    return redirect('admin_verify_couriers')
