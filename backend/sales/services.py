"""
Services cho module sales.

Các hàm nghiệp vụ chính:
- create_sale: tạo phiếu bán + trừ tồn kho (BR-13, BR-14, BR-17)
- void_sale: hủy phiếu bán + hoàn tồn kho (BR-19)
- add_payment: thêm khoản thanh toán + cập nhật payment_status (BR-18)
- void_payment: hủy khoản thanh toán + hoàn paid_amount (Phase 2)
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from common.exceptions import DomainError
from common.models import audit
from harvests.models import BatchStock, HarvestBatch, LabTest

from .models import Payment, Sale, SaleLine



@transaction.atomic
def create_sale(
    farm,
    user,
    sale_code: str,
    sale_date,
    customer_name: str,
    lines: list,
    customer_phone: str = "",
    note: str = "",
    buyer=None,
    season=None,
    destination: str = "DOMESTIC",
) -> Sale:
    """
    Tạo phiếu bán và trừ tồn kho.

    BR-13: Chỉ lô PASSED mới được bán (PENDING bị chặn – Phase 2 Q3).
    BR-14: Dùng select_for_update sắp theo ID tránh deadlock.
    BR-17: Trừ remaining_kg của từng BatchStock.

    Args:
        lines: [{stock_id, qty_kg, unit_price}, ...]

    Returns:
        Sale đã lưu.

    Raises:
        DomainError: vi phạm BR hoặc dữ liệu không hợp lệ.
    """
    if not lines:
        raise DomainError("lines_empty", "Phiếu bán phải có ít nhất một dòng.", 400)

    # Kiểm tra trùng mã phiếu
    if Sale.objects.filter(farm=farm, sale_code=sale_code).exists():
        raise DomainError(
            "duplicate_sale_code",
            f"Mã phiếu '{sale_code}' đã tồn tại trong vườn này.",
            409,
        )

    # ── Thu thập stock_ids và sắp xếp theo ID (BR-14: tránh deadlock) ────────
    stock_ids = sorted({line["stock_id"] for line in lines})

    # Lock theo thứ tự ID
    locked_stocks = {
        s.id: s
        for s in (BatchStock.objects
                  .select_for_update()
                  .select_related("batch")
                  .filter(id__in=stock_ids)
                  .order_by("id"))
    }

    # ── Validate từng dòng ────────────────────────────────────────────────────
    total_amount = Decimal(0)
    sale_lines = []

    for line in lines:
        stock_id = line["stock_id"]
        qty_kg = Decimal(str(line["qty_kg"]))
        unit_price = Decimal(str(line["unit_price"]))

        stock = locked_stocks.get(stock_id)
        if stock is None:
            raise DomainError(
                "stock_not_found",
                f"Không tìm thấy tồn kho (id={stock_id}).",
                400,
            )

        # Kiểm tra lô thuộc vườn TRƯỚC mọi kiểm tra khác, để không lộ mã lô /
        # trạng thái lô của vườn khác qua thông báo lỗi (chống IDOR).
        if stock.batch.farm_id != farm.id:
            raise DomainError("stock_wrong_farm", "Tồn kho không thuộc vườn này.", 403)

        # BR-13: Chỉ lô PASSED mới bán được (Phase 2: chặn PENDING)
        if stock.batch.status == HarvestBatch.Status.PENDING:
            raise DomainError(
                "batch_pending",
                f"Lô '{stock.batch.batch_code}' chưa qua kiểm nghiệm "
                f"(trạng thái: {stock.batch.get_status_display()}). "
                "Chỉ lô đã PASSED mới được bán.",
                409,
            )

        if stock.batch.status == HarvestBatch.Status.FAILED:
            raise DomainError(
                "batch_failed",
                f"Lô '{stock.batch.batch_code}' không đạt kiểm nghiệm "
                f"(trạng thái: {stock.batch.get_status_display()}). Không thể bán.",
                409,
            )

        # Lô đã hủy cũng không bán được
        if stock.batch.status == HarvestBatch.Status.VOIDED:
            raise DomainError(
                "batch_voided",
                f"Lô '{stock.batch.batch_code}' đã bị hủy. Không thể bán.",
                409,
            )

        # BR-13: Kiểm tra tiêu chuẩn khi bán EXPORT
        is_export_sale = (destination == "EXPORT") or (buyer and getattr(buyer, "is_export", False))
        if is_export_sale:
            # 1. Phẩm cấp: chỉ cho phép Grade 1 hoặc Grade 2 xuất khẩu
            if stock.grade in ("GRADE_3", "REJECT"):
                raise DomainError(
                    "export_grade_not_allowed",
                    f"Phân loại '{stock.get_grade_display()}' không đủ tiêu chuẩn xuất khẩu.",
                    400,
                )

            # 2. Kiểm tra có kiểm nghiệm PASS còn hiệu lực
            active_test = (LabTest.objects
                           .filter(batch=stock.batch, status=LabTest.Status.ACTIVE, result=LabTest.Result.PASS)
                           .order_by("-tested_date", "-id")
                           .first())
            if not active_test:
                raise DomainError(
                    "export_requires_valid_lab_test",
                    f"Lô '{stock.batch.batch_code}' không có kết quả kiểm nghiệm đạt chuẩn xuất khẩu.",
                    409,
                )

            # 3. Kiểm tra hạn hiệu lực kiểm nghiệm (nếu có valid_until)
            if active_test.valid_until and active_test.valid_until < sale_date:
                raise DomainError(
                    "export_lab_test_expired",
                    f"Kết quả kiểm nghiệm của lô '{stock.batch.batch_code}' đã hết hạn vào ngày {active_test.valid_until}.",
                    409,
                )

            # 4. Kiểm tra chỉ tiêu đo vs ngưỡng quy định (result_value <= limit_value)
            if active_test.result_value is not None and active_test.limit_value is not None:
                if active_test.result_value > active_test.limit_value:
                    raise DomainError(
                        "export_limit_exceeded",
                        f"Chỉ tiêu '{active_test.analyte or 'kiểm nghiệm'}' đo được {active_test.result_value} "
                        f"vượt ngưỡng tối đa cho phép xuất khẩu ({active_test.limit_value}).",
                        409,
                    )

            # 5. Kiểm tra thông số độc hại trong parameters_json (ví dụ: Cadmium <= 0.05 ppm)
            if active_test.parameters_json and "cadmium_ppm" in active_test.parameters_json:
                cadmium_val = Decimal(str(active_test.parameters_json["cadmium_ppm"]))
                if cadmium_val > Decimal("0.05"):
                    raise DomainError(
                        "export_cadmium_exceeded",
                        f"Dư lượng Cadmium ({cadmium_val} ppm) vượt ngưỡng cho phép xuất khẩu (0.05 ppm).",
                        409,
                    )

        # BR-17: Kiểm tra đủ tồn
        if qty_kg > stock.remaining_kg:
            raise DomainError(
                "insufficient_stock",
                f"Tồn kho '{stock.batch.batch_code}–{stock.grade}' "
                f"chỉ còn {stock.remaining_kg} kg, không đủ xuất {qty_kg} kg.",
                409,
            )


        line_total = qty_kg * unit_price
        total_amount += line_total
        sale_lines.append((stock, qty_kg, unit_price, line_total))

    # ── Tạo Sale ──────────────────────────────────────────────────────────────
    sale = Sale.objects.create(
        farm=farm,
        sale_code=sale_code,
        sale_date=sale_date,
        buyer=buyer,
        customer_name=customer_name,
        customer_phone=customer_phone,
        season=season,
        destination=destination,
        total_amount=total_amount,
        note=note,
        created_by=user,
    )

    # ── Tạo SaleLine + trừ tồn kho ──────────────────────────────────────────
    line_objs = []
    for stock, qty_kg, unit_price, line_total in sale_lines:
        line_objs.append(SaleLine(
            sale=sale,
            stock=stock,
            qty_kg=qty_kg,
            unit_price=unit_price,
            line_total=line_total,
        ))
        # Trừ tồn kho BatchStock
        stock.remaining_kg = F("remaining_kg") - qty_kg
        stock.save(update_fields=["remaining_kg"])
        # Trừ tồn kho HarvestBatch
        stock.batch.remaining_kg = F("remaining_kg") - qty_kg
        stock.batch.save(update_fields=["remaining_kg", "updated_at"])

    SaleLine.objects.bulk_create(line_objs)
    return sale


@transaction.atomic
def void_sale(sale: Sale, user, reason: str) -> None:
    """
    Hủy phiếu bán và hoàn tồn kho (BR-19).

    Phase 2: Cho phép hủy phiếu nếu tất cả payments đã VOIDED hoặc chưa có payment.

    Raises:
        DomainError: phiếu đã hủy hoặc còn thanh toán ACTIVE.
    """
    # Lock sale row để tránh race condition với add_payment
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status == Sale.Status.CANCELLED:
        raise DomainError("already_voided", "Phiếu này đã bị hủy trước đó.", 409)

    # BR-19: Không hủy phiếu còn thanh toán ACTIVE
    active_payments = sale.payments.filter(status=Payment.Status.ACTIVE)
    if active_payments.exists():
        total_active = sum(p.amount for p in active_payments)
        raise DomainError(
            "sale_has_payments",
            f"Không thể hủy phiếu còn thanh toán hiệu lực ({total_active:,.0f} đ). "
            "Vui lòng hủy các khoản thanh toán trước.",
            409,
        )

    # ── Hoàn tồn kho ─────────────────────────────────────────────────────────
    # Lock BatchStock theo thứ tự ID (BR-14) để tránh deadlock
    line_qs = sale.lines.select_related("stock__batch").order_by("stock_id")
    stock_ids = sorted(line_qs.values_list("stock_id", flat=True).distinct())

    locked_stocks = {
        s.id: s
        for s in (BatchStock.objects
                  .select_for_update()
                  .filter(id__in=stock_ids)
                  .order_by("id"))
    }

    for line in line_qs:
        stock = locked_stocks[line.stock_id]
        stock.remaining_kg = F("remaining_kg") + line.qty_kg
        stock.save(update_fields=["remaining_kg"])
        # Hoàn cho batch
        line.stock.batch.remaining_kg = F("remaining_kg") + line.qty_kg
        line.stock.batch.save(update_fields=["remaining_kg", "updated_at"])

    # ── Đánh dấu hủy ─────────────────────────────────────────────────────────
    sale.status = Sale.Status.CANCELLED
    sale.void_reason = reason
    sale.voided_by = user
    sale.voided_at = timezone.now()
    sale.save(update_fields=[
        "status", "void_reason", "voided_by", "voided_at", "updated_at",
    ])

    # Audit trail
    audit(
        farm=sale.farm, actor=user, action="SALE_VOID",
        entity=sale, reason=reason,
    )


@transaction.atomic
def add_payment(sale: Sale, user, amount, payment_date, method="CASH",
                reference="", note="") -> Payment:
    """
    Thêm khoản thanh toán cho phiếu bán (BR-18).

    Raises:
        DomainError: phiếu đã hủy, hoặc vượt tổng tiền.
    """
    # Lock sale row to prevent concurrent payment race condition
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status == Sale.Status.CANCELLED:
        raise DomainError("sale_voided", "Không thể thanh toán cho phiếu đã hủy.", 409)

    amount = Decimal(str(amount))
    new_paid = sale.paid_amount + amount

    if new_paid > sale.total_amount:
        raise DomainError(
            "payment_exceeds_total",
            f"Tổng thanh toán ({new_paid}) sẽ vượt tổng phiếu ({sale.total_amount}).",
            409,
        )

    payment = Payment.objects.create(
        sale=sale,
        amount=amount,
        payment_date=payment_date,
        method=method,
        reference=reference,
        note=note,
        created_by=user,
    )

    # Cập nhật paid_amount và payment_status
    sale.paid_amount = new_paid
    sale.payment_status = sale.recompute_payment_status()
    sale.save(update_fields=["paid_amount", "payment_status", "updated_at"])

    return payment


@transaction.atomic
def void_payment(payment: Payment, user, reason: str) -> None:
    """
    Hủy khoản thanh toán và hoàn paid_amount cho phiếu bán (Phase 2).

    Raises:
        DomainError: thanh toán đã hủy hoặc phiếu đã hủy.
    """
    # Lock payment + sale
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    sale = Sale.objects.select_for_update().get(pk=payment.sale_id)

    if payment.status == Payment.Status.VOIDED:
        raise DomainError("payment_already_voided", "Khoản thanh toán này đã bị hủy trước đó.", 409)

    if sale.status == Sale.Status.CANCELLED:
        raise DomainError("sale_voided", "Không thể hủy thanh toán cho phiếu đã hủy.", 409)

    # Hủy payment
    payment.status = Payment.Status.VOIDED
    payment.void_reason = reason
    payment.voided_by = user
    payment.voided_at = timezone.now()
    payment.save(update_fields=[
        "status", "void_reason", "voided_by", "voided_at",
    ])

    # Hoàn paid_amount
    sale.paid_amount = F("paid_amount") - payment.amount
    sale.save(update_fields=["paid_amount", "updated_at"])
    sale.refresh_from_db()
    sale.payment_status = sale.recompute_payment_status()
    sale.save(update_fields=["payment_status", "updated_at"])

    # Audit trail
    audit(
        farm=sale.farm, actor=user, action="PAYMENT_VOID",
        entity=payment, reason=reason,
        sale_id=sale.pk,
    )
