"""Test: pikap yang dimulai atau diselesaikan masuk ke Riwayat Pikap."""
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from courier.models import PickupRecord, WeightLog
from scheduling.models import PickupSchedule
from courier.utils import get_pickup_history

from .helpers import make_approved_courier
from .test_route import RouteTestBase


class PickupRecordTests(RouteTestBase):
    def history(self):
        return self.client.get(reverse("courier:show_history"))

    def test_start_creates_ongoing_record(self):
        pk = self.ids()[0]
        self.start(pk)
        rec = PickupRecord.objects.get(courier=self.user)
        point = PickupSchedule.objects.get(pk=pk)
        self.assertEqual(rec.status, "ongoing")
        self.assertEqual(rec.pickup_schedule_id, point.pk)
        self.assertEqual(rec.partner_name, point.mitra.profile.business_name)
        self.assertEqual(rec.date, timezone.localdate())
        self.assertRegex(rec.slot, r"^\d{2}\.\d{2}–\d{2}\.\d{2}$")
        self.assertIsNone(rec.actual_kg)

    def test_finish_marks_record_done_with_weight(self):
        pk = self.ids()[0]
        self.start(pk)
        self.finish(pk, "4,5")
        self.assertEqual(PickupRecord.objects.filter(courier=self.user).count(), 1)  # diperbarui, bukan double
        rec = PickupRecord.objects.get(courier=self.user)
        self.assertEqual(rec.status, "done")
        self.assertEqual(rec.actual_kg, Decimal("4.5"))
        self.assertIsNotNone(rec.finished_at)

    def test_finish_without_start_is_rejected(self):
        pk = self.ids()[0]
        res = self.client.post(reverse("courier:finish_pickup", args=[pk]), {"weight_kg": "3"})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(PickupRecord.objects.filter(courier=self.user).exists())

    def test_finish_still_writes_weight_log(self):
        self.finish(self.ids()[0], "3")
        self.assertEqual(WeightLog.objects.filter(courier=self.user).count(), 1)

    def test_invalid_weight_creates_no_record(self):
        pk = self.ids()[0]
        self.assertEqual(self.finish(pk, "abc").status_code, 400)
        self.assertEqual(PickupRecord.objects.get().status, "ongoing")
        self.assertFalse(WeightLog.objects.exists())

    def test_switching_target_reverts_previous_to_scheduled(self):
        a, b = self.ids()[:2]
        self.start(a)
        self.start(b)
        status = {r.code: r.status for r in PickupRecord.objects.all()}
        self.assertEqual(status[f"PK-{a:04d}"], "scheduled")
        self.assertEqual(status[f"PK-{b:04d}"], "ongoing")

    def test_done_stop_cannot_be_restarted_and_record_stays_done(self):
        pk = self.ids()[0]
        self.finish(pk, "2")
        self.assertEqual(self.start(pk).status_code, 400)
        self.assertEqual(PickupRecord.objects.get().status, "done")

    def test_history_page_shows_real_records_not_samples(self):
        pk = self.ids()[0]
        self.finish(pk, "4,5")
        res = self.history()
        point = PickupSchedule.objects.get(pk=pk)
        self.assertContains(res, f"PK-{pk:04d}")
        self.assertContains(res, point.mitra.profile.business_name)
        self.assertContains(res, "4,5 kg")
        self.assertContains(res, "Selesai")
        self.assertNotContains(res, "PK-9999")          # tidak ada data contoh
        self.assertEqual(res.context["total"], 1)
        counts = {key: n for key, _, n in res.context["filters"]}
        self.assertEqual(counts["done"], 1)
        self.assertEqual(counts["ongoing"], 0)

    def test_history_shows_ongoing_status(self):
        self.start(self.ids()[0])
        rows = get_pickup_history(self.user)
        self.assertEqual([r["status"] for r in rows], ["ongoing"])
        self.assertEqual(rows[0]["actual_display"], "–")

    def test_history_newest_first(self):
        old = PickupRecord.objects.create(
            courier=self.user, code="TJ-9", date=timezone.localdate() - timezone.timedelta(days=3),
            partner_name="Lama", status="done", actual_kg=Decimal("1.0"))
        self.finish(self.ids()[0], "2")
        codes = [r["code"] for r in get_pickup_history(self.user)]
        self.assertEqual(codes[-1], old.code)

    def test_no_records_means_empty_history(self):
        self.assertEqual(get_pickup_history(self.user), [])
        res = self.history()
        self.assertEqual(res.context["total"], 0)
        self.assertNotContains(res, "PK-0")

    def test_records_are_per_courier(self):
        self.finish(self.ids()[0], "2")
        other = make_approved_courier("andi")
        self.client.force_login(other)
        res = self.history()
        self.assertEqual(res.context["total"], 0)
        self.assertFalse(PickupRecord.objects.filter(courier=other).exists())

    def test_same_stop_only_once_per_day(self):
        pk = self.ids()[0]
        self.start(pk)
        self.start(pk)
        self.finish(pk, "2")
        self.assertEqual(PickupRecord.objects.filter(courier=self.user).count(), 1)