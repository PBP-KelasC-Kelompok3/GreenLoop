from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import PickupSchedule
from .forms import PickupScheduleForm
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models import Q

@login_required
def mitra_dashboard(request):
    """Dashboard Mitra B2B dengan agregasi statistik, poin, dan grafik dinamis."""
    user_pickups = PickupSchedule.objects.filter(mitra=request.user).order_by('-created_at')
    completed_pickups = user_pickups.filter(status='COMPLETED')

    # 1. Total Limbah Disetor (kg)
    total_waste = (
        completed_pickups.aggregate(Sum('estimated_weight'))['estimated_weight__sum'] or 0
    )

   # 2. Total Penjemputan Selesai (kali)
    pickups_this_month = completed_pickups.count()

    # 3. Estimasi CO2e Dicegah (0.5 kg CO2e per kg limbah)
    co2_saved = round(total_waste * 0.5, 1)

    # 4. Hitung Poin Dinamis (1 kg limbah = 10 poin)
    calculated_points = int(total_waste * 10)

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
    elif calculated_points < 2000:
        current_tier = 'Silver'
        next_tier = 'Gold'
        target_points = 2000
    elif calculated_points < 3000:
        current_tier = 'Gold'
        next_tier = 'Platinum'
        target_points = 3000
    else:
        current_tier = 'Platinum'
        next_tier = 'Max Level'
        target_points = calculated_points

    points_needed = max(0, target_points - calculated_points)
    kg_needed = round(points_needed / 10, 1)
    level_progress_pct = (
        min(100, int((calculated_points / target_points) * 100))
        if target_points > 0
        else 100
    )

    # 8. Agregasi Grafik 8 Minggu Terakhir
    weekly_labels = []
    weekly_data = []

    today = timezone.now().date()
    for i in range(7, -1, -1):
        start_of_week = today - timedelta(days=today.weekday() + (i * 7))
        end_of_week = start_of_week + timedelta(days=6)

        sum_weight = (
            completed_pickups.filter(
                pickup_date__range=[start_of_week, end_of_week]
            ).aggregate(Sum('estimated_weight'))['estimated_weight__sum'] or 0
        )

        weekly_labels.append(f'M{8-i}')
        weekly_data.append(float(sum_weight))

    context = {
        'pickups': user_pickups,
        'total_waste': total_waste,
        'pickups_this_month': pickups_this_month,
        'co2_saved': co2_saved,
        'user_points': calculated_points,
        'weekly_labels': json.dumps(weekly_labels),
        'weekly_data': json.dumps(weekly_data),
        'title': 'Dashboard Mitra',
        'next_pickup': next_pickup,
        'stepper_progress': stepper_progress,
        'current_tier': current_tier,
        'next_tier': next_tier,
        'target_points': target_points,
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
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Anda tidak memiliki hak akses ke Halaman Admin.")
        return redirect('mitra_dashboard')

    # Ambil kata kunci pencarian dari URL (?q=nama)
    search_query = request.GET.get('q', '')
    
    all_pickups = PickupSchedule.objects.select_related('mitra').all().order_by('-created_at')
    
    # Jika admin mengetik sesuatu di kolom pencarian
    if search_query:
        all_pickups = all_pickups.filter(
            Q(mitra__username__icontains=search_query) | 
            Q(mitra__email__icontains=search_query) |
            Q(id__icontains=search_query)
        )

    pending_count = all_pickups.filter(status='PENDING').count()
    in_progress_count = all_pickups.filter(status__in=['IN_PROGRESS', 'SCHEDULED']).count()
    completed_count = all_pickups.filter(status='COMPLETED').count()

    context = {
        'all_pickups': all_pickups,
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'search_query': search_query, # Kirim balik ke template
    }
    return render(request, 'scheduling/admin_dashboard.html', context)

@login_required
def update_pickup_status(request, pickup_id, new_status=None):
    pickup = get_object_or_404(PickupSchedule, id=pickup_id)
    
    # 1. Jika diakses via Form POST (Selesaikan Penjemputan & Input Berat)
    if request.method == 'POST':
        actual_weight = request.POST.get('actual_weight')
        
        pickup.status = 'COMPLETED'
        
        if actual_weight:
            pickup.actual_weight = float(actual_weight)
            # Perhitungan poin dinamis (berat * 10)
            pickup.points = int(pickup.actual_weight * 10)
            
        # Hitung total penjemputan selesai milik mitra ini (termasuk yang sedang diselesaikan ini)
        completed_count = PickupSchedule.objects.filter(
            mitra=pickup.mitra, 
            status='COMPLETED'
        ).exclude(id=pickup.id).count() + 1
        
        # Cek apakah ini tepat pencapaian ke-10 (hanya 1 kali saja, tidak pakai kelipatan sisa bagi %)
        if completed_count == 10:
            pickup.certificate = "certificates/Certificate.png"
            messages.info(request, f"🎉 Selamat! Penjemputan ke-10 untuk {pickup.mitra.username} tercapai! Sertifikat Anda kini tersedia di atas.")
        elif completed_count > 10:
            # Jika sudah lewat dari 10, pastikan sertifikat tetap tersemat atau aman
            pickup.certificate = "certificates/Certificate.png"
            
        pickup.save()
        messages.success(request, f"Penjemputan PK-00{pickup.id} berhasil diselesaikan. Berat aktual: {pickup.actual_weight} kg tercatat.")
        
        # Jika yang submit adalah kurir, kembalikan ke courier_dashboard
        if 'courier' in request.META.get('HTTP_REFERER', ''):
            return redirect('courier_dashboard')
            
    # 2. Jika diakses via Link Instan (Proses / Tolak oleh Admin)
    elif new_status:
        pickup.status = new_status
        pickup.save()
        messages.success(request, f"Status penjemputan PK-00{pickup.id} diubah menjadi {new_status}!")
        
    return redirect('admin_dashboard')

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
    """Dashboard khusus kurir untuk melihat tugas aktif dan input berat aktual."""
    # Ambil penjemputan yang sedang diproses / siap ditimbang kurir
    active_pickups = PickupSchedule.objects.filter(status__in=['IN_PROGRESS', 'SCHEDULED']).order_by('-created_at')
    
    context = {
        'pickups': active_pickups,
    }
    return render(request, 'scheduling/courier_dashboard.html', context)