"""
Tests cho module harvests – kiểm tra BR-08 → BR-13.

BR-08: Không tạo lô khi harvest_date < phi_safe_date
       4 trường hợp PHI:
       - Phun cùng ngày thu hoạch
       - Nhật ký phun không gắn vụ
       - Nhật ký phun thuộc vụ cũ
       - Thuốc BVTV trong nhật ký loại khác SPRAY
       + OWNER override PHI
BR-09: batch_code phải duy nhất trong vườn
BR-10: remaining_kg không âm, không vượt total_kg (constraint DB)
BR-11: Không hủy lô đã có phiếu bán (remaining_kg < total_kg)
BR-12: Kết quả kiểm nghiệm phải là PASS hoặc FAIL
BR-13: Trạng thái lô cập nhật theo kết quả kiểm nghiệm mới nhất (tested_date)
"""
from datetime import date, timedelta

from django.db.utils import IntegrityError

from tests.base import BaseTest
from harvests.models import HarvestBatch, BatchStock, LabTest
from harvests.services import compute_phi_safe_date, create_batch, void_batch, add_lab_test, void_lab_test

from common.exceptions import DomainError
from common.models import AuditLog
from logs.models import FarmLog, FarmLogInput

API = "/api/v1"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
STOCKS_OK = [{"grade": "GRADE_1", "qty_kg": "100.00"}]


def make_spray_log(test_case, activity_date, phi_days=14, season=None,
                   activity_type=FarmLog.Activity.SPRAY):
    """Tạo nhật ký kèm thuốc BVTV.

    Mặc định: SPRAY, trong lô A mùa A.  Có thể override season và activity_type.
    """
    tc = test_case
    log = FarmLog.objects.create(
        plot=tc.plot_a,
        season=season if season is not None else tc.season_a,
        activity_type=activity_type,
        activity_date=activity_date,
        created_by=tc.owner_a,
    )
    FarmLogInput.objects.create(
        log=log,
        product=tc.spray,
        quantity=1,
        unit_cost=100_000,
        total_cost=100_000,
    )
    return log


