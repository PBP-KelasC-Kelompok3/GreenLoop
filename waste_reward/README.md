# Waste & Reward

Modul ini mengelola poin milik mitra B2B, katalog voucher, penukaran poin, dan pemakaian voucher saat checkout.

## Aturan poin

- Hanya akun dengan role `mitra` yang dapat memperoleh atau menukar poin.
- Poin diberikan setelah pickup dinyatakan terverifikasi oleh modul pickup/kurir.
- Konversi saat ini adalah 5 poin untuk setiap kilogram. Berat dibulatkan ke bawah sampai satu angka desimal sebelum dihitung.
- Kirim referensi pickup yang stabil dan unik sebagai `pickup_reference`. Pemanggilan ulang dengan referensi milik mitra yang sama tidak menggandakan poin.
- Saldo dihitung dari transaksi poin, dan riwayatnya tersimpan di `RewardTransaction`.
- Poin pada riwayat pickup disalin dari ledger setelah pemberian poin berhasil; ledger tetap menjadi sumber saldo utama.
- Voucher katalog diarsipkan, bukan dihapus permanen, agar riwayat penukaran tetap utuh.
- `RewardTransaction` dan `UserVoucher` bersifat read-only di admin. Perubahan saldo harus lewat service agar jejak audit dan saldo tidak rusak.

Contoh pemanggilan setelah status pickup berubah menjadi terverifikasi:

```python
from waste_reward.services import award_verified_pickup

award_verified_pickup(mitra, pickup.weight_kg, f'pickup-{pickup.pk}')
```

Pemanggilan dilakukan sekali ketika pickup mencapai status terverifikasi. Gunakan ID pickup sebagai referensi, bukan nilai yang berubah-ubah.

## Penukaran voucher

`redeem_voucher(user, voucher_id)` memvalidasi role, status voucher, dan saldo. Jika berhasil, layanan membuat `UserVoucher` dan transaksi debit poin dalam satu transaksi database. View dashboard dan endpoint penukaran tersedia melalui namespace `waste_reward`. Dashboard menyediakan pencarian, filter jenis/periode, dan paginasi riwayat. Penukaran berjalan lewat AJAX dengan umpan balik optimistis; form POST tetap tersedia sebagai fallback.

## Integrasi katalog dan checkout

Mitra memakai katalog di `/katalog/` untuk melihat harga B2B, mencari tujuan pengiriman, memilih kurir, dan menggunakan voucher aktif yang sudah ditukar. Voucher tidak bisa dipakai oleh akun lain, dipakai ulang, atau digunakan setelah kedaluwarsa. Voucher grosir hanya berlaku untuk akun mitra.

Endpoint checkout memvalidasi kembali stok, harga berdasarkan role, dan ongkos kirim dari RajaOngkir di server. Pemakaian voucher, pengurangan stok, pembuatan pesanan, dan permintaan token Midtrans berada dalam transaksi database yang sama. Jika checkout gagal sebelum pesanan dibuat, stok dan voucher tidak terpotong. Pesanan menyimpan snapshot nama produk, jumlah, harga, ongkir, potongan, alamat, dan layanan kurir.

Status pembayaran diperbarui dari notifikasi Midtrans di `/katalog/api/transaction/notification/`. Notifikasi harus memakai tanda tangan valid. Jika pembayaran gagal atau kedaluwarsa, stok dan voucher dikembalikan. Untuk pembayaran sukses dari halaman Snap, katalog juga meminta konfirmasi status ke server Midtrans.

## Konfigurasi dan migrasi

Atur environment berikut sebelum mengaktifkan checkout:

- `MIDTRANS_CLIENT_KEY` dan `MIDTRANS_SERVER_KEY`
- `MIDTRANS_IS_PRODUCTION` (`False` untuk sandbox)
- `RAJAONGKIR_API_KEY` dan `RAJAONGKIR_ORIGIN_ID`
- Opsional: `RAJAONGKIR_BASE_URL` dan `RAJAONGKIR_COURIERS`

Arahkan URL notifikasi pembayaran Midtrans ke `/katalog/api/transaction/notification/`, lalu jalankan migrasi:

```powershell
python manage.py migrate
```

Voucher bawaan dibuat oleh migrasi awal `waste_reward`. Poin otomatis ditambahkan saat pickup mitra selesai dan memiliki berat aktual; ID pickup dipakai sebagai referensi unik agar penyimpanan ulang tidak menggandakan poin.

## Verifikasi lokal

Jalankan tes modul dari direktori root proyek:

```powershell
.\env\Scripts\python.exe manage.py test waste_reward
```

Ukur coverage modul (pasang `coverage` di virtualenv lokal terlebih dahulu):

```powershell
python -m pip install coverage
python -m coverage run --source=waste_reward manage.py test waste_reward
python -m coverage report -m
```
