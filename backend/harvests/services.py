"""
Services cho module harvests.

Các hàm nghiệp vụ chính:
- compute_phi_safe_date: tính ngày cách ly PHI từ nhật ký phun thuốc của lô (mọi vụ)
- create_batch: tạo lô thu hoạch kèm kiểm tra BR-08 (PHI), BR-09 (unique code)
- void_batch: hủy lô (BR-11: từ chối nếu đã có phiếu bán)
- add_lab_test: thêm kết quả kiểm nghiệm và cập nhật trạng thái lô (BR-12, BR-13)
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from common.exceptions import DomainError
from common.models import audit
from logs.models import FarmLog, FarmLogInput


def compute_phi_safe_date(plot_id: int, before_date: date) -> Optional[date]:
    """
    Tính ngày cách ly PHI an toàn cho một lô đất.

    Theo spec (BR-08): "mọi lần dùng thuốc có phi_days trên lô" – không giới hạn
    theo mùa vụ hay loại nhật ký. Chỉ cần sản phẩm là PESTICIDE có phi_days.

    Bao gồm cả nhật ký phun cùng ngày thu hoạch (dùng __lte thay vì __lt).

    Returns:
        Ngày cách ly an toàn (phi_safe_date) hoặc None nếu không có thuốc BVTV.
    """
    qs = (FarmLogInput.objects
          .filter(
              log__plot_id=plot_id,
              log__status=FarmLog.Status.ACTIVE,
              log__activity_date__lte=before_date,   # <= thay vì < : phun cùng ngày cũng tính
              product__kind="PESTICIDE",
              product__phi_days__isnull=False,
          )
          .select_related("product", "log"))
    # Không filter theo season_id hay activity_type:
    # spec nói "mọi lần dùng thuốc có phi_days trên lô", không phân biệt vụ hay loại nhật ký.

    phi_safe: Optional[date] = None
    for item in qs:
        candidate = item.log.activity_date + timedelta(days=item.product.phi_days)
        if phi_safe is None or candidate > phi_safe:
            phi_safe = candidate
    return phi_safe


@transaction.atomic
def create_batch(
    farm,
    plot,
    season,
    user,
    batch_code: str,
    harvest_date: date,
    stocks: list,        # [{"grade": "A", "qty_kg": 100, ...}, ...]
    note: str = "",
    override_reason: str = "",
    user_role: str = "",
) -> "HarvestBatch":
    """
    Tạo mới lô thu hoạch.

    BR-08: Kiểm tra ngày cách ly PHI. Nếu vi phạm:
           - OWNER có thể override bằng cách cung cấp override_reason (audit trail).
           - Vai trò khác bị chặn cứng.
    BR-09: batch_code phải duy nhất trong vườn (ràng buộc DB + lỗi thân thiện).

    Args:
        stocks: danh sách dict {grade, qty_kg, estimated_price_per_kg?}
        override_reason: lý do OWNER override ngày cách ly (bỏ trống = không override)
        user_role: vai trò hiện tại ("OWNER", "WORKER", ...)

    Returns:
        HarvestBatch đã lưu.

    Raises:
        DomainError: vi phạm BR-08, BR-09 hoặc dữ liệu không hợp lệ.
    """
    from .models import BatchStock, HarvestBatch

    # ── BR-08: kiểm tra PHI ──────────────────────────────────────────────────
    phi_safe = compute_phi_safe_date(
        plot_id=plot.id,
        before_date=harvest_date,
    )
    phi_violated = phi_safe is not None and harvest_date < phi_safe

    if phi_violated:
        if override_reason and user_role == "OWNER":
            # OWNER override – cho phép nhưng ghi audit (xử lý sau khi tạo batch)
            pass
        else:
            raise DomainError(
                "phi_not_elapsed",
                f"Ngày thu hoạch {harvest_date} chưa qua ngày cách ly PHI an toàn ({phi_safe}). "
                "Vui lòng chờ hoặc kiểm tra lại lịch phun thuốc."
                + (" Chỉ OWNER có thể override với lý do hợp lệ." if not override_reason else ""),
                409,
            )

    # ── Kiểm tra stocks ──────────────────────────────────────────────────────
    if not stocks:
        raise DomainError("stocks_empty", "Lô thu hoạch phải có ít nhất một dòng phân loại.", 400)

    total_kg = sum(Decimal(str(s["qty_kg"])) for s in stocks)
    if total_kg <= 0:
        raise DomainError("total_kg_zero", "Tổng sản lượng phải lớn hơn 0.", 400)

    # ── BR-09: Kiểm tra trùng batch_code TRƯỚC khi insert ───────────────────
    if HarvestBatch.objects.filter(farm=farm, batch_code=batch_code).exists():
        raise DomainError(
            "duplicate_batch_code",
            f"Mã lô '{batch_code}' đã tồn tại trong vườn này.",
            409,
        )

    # ── Tạo batch ────────────────────────────────────────────────────────────
    # Khi OWNER override: phi_safe_date vẫn được lưu để audit, nhưng DB constraint
    # cần cho phép harvest_date < phi_safe_date khi có override_reason.
    batch = HarvestBatch.objects.create(
        farm=farm,
        plot=plot,
        season=season,
        batch_code=batch_code,
        harvest_date=harvest_date,
        phi_safe_date=phi_safe,
        total_kg=total_kg,
        remaining_kg=total_kg,
        note=note,
        override_reason=override_reason if phi_violated else "",
        created_by=user,
    )

    # ── Tạo BatchStock ───────────────────────────────────────────────────────
    stock_objs = []
    for s in stocks:
        qty = Decimal(str(s["qty_kg"]))
        stock_objs.append(BatchStock(
            batch=batch,
            grade=s["grade"],
            qty_kg=qty,
            remaining_kg=qty,
            estimated_price_per_kg=s.get("estimated_price_per_kg"),
        ))
    BatchStock.objects.bulk_create(stock_objs)

    # Audit: BR-08 PHI override
    if phi_violated and override_reason and user_role == "OWNER":
        audit(
            farm=farm, actor=user, action="PHI_OVERRIDE",
            entity=batch,
            override_reason=override_reason,
            phi_safe_date=str(phi_safe),
            harvest_date=str(harvest_date),
        )

    return batch


@transaction.atomic
def void_batch(batch, user, reason: str) -> None:
    """
    Hủy lô thu hoạch.

    BR-11: Từ chối nếu lô đã có phiếu bán (remaining_kg < total_kg).
    """
    from .models import HarvestBatch

    if batch.status == HarvestBatch.Status.VOIDED:
        raise DomainError("already_voided", "Lô này đã bị hủy trước đó.", 409)

    # BR-11: kiểm tra đã có giao dịch bán chưa
    if batch.remaining_kg < batch.total_kg:
        raise DomainError(
            "batch_has_sales",
            "Không thể hủy lô đã có phiếu bán. "
            "Vui lòng hủy các phiếu bán trước.",
            409,
        )

    batch.status = HarvestBatch.Status.VOIDED
    batch.void_reason = reason
    batch.voided_by = user
    batch.voided_at = timezone.now()
    batch.save(update_fields=["status", "void_reason", "voided_by", "voided_at", "updated_at"])

    # Audit trail
    audit(
        farm=batch.farm, actor=user, action="BATCH_VOID",
        entity=batch, reason=reason,
    )


@transaction.atomic
def add_lab_test(batch, user, tested_date: date, lab_name: str, result: str,
                 parameters_json: dict = None, certificate_url: str = "",
                 note: str = "", analyte: str = "", result_value=None,
                 limit_value=None, valid_until=None) -> "LabTest":
    """
    Thêm kết quả kiểm nghiệm và cập nhật trạng thái lô.

    BR-12: result bắt buộc là PASS hoặc FAIL (xác nhận tại serializer).
    BR-13: Cập nhật batch.status dựa theo kết quả kiểm nghiệm ACTIVE mới nhất
           (xác định bằng tested_date DESC, id DESC).
           - Kết quả mới nhất PASS → batch PASSED
           - Kết quả mới nhất FAIL → batch FAILED
    """
    from .models import HarvestBatch, LabTest

    if batch.status == HarvestBatch.Status.VOIDED:
        raise DomainError("batch_voided", "Không thể thêm kiểm nghiệm cho lô đã hủy.", 409)

    test = LabTest.objects.create(
        batch=batch,
        tested_date=tested_date,
        lab_name=lab_name,
        result=result,
        analyte=analyte,
        result_value=result_value,
        limit_value=limit_value,
        valid_until=valid_until,
        parameters_json=parameters_json or {},
        certificate_url=certificate_url,
        note=note,
        created_by=user,
    )

    # BR-13: Trạng thái lô theo kết quả kiểm nghiệm ACTIVE MỚI NHẤT (tested_date, id)
    latest = (LabTest.objects
              .filter(batch=batch, status=LabTest.Status.ACTIVE)
              .order_by("-tested_date", "-id")
              .first())

    if latest is None:
        new_status = HarvestBatch.Status.PENDING
    elif latest.result == LabTest.Result.PASS:
        new_status = HarvestBatch.Status.PASSED
    else:
        new_status = HarvestBatch.Status.FAILED

    if batch.status != new_status:
        batch.status = new_status
        batch.save(update_fields=["status", "updated_at"])

    return test


@transaction.atomic
def void_lab_test(lab_test, user, reason: str) -> None:
    """
    Hủy kết quả kiểm nghiệm và cập nhật lại trạng thái lô thu hoạch (BR-13).

    Raises:
        DomainError: kiểm nghiệm đã hủy trước đó.
    """
    from .models import HarvestBatch, LabTest

    if lab_test.status == LabTest.Status.VOIDED:
        raise DomainError("already_voided", "Kết quả kiểm nghiệm này đã bị hủy trước đó.", 409)

    lab_test.status = LabTest.Status.VOIDED
    lab_test.void_reason = reason
    lab_test.voided_by = user
    lab_test.voided_at = timezone.now()
    lab_test.save(update_fields=["status", "void_reason", "voided_by", "voided_at"])

    # Tính lại trạng thái batch từ các test còn ACTIVE
    batch = lab_test.batch
    latest_active = (LabTest.objects
                     .filter(batch=batch, status=LabTest.Status.ACTIVE)
                     .order_by("-tested_date", "-id")
                     .first())

    if latest_active is None:
        new_status = HarvestBatch.Status.PENDING
    elif latest_active.result == LabTest.Result.PASS:
        new_status = HarvestBatch.Status.PASSED
    else:
        new_status = HarvestBatch.Status.FAILED

    if batch.status != new_status:
        batch.status = new_status
        batch.save(update_fields=["status", "updated_at"])

    audit(
        farm=batch.farm, actor=user, action="LAB_TEST_VOID",
        entity=lab_test, reason=reason, batch_id=batch.pk,
    )

