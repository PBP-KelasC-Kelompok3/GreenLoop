from django.db import migrations


# Curated GreenLoop starter catalog. This is intentionally kept inside the
# migration so deployed databases receive the same deterministic initial data.
PRODUCTS = [
    ("Sabun Batang Eco-Enzyme Jeruk Nipis 80 g", "Sabun batang dengan aroma jeruk nipis, dibuat untuk rutinitas mandi harian.", 22000, 16500, 48, 80),
    ("Sabun Batang Eco-Enzyme Lemon 80 g", "Sabun batang beraroma lemon segar dalam kemasan ringkas.", 22000, 16500, 45, 80),
    ("Sabun Batang Eco-Enzyme Serai 80 g", "Sabun batang dengan aroma serai yang segar untuk penggunaan sehari-hari.", 22000, 16500, 42, 80),
    ("Sabun Batang Eco-Enzyme Lavender 80 g", "Sabun batang beraroma lavender dengan busa lembut.", 24000, 18000, 36, 80),
    ("Sabun Batang Eco-Enzyme Peppermint 80 g", "Sabun batang dengan sensasi aroma peppermint yang menyegarkan.", 24000, 18000, 34, 80),
    ("Sabun Batang Eco-Enzyme Kopi 80 g", "Sabun batang dengan aroma kopi dan tekstur scrub ringan.", 25000, 18750, 32, 80),
    ("Sabun Batang Eco-Enzyme Arang Aktif 80 g", "Sabun batang arang aktif untuk membersihkan kulit setelah aktivitas harian.", 25000, 18750, 30, 80),
    ("Sabun Batang Eco-Enzyme Oat 80 g", "Sabun batang dengan oat dan aroma lembut untuk perawatan harian.", 25000, 18750, 32, 80),
    ("Sabun Batang Eco-Enzyme Mawar 80 g", "Sabun batang dengan aroma mawar ringan.", 24000, 18000, 30, 80),
    ("Sabun Batang Eco-Enzyme Tea Tree 80 g", "Sabun batang dengan aroma tea tree yang bersih dan segar.", 25000, 18750, 28, 80),
    ("Sabun Batang Eco-Enzyme Calendula 80 g", "Sabun batang calendula dengan aroma botanical yang ringan.", 26000, 19500, 26, 80),
    ("Sabun Batang Eco-Enzyme Rosemary 80 g", "Sabun batang beraroma rosemary untuk rutinitas mandi.", 24000, 18000, 28, 80),
    ("Sabun Batang Eco-Enzyme Green Tea 80 g", "Sabun batang dengan aroma green tea yang lembut.", 24000, 18000, 35, 80),
    ("Sabun Batang Eco-Enzyme Kelapa 80 g", "Sabun batang dengan aroma kelapa tropis.", 24000, 18000, 32, 80),
    ("Sabun Batang Eco-Enzyme Tanpa Pewangi 80 g", "Sabun batang tanpa tambahan pewangi untuk pilihan aroma netral.", 22000, 16500, 24, 80),
    ("Sabun Batang Eco-Enzyme Citrus Mint 80 g", "Perpaduan aroma citrus dan mint dalam sabun batang.", 25000, 18750, 28, 80),
    ("Sabun Batang Eco-Enzyme Kopi Kakao 80 g", "Sabun batang beraroma kopi dan kakao dengan scrub ringan.", 26000, 19500, 26, 80),
    ("Sabun Batang Eco-Enzyme Rice Bran 80 g", "Sabun batang dengan rice bran dan aroma lembut.", 26000, 19500, 25, 80),
    ("Sabun Batang Eco-Enzyme Citrus 100 g", "Ukuran 100 gram sabun batang beraroma citrus untuk pemakaian lebih lama.", 28000, 21000, 30, 100),
    ("Sabun Batang Eco-Enzyme Travel 40 g", "Sabun batang ukuran perjalanan dengan aroma citrus.", 14000, 10500, 50, 40),
    ("Sabun Cuci Piring Eco-Enzyme Jeruk 500 ml", "Sabun cuci piring cair beraroma jeruk untuk kebutuhan dapur.", 26000, 19500, 40, 600),
    ("Sabun Cuci Piring Eco-Enzyme Jeruk 1 L", "Ukuran hemat satu liter sabun cuci piring cair beraroma jeruk.", 46000, 34500, 30, 1100),
    ("Sabun Cuci Piring Eco-Enzyme Serai 500 ml", "Sabun cuci piring cair beraroma serai.", 26000, 19500, 36, 600),
    ("Sabun Cuci Piring Eco-Enzyme Serai 1 L", "Ukuran hemat satu liter sabun cuci piring cair beraroma serai.", 46000, 34500, 28, 1100),
    ("Sabun Cuci Piring Eco-Enzyme Lemon 500 ml", "Sabun cuci piring cair dengan aroma lemon segar.", 26000, 19500, 38, 600),
    ("Sabun Cuci Piring Eco-Enzyme Lemon 1 L", "Ukuran hemat satu liter sabun cuci piring cair beraroma lemon.", 46000, 34500, 30, 1100),
    ("Sabun Cuci Piring Eco-Enzyme Mint 500 ml", "Sabun cuci piring cair beraroma mint.", 27000, 20250, 30, 600),
    ("Sabun Cuci Piring Eco-Enzyme Mint 1 L", "Ukuran hemat satu liter sabun cuci piring cair beraroma mint.", 48000, 36000, 24, 1100),
    ("Sabun Cuci Piring Eco-Enzyme Pandan 500 ml", "Sabun cuci piring cair dengan aroma pandan ringan.", 27000, 20250, 28, 600),
    ("Sabun Cuci Piring Eco-Enzyme Pandan 1 L", "Ukuran hemat satu liter sabun cuci piring cair beraroma pandan.", 48000, 36000, 22, 1100),
    ("Pembersih Serbaguna Eco-Enzyme Citrus 500 ml", "Pembersih serbaguna untuk permukaan rumah dengan aroma citrus.", 30000, 22500, 35, 600),
    ("Pembersih Serbaguna Eco-Enzyme Citrus 1 L", "Refill satu liter pembersih serbaguna beraroma citrus.", 52000, 39000, 25, 1100),
    ("Pembersih Serbaguna Eco-Enzyme Serai 500 ml", "Pembersih serbaguna untuk permukaan rumah beraroma serai.", 30000, 22500, 32, 600),
    ("Pembersih Serbaguna Eco-Enzyme Serai 1 L", "Refill satu liter pembersih serbaguna beraroma serai.", 52000, 39000, 22, 1100),
    ("Pembersih Serbaguna Eco-Enzyme Lavender 500 ml", "Pembersih serbaguna dengan aroma lavender ringan.", 32000, 24000, 28, 600),
    ("Pembersih Serbaguna Eco-Enzyme Lavender 1 L", "Refill satu liter pembersih serbaguna beraroma lavender.", 55000, 41250, 20, 1100),
    ("Pembersih Serbaguna Eco-Enzyme Tanpa Pewangi 500 ml", "Pembersih serbaguna dengan aroma netral untuk berbagai permukaan.", 30000, 22500, 24, 600),
    ("Pembersih Serbaguna Eco-Enzyme Tanpa Pewangi 1 L", "Refill satu liter pembersih serbaguna dengan aroma netral.", 52000, 39000, 18, 1100),
    ("Pembersih Lantai Eco-Enzyme Jeruk 500 ml", "Pembersih lantai cair beraroma jeruk untuk kebersihan rumah.", 28000, 21000, 30, 600),
    ("Pembersih Lantai Eco-Enzyme Jeruk 1 L", "Ukuran satu liter pembersih lantai cair beraroma jeruk.", 48000, 36000, 24, 1100),
    ("Pembersih Lantai Eco-Enzyme Serai 500 ml", "Pembersih lantai cair beraroma serai.", 28000, 21000, 28, 600),
    ("Pembersih Lantai Eco-Enzyme Serai 1 L", "Ukuran satu liter pembersih lantai cair beraroma serai.", 48000, 36000, 22, 1100),
    ("Pembersih Kaca Eco-Enzyme 500 ml", "Pembersih kaca untuk perawatan jendela dan permukaan kaca.", 29000, 21750, 25, 600),
    ("Pembersih Kamar Mandi Eco-Enzyme 500 ml", "Pembersih serbaguna untuk area kamar mandi.", 32000, 24000, 22, 600),
    ("Pembersih Dapur Eco-Enzyme 500 ml", "Pembersih permukaan dapur untuk penggunaan rumah tangga.", 32000, 24000, 24, 600),
    ("Pencuci Buah dan Sayur Eco-Enzyme 500 ml", "Cairan pencuci buah dan sayur; ikuti petunjuk pemakaian pada label.", 30000, 22500, 25, 600),
    ("Paket Sabun Batang Eco-Enzyme Isi 3", "Paket tiga sabun batang pilihan untuk persediaan rumah.", 62000, 46500, 22, 300),
    ("Paket Cuci Dapur Eco-Enzyme", "Paket sabun cuci piring dan pembersih dapur untuk kebutuhan rumah.", 54000, 40500, 18, 1200),
    ("Paket Perawatan Rumah Eco-Enzyme", "Paket pembersih serbaguna dan lantai dalam ukuran praktis.", 58000, 43500, 16, 1200),
    ("Paket Coba Produk GreenLoop", "Paket pengenalan berisi sabun batang, sabun cuci piring, dan pembersih serbaguna.", 68000, 51000, 15, 1200),
]


def seed_products(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for name, description, price_b2c, price_b2b, stock, weight_grams in PRODUCTS:
        Product.objects.using(schema_editor.connection.alias).get_or_create(
            name=name,
            defaults={
                "description": description,
                "price_b2c": price_b2c,
                "price_b2b": price_b2b,
                "stock": stock,
                "weight_grams": weight_grams,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0008_product_weight_grams")]

    operations = [migrations.RunPython(seed_products, migrations.RunPython.noop)]
