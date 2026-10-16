"""Nghiệp vụ nhật ký: kiểm tra vật tư (BR-06), tính chi phí (BR-07), chi phí tự sinh (BR-16)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from catalog.models import InputProduct
from common.exceptions import DomainError
from common.models import audit
from farms.models import Season
from finance.models import LedgerEntry

from .models import FarmLog, FarmLogInput


def line_total(quantity, unit_cost):
    """BR-07: total_cost = quantity × unit_cost, làm tròn đến đồng."""
    return (Decimal(quantity) * Decimal(unit_cost)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def evaluate_inputs(*, inputs, plot, season, acknowledged, exclude_log=None):
    """Trả về (warnings, cờ đã xác nhận theo vật tư). Chặn nếu vật tư không dùng được cho sầu riêng."""
    warnings, unacknowledged, ack_flags = [], [], {}
    for item in inputs:
        product = item["product"]
        if product.registered_for_durian == InputProduct.DurianStatus.NO:
            raise DomainError(
                "product_not_allowed",
                f"Vật tư '{product.name}' không có trong danh mục dùng cho sầu riêng.",
                product=product.id,
            )
        if product.registered_for_durian == InputProduct.DurianStatus.UNKNOWN:
            warn = {"code": "registered_unknown", "product": product.id,
                    "detail": "Chưa xác định vật tư này có trong danh mục cho sầu riêng. "
                              "Hãy kiểm tra nhãn và hỏi kỹ thuật viên."}
            warnings.append(warn)
            if product.id in acknowledged:
                ack_flags[product.id] = True
            else:
                unacknowledged.append(warn)
        if product.max_applications_per_season and season:
            used = (FarmLogInput.objects
                    .filter(log__plot=plot, log__season=season, log__status=FarmLog.Status.ACTIVE,
                            product=product)
                    .exclude(log=exclude_log).count())
            if used + 1 > product.max_applications_per_season:
                warnings.append({
                    "code": "max_applications_exceeded", "product": product.id,
                    "detail": f"'{product.name}' đã dùng {used} lần trong vụ này "
                              f"(tối đa {product.max_applications_per_season} lần).",
                })
    if unacknowledged:
        raise DomainError("warning_unacknowledged",
                          "Cần xác nhận cảnh báo vật tư trước khi lưu.", 409, warnings=unacknowledged)
    return warnings, ack_flags


def sync_expense(log, user):
    """BR-16: giữ các khoản chi tự sinh tách theo từng loại vật tư (FERTILIZER, PESTICIDE...) của nhật ký."""
    items = list(log.inputs.select_related("product"))
    by_kind = {}
    for i in items:
        by_kind[i.product.kind] = by_kind.get(i.product.kind, Decimal("0")) + i.total_cost

    existing_entries = {e.category: e for e in LedgerEntry.objects.filter(source_log=log)}

    # Với các category không còn trong log (hoặc không còn chi phí): void khoản chi đó
    for cat, entry in existing_entries.items():
        if cat not in by_kind or by_kind[cat] <= 0:
            if entry.status == LedgerEntry.Status.ACTIVE:
                entry.status = LedgerEntry.Status.VOIDED
                entry.void_reason = "Nhật ký không còn chi phí cho loại vật tư này"
                entry.voided_by, entry.voided_at = user, timezone.now()
                entry.save()

    active_entries = []
    for kind, amount in by_kind.items():
        if amount <= 0:
            continue
        category_label = dict(LedgerEntry.Category.choices).get(kind, kind)
        fields = dict(
            farm_id=log.plot.farm_id, plot=log.plot, season=log.season,
            type=LedgerEntry.Type.EXPENSE, category=kind, amount=amount,
            txn_date=log.activity_date,
            description=f"Nhật ký #{log.pk} ({category_label}): {log.get_activity_type_display()}",
            status=LedgerEntry.Status.ACTIVE, void_reason="", voided_by=None, voided_at=None,
        )
        entry = existing_entries.get(kind)
        if entry is None:
            entry = LedgerEntry.objects.create(source_log=log, created_by=user, **fields)
        else:
            for k, v in fields.items():
                setattr(entry, k, v)
            entry.save()
        active_entries.append(entry)

    if not active_entries:
        return None
    return active_entries[0] if len(active_entries) == 1 else active_entries


@transaction.atomic
def save_log(*, farm, user, data, log=None):
    """Tạo hoặc cập nhật nhật ký cùng vật tư và khoản chi tương ứng trong một transaction."""
    data = dict(data)
    inputs = data.pop("inputs", None)
    acknowledged = set(data.pop("acknowledged_warnings", []))
    creating = log is None

    plot = data.get("plot", None if creating else log.plot)
    season = data.get("season", None if creating else log.season)
    if creating and season is None:
        season = Season.objects.filter(farm=farm, status=Season.Status.ACTIVE).first()
    if season is not None and season.status == Season.Status.CLOSED:
        raise DomainError("season_closed", "Vụ này đã đóng, không ghi thêm nhật ký.", 409)

    warnings, ack_flags = [], {}
    if inputs is not None:
        warnings, ack_flags = evaluate_inputs(inputs=inputs, plot=plot, season=season,
                                              acknowledged=acknowledged, exclude_log=log)

    if creating:
        log = FarmLog.objects.create(created_by=user, season=season,
                                     performed_by=data.pop("performed_by", None) or user,
                                     **{k: v for k, v in data.items() if k != "season"})
    else:
        for k, v in data.items():
            setattr(log, k, v)
        log.save()

    if inputs is not None:
        log.inputs.all().delete()
        FarmLogInput.objects.bulk_create([
            FarmLogInput(log=log, product=i["product"], quantity=i["quantity"], unit_cost=i["unit_cost"],
                         total_cost=line_total(i["quantity"], i["unit_cost"]),
                         warning_acknowledged=ack_flags.get(i["product"].id, False))
            for i in inputs
        ])
    expense = sync_expense(log, user)
    return log, warnings, expense


@transaction.atomic
def void_log(*, log, user, reason):
    """BR-03: hủy có dấu vết, không xóa. Khoản chi tự sinh cũng bị hủy theo."""
    if log.status == FarmLog.Status.VOIDED:
        raise DomainError("already_voided", "Nhật ký đã được hủy trước đó.", 409)
    log.status = FarmLog.Status.VOIDED
    log.void_reason, log.voided_by, log.voided_at = reason, user, timezone.now()
    log.save()
    entries = LedgerEntry.objects.filter(source_log=log, status=LedgerEntry.Status.ACTIVE)
    for entry in entries:
        entry.status = LedgerEntry.Status.VOIDED
        entry.void_reason, entry.voided_by, entry.voided_at = f"Hủy nhật ký: {reason}", user, timezone.now()
        entry.save()
    audit(farm=log.plot.farm, actor=user, action="LOG_VOID", entity=log, reason=reason)
    return log