def make_batch(test_case, harvest_date=None, batch_code="LOT-001", stocks=None,
               override_reason="", user_role=""):
    """Tạo HarvestBatch cho vườn A, lô A, mùa A."""
    tc = test_case
    return create_batch(
        farm=tc.farm_a,
        plot=tc.plot_a,
        season=tc.season_a,
        user=tc.owner_a,
        batch_code=batch_code,
        harvest_date=harvest_date or TODAY,
        stocks=stocks or STOCKS_OK,
        override_reason=override_reason,
        user_role=user_role,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BR-08: PHI check (compute + block + 4 lỗ hổng + override)
# ─────────────────────────────────────────────────────────────────────────────

class PhiComputeTest(BaseTest):
    """BR-08: compute_phi_safe_date tính đúng ngày cách ly."""

    def test_no_spray_returns_none(self):
        """Không có nhật ký phun → phi_safe_date = None."""
        result = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNone(result)

    def test_single_spray(self):
        """phi_safe = spray_date + phi_days."""
        spray_date = TODAY - timedelta(days=10)
        make_spray_log(self, spray_date)   # spray có phi_days=14
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertEqual(phi, spray_date + timedelta(days=14))

    def test_latest_spray_wins(self):
        """Nhiều lần phun → lấy ngày cách ly muộn nhất."""
        early = TODAY - timedelta(days=20)
        late = TODAY - timedelta(days=5)
        make_spray_log(self, early)
        make_spray_log(self, late)
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertEqual(phi, late + timedelta(days=14))

    def test_voided_log_excluded(self):
        """Nhật ký đã hủy không được tính vào PHI."""
        spray_date = TODAY - timedelta(days=5)
        log = make_spray_log(self, spray_date)
        log.status = FarmLog.Status.VOIDED
        log.save(update_fields=["status"])
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNone(phi)

    def test_other_plot_excluded(self):
        """Nhật ký của lô khác không được tính."""
        spray_date = TODAY - timedelta(days=5)
        # Tạo log cho plot_b (khác vườn)
        log = FarmLog.objects.create(
            plot=self.plot_b,
            activity_type=FarmLog.Activity.SPRAY,
            activity_date=spray_date,
            created_by=self.owner_b,
        )
        FarmLogInput.objects.create(log=log, product=self.spray, quantity=1,
                                    unit_cost=0, total_cost=0)
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNone(phi)

    # ── Bốn lỗ hổng PHI đã sửa ──────────────────────────────────────────────

    def test_same_day_spray_included(self):
        """Phun thuốc cùng ngày thu hoạch → phi_safe_date phải có giá trị (dùng __lte)."""
        make_spray_log(self, TODAY)
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNotNone(phi)
        self.assertEqual(phi, TODAY + timedelta(days=14))

    def test_no_season_spray_included(self):
        """Nhật ký phun không gắn vụ vẫn được tính vào PHI."""
        spray_date = TODAY - timedelta(days=5)
        make_spray_log(self, spray_date, season=None)  # không gắn vụ
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNotNone(phi)
        self.assertEqual(phi, spray_date + timedelta(days=14))

    def test_old_season_spray_included(self):
        """Nhật ký phun thuộc vụ cũ vẫn được tính vào PHI (spec: mọi lần dùng thuốc trên lô)."""
        from farms.models import Season
        old_season = Season.objects.create(
            farm=self.farm_a, name="Vụ cũ 2025", status="COMPLETED",
            start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        )
        spray_date = TODAY - timedelta(days=5)
        make_spray_log(self, spray_date, season=old_season)
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNotNone(phi)
        self.assertEqual(phi, spray_date + timedelta(days=14))

    def test_non_spray_activity_pesticide_included(self):
        """Thuốc BVTV trong nhật ký loại khác SPRAY (vd: OTHER) vẫn được tính vào PHI."""
        spray_date = TODAY - timedelta(days=5)
        make_spray_log(self, spray_date, activity_type=FarmLog.Activity.OTHER)
        phi = compute_phi_safe_date(self.plot_a.id, TODAY)
        self.assertIsNotNone(phi)
        self.assertEqual(phi, spray_date + timedelta(days=14))


class PhiBlockCreateTest(BaseTest):
    """BR-08: Không tạo lô khi harvest_date < phi_safe_date."""

    def test_cannot_harvest_before_phi(self):
        """Phun thuốc hôm qua → cần chờ 14 ngày → hôm nay không được thu hoạch."""
        make_spray_log(self, YESTERDAY)
        with self.assertRaises(DomainError) as cm:
            make_batch(self, harvest_date=TODAY)
        self.assertEqual(cm.exception.code_str, "phi_not_elapsed")

    def test_cannot_harvest_same_day_as_spray(self):
        """Phun thuốc cùng ngày thu hoạch → chặn (phi_days > 0)."""
        make_spray_log(self, TODAY)
        with self.assertRaises(DomainError) as cm:
            make_batch(self, harvest_date=TODAY)
        self.assertEqual(cm.exception.code_str, "phi_not_elapsed")

    def test_can_harvest_after_phi(self):
        """Phun đủ 14 ngày trước → được thu hoạch."""
        spray_date = TODAY - timedelta(days=15)
        make_spray_log(self, spray_date)
        batch = make_batch(self, harvest_date=TODAY)
        self.assertIsNotNone(batch.pk)
        # phi_safe_date được lưu đúng
        self.assertEqual(batch.phi_safe_date, spray_date + timedelta(days=14))

    def test_no_pesticide_no_block(self):
        """Không có thuốc BVTV → không bị chặn."""
        # Chỉ có nhật ký bón phân, không có phun thuốc
        FarmLog.objects.create(
            plot=self.plot_a, season=self.season_a,
            activity_type=FarmLog.Activity.FERTILIZE,
            activity_date=YESTERDAY, created_by=self.owner_a,
        )
        batch = make_batch(self, harvest_date=TODAY)
        self.assertIsNone(batch.phi_safe_date)


class PhiOverrideTest(BaseTest):
    """BR-08: OWNER override PHI."""

    def test_owner_override_allows_harvest(self):
        """OWNER cung cấp override_reason → được thu hoạch dù chưa hết PHI + ghi audit."""
        make_spray_log(self, YESTERDAY)
        batch = make_batch(
            self, harvest_date=TODAY,
            override_reason="Khách hàng cần gấp",
            user_role="OWNER",
        )
        self.assertIsNotNone(batch.pk)
        self.assertEqual(batch.override_reason, "Khách hàng cần gấp")
        # phi_safe_date vẫn được lưu để audit
        self.assertIsNotNone(batch.phi_safe_date)
        # Audit log phải có PHI_OVERRIDE
        self.assertTrue(
            AuditLog.objects.filter(
                action="PHI_OVERRIDE", entity_id=batch.pk,
            ).exists()
        )
        log_entry = AuditLog.objects.get(action="PHI_OVERRIDE", entity_id=batch.pk)
        self.assertEqual(log_entry.metadata["override_reason"], "Khách hàng cần gấp")

    def test_worker_cannot_override(self):
        """WORKER cung cấp override_reason nhưng vẫn bị chặn."""
        make_spray_log(self, YESTERDAY)
        with self.assertRaises(DomainError) as cm:
            make_batch(
                self, harvest_date=TODAY,
                override_reason="Muốn gấp",
                user_role="WORKER",
            )
        self.assertEqual(cm.exception.code_str, "phi_not_elapsed")

    def test_no_reason_no_override(self):
        """OWNER không cung cấp lý do → bị chặn như bình thường."""
        make_spray_log(self, YESTERDAY)
        with self.assertRaises(DomainError) as cm:
            make_batch(
                self, harvest_date=TODAY,
                override_reason="",
                user_role="OWNER",
            )
        self.assertEqual(cm.exception.code_str, "phi_not_elapsed")


# ─────────────────────────────────────────────────────────────────────────────
# BR-09: batch_code unique per farm
# ─────────────────────────────────────────────────────────────────────────────

class BatchCodeUniqueTest(BaseTest):
    """BR-09: batch_code phải duy nhất trong vườn."""

    def test_duplicate_code_same_farm(self):
        """Mã lô trùng trong cùng vườn → DomainError."""
        make_batch(self, batch_code="LOT-001")
        with self.assertRaises(DomainError) as cm:
            make_batch(self, batch_code="LOT-001")
        self.assertEqual(cm.exception.code_str, "duplicate_batch_code")

    def test_same_code_different_farm(self):
        """Mã lô trùng nhưng khác vườn → được phép."""
        make_batch(self, batch_code="LOT-001")
        batch_b = create_batch(
            farm=self.farm_b, plot=self.plot_b, season=None,
            user=self.owner_b, batch_code="LOT-001",
            harvest_date=TODAY, stocks=STOCKS_OK,
        )
        self.assertIsNotNone(batch_b.pk)

    def test_unique_code_ok(self):
        """Mã khác nhau trong cùng vườn → ok."""
        make_batch(self, batch_code="LOT-001")
        batch2 = make_batch(self, batch_code="LOT-002")
        self.assertIsNotNone(batch2.pk)


# ─────────────────────────────────────────────────────────────────────────────
# BR-10: Tồn kho (DB constraint)
# ─────────────────────────────────────────────────────────────────────────────

class StockConstraintTest(BaseTest):
    """BR-10: remaining_kg không âm, không vượt total_kg."""

    def test_remaining_cannot_be_negative(self):
        batch = make_batch(self)
        batch.remaining_kg = -1
        with self.assertRaises(IntegrityError):
            batch.save()

    def test_remaining_cannot_exceed_total(self):
        batch = make_batch(self)
        batch.remaining_kg = batch.total_kg + 1
        with self.assertRaises(IntegrityError):
            batch.save()

    def test_stock_qty_must_be_positive(self):
        batch = make_batch(self)
        stock = batch.stocks.first()
        stock.qty_kg = 0
        with self.assertRaises(IntegrityError):
            stock.save()


# ─────────────────────────────────────────────────────────────────────────────
# BR-11: Không hủy lô đã có phiếu bán
# ─────────────────────────────────────────────────────────────────────────────

class VoidBatchTest(BaseTest):
    """BR-11: Hủy lô."""

    def test_void_clean_batch(self):
        """Lô sạch (chưa bán) → được hủy + ghi audit."""
        batch = make_batch(self)
        void_batch(batch=batch, user=self.owner_a, reason="Kiểm tra")
        batch.refresh_from_db()
        self.assertEqual(batch.status, HarvestBatch.Status.VOIDED)
        self.assertEqual(batch.void_reason, "Kiểm tra")
        # Audit log phải có BATCH_VOID
        self.assertTrue(
            AuditLog.objects.filter(
                action="BATCH_VOID", entity_id=batch.pk,
            ).exists()
        )

    def test_void_with_sales_blocked(self):
        """Lô đã xuất một phần (remaining_kg < total_kg) → từ chối hủy."""
        batch = make_batch(self)
        # Giả lập đã bán bớt một phần
        batch.remaining_kg -= 10
        batch.save(update_fields=["remaining_kg"])
        with self.assertRaises(DomainError) as cm:
            void_batch(batch=batch, user=self.owner_a, reason="Test")
        self.assertEqual(cm.exception.code_str, "batch_has_sales")

    def test_void_already_voided(self):
        """Hủy lần 2 → lỗi."""
        batch = make_batch(self)
        void_batch(batch=batch, user=self.owner_a, reason="Lần 1")
        with self.assertRaises(DomainError) as cm:
            void_batch(batch=batch, user=self.owner_a, reason="Lần 2")
        self.assertEqual(cm.exception.code_str, "already_voided")


# ─────────────────────────────────────────────────────────────────────────────
# BR-12 / BR-13: Kiểm nghiệm
# ─────────────────────────────────────────────────────────────────────────────

class LabTestTest(BaseTest):
    """BR-12: result chỉ nhận PASS/FAIL; BR-13: trạng thái lô cập nhật."""

    def setUp(self):
        super().setUp()
        self.batch = make_batch(self)

    def test_pass_sets_batch_passed(self):
        """Kiểm nghiệm PASS → batch.status = PASSED (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY, lab_name="Lab Sài Gòn", result=LabTest.Result.PASS,
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, HarvestBatch.Status.PASSED)

    def test_fail_sets_batch_failed(self):
        """Kiểm nghiệm FAIL → batch.status = FAILED (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY, lab_name="Lab Sài Gòn", result=LabTest.Result.FAIL,
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, HarvestBatch.Status.FAILED)

    def test_retest_overrides_status(self):
        """Kiểm lại với kết quả khác → trạng thái cập nhật theo kết quả mới nhất (BR-13)."""
        add_lab_test(batch=self.batch, user=self.owner_a,
                     tested_date=TODAY - timedelta(days=2), lab_name="Lab A",
                     result=LabTest.Result.PASS)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, HarvestBatch.Status.PASSED)

        add_lab_test(batch=self.batch, user=self.owner_a,
                     tested_date=TODAY, lab_name="Lab A", result=LabTest.Result.FAIL)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, HarvestBatch.Status.FAILED)

    def test_status_by_tested_date_not_insert_order(self):
        """Trạng thái lô theo tested_date chứ không phải thứ tự nhập.

        FAIL hôm nay rồi nhập PASS cũ 30 ngày → lô vẫn FAILED.
        """
        # Nhập FAIL hôm nay
        add_lab_test(batch=self.batch, user=self.owner_a,
                     tested_date=TODAY, lab_name="Lab A", result=LabTest.Result.FAIL)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, HarvestBatch.Status.FAILED)

        # Nhập PASS 30 ngày trước (insert order sau, nhưng tested_date cũ hơn)
        add_lab_test(batch=self.batch, user=self.owner_a,
                     tested_date=TODAY - timedelta(days=30), lab_name="Lab B",
                     result=LabTest.Result.PASS)
        self.batch.refresh_from_db()
        # Lô phải vẫn FAILED vì kết quả MỚI NHẤT theo tested_date là FAIL
        self.assertEqual(self.batch.status, HarvestBatch.Status.FAILED)

    def test_cannot_add_test_to_voided_batch(self):
        """Lô đã hủy không nhận kiểm nghiệm mới."""
        void_batch(batch=self.batch, user=self.owner_a, reason="Hỏng")
        with self.assertRaises(DomainError) as cm:
            add_lab_test(batch=self.batch, user=self.owner_a,
                         tested_date=TODAY, lab_name="Lab", result=LabTest.Result.PASS)
        self.assertEqual(cm.exception.code_str, "batch_voided")

    def test_parameters_json_saved(self):
        """Dữ liệu JSON kiểm nghiệm được lưu đúng."""
        params = {"cadmium_ppm": 0.01, "chlorpyrifos_ppm": 0.005}
        test = add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY, lab_name="Lab B", result=LabTest.Result.PASS,
            parameters_json=params,
        )
        test.refresh_from_db()
        self.assertEqual(test.parameters_json["cadmium_ppm"], 0.01)


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

