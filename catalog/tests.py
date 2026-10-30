from django.test import TestCase

from catalog.models import Product


class InitialCatalogDataTests(TestCase):
    def test_at_least_fifty_greenloop_products_are_seeded(self):
        self.assertGreaterEqual(Product.objects.count(), 50)

    def test_seeded_products_have_sellable_price_stock_and_shipping_weight(self):
        product = Product.objects.get(name="Sabun Batang Eco-Enzyme Jeruk Nipis 80 g")
        self.assertGreater(product.price_b2c, 0)
        self.assertGreater(product.price_b2b, 0)
        self.assertGreater(product.stock, 0)
        self.assertGreater(product.weight_grams, 0)
