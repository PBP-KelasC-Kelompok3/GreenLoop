from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from .models import PickupSchedule, MitraProfile
from .forms import MitraProfileForm, PickupScheduleForm
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models import Q
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST
from waste_reward.services import get_balance
from waste_reward.models import RewardTransaction
from waste_reward.points import POINTS_PER_KILOGRAM, membership_tier
from greenloop.impact import estimate_co2e_avoided
from accounts.permissions import can_manage_greenloop
from accounts.decorator import role_required
from .schedule_rules import PICKUP_TIME_SLOTS, validate_pickup_window


def _can_manage_pickups(user):
    return can_manage_greenloop(user)


@role_required(['mitra'])
def mitra_dashboard(request):
    """Dashboard Mitra B2B dengan agregasi statistik, poin, dan grafik dinamis."""
    user_pickups = PickupSchedule.objects.filter(mitra=request.user).select_related(
        'courier_assignment__courier'
    ).order_by('-created_at')
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

    # 3. Estimasi CO2e memakai faktor bersama lintas halaman.
    co2_saved = estimate_co2e_avoided(total_waste)

    # Reward ledger is the single source of truth for member points.
    calculated_points = get_balance(request.user)

    # 5. Penjemputan Terdekat
    next_pickup = (
        user_pickups.filter(status__in=['PENDING', 'APPROVED', 'SCHEDULED', 'IN_PROGRESS'])
        .order_by('pickup_date')
        .first()
    )

    # 6. Hitung Stepper Progress Penjemputan Berikutnya
    stepper_progress = 0
    if next_pickup:
        courier_assignment = getattr(next_pickup, 'courier_assignment', None)
        if next_pickup.status == 'PENDING':
            stepper_progress = 25
        elif next_pickup.status == 'APPROVED':
            stepper_progress = 50
        elif next_pickup.status == 'COMPLETED':
            stepper_progress = 100
        elif courier_assignment:
            stepper_progress = 75

    # 7. Logika Tier/Level Membership Dinamis
    current_tier = membership_tier(calculated_points)
    if current_tier == 'Bronze':
        next_tier = 'Silver'
        target_points = 1000
    elif current_tier == 'Silver':
        next_tier = 'Gold'
        target_points = 3000
    elif current_tier == 'Gold':
        next_tier = 'Platinum'
        target_points = 5000
    else:
        current_tier = 'Platinum'
        next_tier = 'Max Level'
        target_points = calculated_points

    points_needed = max(0, target_points - calculated_points)
    kg_needed = round(points_needed / POINTS_PER_KILOGRAM, 1)
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
        'points_per_kg': POINTS_PER_KILOGRAM,
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


@role_required(['mitra'])
def create_pickup(request):
    if request.method == 'POST':
        form = PickupScheduleForm(request.POST, request.FILES)
        if form.is_valid():
            from courier.maps import in_depok
            location = MitraProfile.objects.filter(user=request.user).first()
            if (
                location is None
                or location.latitude is None
                or location.longitude is None
                or not in_depok(location.latitude, location.longitude)
            ):
                messages.error(
                    request,
                    'Atur titik lokasi usaha di Kota Depok pada Profil sebelum mengajukan penjemputan.',
                )
                return redirect('mitra_profile')
            pickup = form.save(commit=False)
            pickup.mitra = request.user
            pickup.status = 'PENDING'
            pickup.save()
            messages.success(request, "Pengajuan penjemputan berhasil dikirim!")
            return redirect('mitra_dashboard')
    else:
        form = PickupScheduleForm()
        
    local_now = timezone.localtime()
    context = {
        'form': form,
        'pickup_slots': PICKUP_TIME_SLOTS,
        'schedule_today': timezone.localdate().isoformat(),
        'schedule_now_minutes': local_now.hour * 60 + local_now.minute,
    }
    return render(request, 'scheduling/create_pickup.html', context)