class HarvestBatchAPITest(BaseTest):
    """Test API endpoint /farms/{farm_id}/harvest-batches/."""

    def _batch_url(self, farm=None, pk=None):
        f = farm or self.farm_a
        base = f"{API}/farms/{f.id}/harvest-batches/"
        return f"{base}{pk}/" if pk else base

    def test_create_batch_owner(self):
        """OWNER tạo lô thành công."""
        self.login(self.owner_a)
        payload = {
            "plot": self.plot_a.id,
            "season": self.season_a.id,
            "batch_code": "API-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "80.00"}, {"grade": "GRADE_2", "qty_kg": "20.00"}],
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["batch_code"], "API-001")
        self.assertEqual(len(r.data["stocks"]), 2)

    def test_create_batch_worker(self):
        """WORKER cũng được tạo lô."""
        self.login(self.worker_a)
        payload = {
            "plot": self.plot_a.id,
            "batch_code": "W-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_3", "qty_kg": "50.00"}],
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_advisor_cannot_create(self):
        """ADVISOR chỉ đọc, không tạo được lô."""
        self.login(self.advisor_a)
        payload = {
            "plot": self.plot_a.id,
            "batch_code": "ADV-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "10.00"}],
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cross_farm_blocked(self):
        """Owner B không thể tạo lô cho Farm A."""
        self.login(self.owner_b)
        payload = {
            "plot": self.plot_a.id,
            "batch_code": "CROSS-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "10.00"}],
        }
        r = self.client.post(self._batch_url(self.farm_a), payload, format="json")
        self.assertEqual(r.status_code, 403)

    def test_phi_block_via_api(self):
        """Phun hôm qua → API trả 409."""
        make_spray_log(self, YESTERDAY)
        self.login(self.owner_a)
        payload = {
            "plot": self.plot_a.id,
            "season": self.season_a.id,
            "batch_code": "PHI-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "50.00"}],
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 409)

    def test_phi_override_via_api(self):
        """OWNER override PHI qua API."""
        make_spray_log(self, YESTERDAY)
        self.login(self.owner_a)
        payload = {
            "plot": self.plot_a.id,
            "season": self.season_a.id,
            "batch_code": "PHI-OVERRIDE",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "50.00"}],
            "override_reason": "Khách hàng yêu cầu giao gấp",
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["override_reason"], "Khách hàng yêu cầu giao gấp")

    def test_duplicate_code_via_api(self):
        """Mã lô trùng → 409."""
        make_batch(self, batch_code="DUP-001")
        self.login(self.owner_a)
        payload = {
            "plot": self.plot_a.id,
            "batch_code": "DUP-001",
            "harvest_date": str(TODAY),
            "stocks": [{"grade": "GRADE_1", "qty_kg": "30.00"}],
        }
        r = self.client.post(self._batch_url(), payload, format="json")
        self.assertEqual(r.status_code, 409)

    def test_void_via_api(self):
        """OWNER hủy lô qua API."""
        batch = make_batch(self)
        self.login(self.owner_a)
        r = self.client.post(
            f"{self._batch_url(pk=batch.id)}void/",
            {"reason": "Lô bị hỏng"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "VOIDED")

    def test_add_lab_test_via_api(self):
        """OWNER thêm kết quả kiểm nghiệm → batch chuyển PASSED."""
        batch = make_batch(self)
        self.login(self.owner_a)
        r = self.client.post(
            f"{self._batch_url(pk=batch.id)}lab-tests/",
            {"tested_date": str(TODAY), "lab_name": "Lab Mekong",
             "result": "PASS", "parameters_json": {"cadmium_ppm": 0.02}},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["batch"]["status"], "PASSED")

    def test_list_lab_tests_via_api(self):
        """GET /lab-tests/ trả về danh sách kiểm nghiệm (không bị 405)."""
        batch = make_batch(self)
        add_lab_test(batch=batch, user=self.owner_a, tested_date=TODAY,
                     lab_name="Lab A", result=LabTest.Result.PASS)
        self.login(self.owner_a)
        r = self.client.get(f"{self._batch_url(pk=batch.id)}lab-tests/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsInstance(r.data, list)
        self.assertEqual(len(r.data), 1)

    def test_list_requires_auth(self):
        """Không xác thực → 401."""
        r = self.client.get(self._batch_url())
        self.assertEqual(r.status_code, 401)

    def test_filter_by_status(self):
        """Lọc theo status."""
        batch = make_batch(self)
        add_lab_test(batch=batch, user=self.owner_a, tested_date=TODAY,
                     lab_name="Lab", result=LabTest.Result.PASS)
        self.login(self.owner_a)
        r = self.client.get(self._batch_url() + "?status=PASSED")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)

    def test_worker_can_add_lab_test(self):
        """WORKER có quyền thêm kết quả kiểm nghiệm (khớp đặc tả OWNER + WORKER)."""
        batch = make_batch(self)
        self.login(self.worker_a)
        r = self.client.post(
            f"{self._batch_url(pk=batch.id)}lab-tests/",
            {
                "tested_date": str(TODAY),
                "lab_name": "Lab Cần Thơ",
                "result": "PASS",
                "analyte": "Cadmium",
                "result_value": "0.0200",
                "limit_value": "0.0500",
                "valid_until": str(TODAY + timedelta(days=90)),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["batch"]["status"], "PASSED")
        self.assertEqual(r.data["lab_test"]["analyte"], "Cadmium")
        self.assertEqual(r.data["lab_test"]["status"], "ACTIVE")

    def test_void_lab_test_reverts_batch_status(self):
        """Hủy kết quả kiểm nghiệm duy nhất khiến lô trở về PENDING (BR-13)."""
        batch = make_batch(self)
        t = add_lab_test(batch=batch, user=self.owner_a, tested_date=TODAY,
                         lab_name="Lab Test", result=LabTest.Result.PASS)
        batch.refresh_from_db()
        self.assertEqual(batch.status, HarvestBatch.Status.PASSED)

        self.login(self.owner_a)
        r = self.client.post(
            f"{self._batch_url(pk=batch.id)}lab-tests/{t.id}/void/",
            {"reason": "Nhầm số liệu mẫu"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        batch.refresh_from_db()
        self.assertEqual(batch.status, HarvestBatch.Status.PENDING)
        t.refresh_from_db()
        self.assertEqual(t.status, LabTest.Status.VOIDED)

    def test_batches_url_alias(self):
        """URL /farms/{id}/batches/ hoạt động như /farms/{id}/harvest-batches/ (thống nhất URL)."""
        make_batch(self)
        self.login(self.owner_a)
        r = self.client.get(f"{API}/farms/{self.farm_a.id}/batches/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 1)

