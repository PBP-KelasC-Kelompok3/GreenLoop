# Waste & Reward

Modul ini mengelola poin milik mitra B2B, katalog voucher, penukaran poin, dan pemakaian voucher saat checkout.

## Aturan poin

- Hanya akun dengan role `mitra` yang dapat memperoleh atau menukar poin.
- Poin diberikan setelah pickup dinyatakan terverifikasi oleh modul pickup/kurir.
- Konversi saat ini adalah 5 poin untuk setiap kilogram. Berat dibulatkan ke bawah sampai satu angka desimal sebelum dihitung.
- Kirim referensi pickup yang stabil dan unik sebagai `pickup_reference`. Pemanggilan ulang dengan referensi milik mitra yang sama tidak menggandakan poin.
- Saldo dihitung dari transaksi poin, dan riwayatnya tersimpan di `RewardTransaction`.

Contoh pemanggilan setelah status pickup berubah menjadi terverifikasi:

```python
from waste_reward.services import award_verified_pickup

award_verified_pickup(mitra, pickup.weight_kg, f'pickup-{pickup.pk}')
```

Pemanggilan dilakukan sekali ketika pickup mencapai status terverifikasi. Gunakan ID pickup sebagai referensi, bukan nilai yang berubah-ubah.

## Penukaran voucher

`redeem_voucher(user, voucher_id)` memvalidasi role, status voucher, dan saldo. Jika berhasil, layanan membuat `UserVoucher` dan transaksi debit poin dalam satu transaksi database. View dashboard dan endpoint penukaran tersedia melalui namespace `waste_reward`.

## Kontrak checkout

Modul e-commerce dapat menggunakan `apply_voucher_at_checkout` untuk memvalidasi voucher milik mitra, membatasi penggunaan satu voucher per pesanan, menandai voucher terpakai, dan menghitung total.

```python
from django.db import transaction
from waste_reward.services import apply_voucher_at_checkout

with transaction.atomic():
    result = apply_voucher_at_checkout(
        user=buyer,
        voucher_code=checkout_voucher_code,
        order_reference=f'order-{order.pk}',
        subtotal=order.subtotal,
        shipping_cost=order.shipping_cost,
        wholesale_order=order.is_wholesale,
    )
    order.goods_discount = result['goods_discount']
    order.shipping_discount = result['shipping_discount']
    order.total = result['total_due']
    order.save()
```

Panggil layanan dalam transaksi database yang sama dengan pembuatan atau penyimpanan pesanan. Jika penyimpanan pesanan gagal, perubahan status voucher ikut dibatalkan. `order_reference` harus unik dan stabil. Nilai `wholesale_order` hanya `True` untuk pesanan grosir B2B.

Hasil layanan memuat `user_voucher`, `subtotal`, `shipping_cost`, `goods_discount`, `shipping_discount`, dan `total_due`. Untuk akun yang tidak berhak, layanan melempar `PermissionDenied`; untuk voucher tidak tersedia/invalid, layanan melempar `VoucherUnavailable`; nominal atau referensi tidak valid menghasilkan `ValueError`.

## Verifikasi lokal

Jalankan tes modul dari direktori root proyek:

```powershell
.\env\Scripts\python.exe manage.py test waste_reward
```