@role_required(['mitra'])
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
    pickup_date = parse_date(request.POST.get('pickup_date', ''))
    time_slot = request.POST.get('time_slot', '')
    valid_slots = {value for value, _label in PICKUP_TIME_SLOTS}
    try:
      if time_slot not in valid_slots:
        raise ValidationError('Slot waktu penjemputan tidak valid.')
      validate_pickup_window(pickup_date, time_slot)
    except ValidationError as error:
      messages.error(request, error.messages[0])
      return render(request, 'scheduling/edit_pickup.html', {
          'pickup': pickup,
          'pickup_slots': PICKUP_TIME_SLOTS,
          'submitted_date': request.POST.get('pickup_date', ''),
          'submitted_slot': time_slot,
      })

    pickup.pickup_date = pickup_date
    pickup.pickup_time_slot = time_slot
    pickup.notes = request.POST.get('notes')
    pickup.save(update_fields=['pickup_date', 'pickup_time_slot', 'notes'])

    messages.success(request, 'Jadwal penjemputan berhasil diperbarui.')
    return redirect('mitra_dashboard')

  return render(request, 'scheduling/edit_pickup.html', {
      'pickup': pickup,
      'pickup_slots': PICKUP_TIME_SLOTS,
      'submitted_date': pickup.pickup_date.isoformat(),
      'submitted_slot': pickup.pickup_time_slot,
  })


@role_required(['mitra'])
@require_POST
def delete_pickup(request, pickup_id):
    pickup = get_object_or_404(PickupSchedule, id=pickup_id, mitra=request.user)
    if pickup.status != 'PENDING':
        messages.error(request, 'Hanya pengajuan yang menunggu verifikasi yang dapat dihapus.')
        return redirect('pickup_history')

    pickup.delete()
    messages.success(request, 'Pengajuan penjemputan berhasil dihapus.')
    return redirect('pickup_history')


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
        'mitra', 'courier_assignment__courier'
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

    waiting_courier_count = all_pickups.filter(status='APPROVED').count()

    rejected_count = all_pickups.filter(status='REJECTED').count()

    completed_count = all_pickups.filter(
        status='COMPLETED'
    ).count()

    context = {
        'all_pickups': all_pickups,
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'waiting_courier_count': waiting_courier_count,
        'completed_count': completed_count,
        'rejected_count': rejected_count,
        'search_query': search_query,
    }

    return render(
        request,
        'scheduling/admin_dashboard.html',
        context
    )


@login_required
@require_GET
def update_pickup_status(request, pickup_id, new_status):
    """Admin menyetujui foto atau menolak pengajuan; penugasan ditangani app courier."""
    if not _can_manage_pickups(request.user):
        messages.error(request, "Anda tidak memiliki hak akses untuk mengubah penjemputan.")
        return redirect('home')

    pickup = get_object_or_404(PickupSchedule, id=pickup_id)
    if pickup.status != 'PENDING':
        messages.info(request, "Pengajuan ini sudah diproses sebelumnya.")
        return redirect('admin_dashboard')

    if new_status == 'REJECTED':
        pickup.status = 'REJECTED'
        pickup.save(update_fields=['status'])
        messages.success(request, f"Pengajuan PK-{pickup.pk:04d} ditolak.")
        return redirect('admin_dashboard')

    if new_status != 'SCHEDULED':
        messages.error(request, "Status penjemputan tidak valid.")
        return redirect('admin_dashboard')

    pickup.status = 'APPROVED'
    pickup.save(update_fields=['status'])

    from courier.dispatch import dispatch_pickup, dispatch_wait_message
    result = dispatch_pickup(pickup.pk)
    if result.assignment:
        courier_name = result.assignment.courier.get_full_name() or result.assignment.courier.username
        messages.success(
            request,
            f"Foto disetujui. Kurir {courier_name} ditugaskan untuk PK-{pickup.pk:04d}.",
        )
    else:
        messages.warning(
            request,
            f"Foto disetujui, tetapi PK-{pickup.pk:04d} belum ditugaskan. "
            f"{dispatch_wait_message(result.reason)} Sistem akan mencoba lagi saat kurir mulai bertugas.",
        )
    return redirect('admin_dashboard')

@role_required(['mitra'])
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


@role_required(['mitra'])
def mitra_profile(request):
    profile, _ = MitraProfile.objects.get_or_create(user=request.user)
    form = MitraProfileForm(request.POST or None, instance=profile)

    if request.method == 'POST':
        lat_raw = request.POST.get('latitude', '').strip()
        lng_raw = request.POST.get('longitude', '').strip()
        map_valid = True

        if lat_raw and lng_raw:
            try:
                lat, lng = float(lat_raw), float(lng_raw)
                from courier.maps import in_depok
                if -90 <= lat <= 90 and -180 <= lng <= 180 and in_depok(lat, lng):
                    profile.latitude = lat
                    profile.longitude = lng
                    profile.location_locked = True   # lokasi jadi permanen
                else:
                    messages.error(request, 'Pilih titik lokasi di dalam Kota Depok.')
                    map_valid = False
                    lat_raw = lng_raw = ''
            except ValueError:
                messages.error(request, 'Format koordinat tidak valid.')
                map_valid = False
                lat_raw = lng_raw = ''
        elif not profile.location_locked:
            # mitra belum pernah menentukan titik dan tidak mengirim koordinat
            messages.error(request, 'Tentukan titik lokasi di peta terlebih dahulu.')
            map_valid = False
        if form.is_valid() and map_valid:
            profile = form.save(commit=False)
            # Koordinat dan status kunci diatur oleh validasi peta di atas.
            if lat_raw and lng_raw:
                try:
                    profile.latitude = float(lat_raw)
                    profile.longitude = float(lng_raw)
                    profile.location_locked = True
                except ValueError:
                    pass
            profile.save()
            messages.success(request, 'Profil berhasil diperbarui.')
            return redirect('mitra_profile')
        if not form.is_valid():
            messages.error(request, 'Periksa kembali data profil yang kamu masukkan.')

    # ---- Statistik dinamis ----
    completed = PickupSchedule.objects.filter(mitra=request.user, status='COMPLETED')
    total_limbah = completed.aggregate(Sum('actual_weight'))['actual_weight__sum'] or 0
    total_poin = (
        RewardTransaction.objects.filter(
            user=request.user,
            kind=RewardTransaction.Kind.PICKUP,
        ).aggregate(Sum('points_delta'))['points_delta__sum'] or 0
    )
    current_tier = membership_tier(get_balance(request.user))
    from courier.maps import DEPOK_BOUNDS, DEPOK_BOUNDARY, in_depok
    has_depok_location = (
        profile.latitude is not None
        and profile.longitude is not None
        and in_depok(profile.latitude, profile.longitude)
    )

    context = {
        'profile': profile,
        'form': form,
        'total_limbah': total_limbah,
        'total_penjemputan': completed.count(),
        'total_poin': total_poin,
        'membership_tier': current_tier,
        'co2e_dicegah': estimate_co2e_avoided(total_limbah),
        'map_data': {
            'lat': profile.latitude if has_depok_location else None,
            'lng': profile.longitude if has_depok_location else None,
            'locked': profile.location_locked,
            'bounds': DEPOK_BOUNDS,
            'boundary': DEPOK_BOUNDARY,
        },
    }
    return render(request, 'scheduling/mitra_profile.html', context)


@role_required(['mitra'])
@require_POST
def delete_mitra_profile(request):
    profile = get_object_or_404(MitraProfile, user=request.user)
    profile.delete()
    messages.success(request, 'Data profil usaha berhasil dihapus. Akun mitra tetap aktif.')
    return redirect('mitra_dashboard')


@role_required(['mitra'])
@require_POST
def update_mitra_profile_photo(request):
    photo = request.FILES.get('profile_photo')
    if not photo:
        return JsonResponse({'ok': False, 'message': 'Pilih foto profil terlebih dahulu.'}, status=400)

    from django import forms

    photo_field = forms.ImageField()
    try:
        cleaned_photo = photo_field.clean(photo)
    except forms.ValidationError as error:
        return JsonResponse({'ok': False, 'message': error.messages[0]}, status=400)

    profile, _ = MitraProfile.objects.get_or_create(user=request.user)
    previous_photo = profile.profile_photo
    profile.profile_photo = cleaned_photo
    profile.save(update_fields=['profile_photo'])
    if previous_photo and previous_photo.name != profile.profile_photo.name:
        previous_photo.delete(save=False)

    return JsonResponse({'ok': True, 'photo_url': profile.profile_photo.url})
