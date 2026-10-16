"""
Services tính toán báo cáo cho DurianCare.

Các báo cáo:
- Profit & Loss (Doanh thu bán hàng, thu khác, chi phí phân theo danh mục, lợi nhuận ròng, tỷ suất)
- Cost per kg (BR-24: chi phí trực tiếp từng lô + phân bổ chi phí chung theo diện tích, tính giá thành / kg)
- Receivables (Công nợ người mua: tổng xuất, đã thu, còn nợ)
- Stock Inventory (Tồn kho theo grade, kg ban đầu, đã bán, còn lại, ước tính giá trị)
- PHI Warnings (Cảnh báo thời gian cách ly thuốc BVTV theo từng lô đất)
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from django.db.models import Sum, Count, Q, F

from farms.models import Plot, Season, PlotSeason
from finance.models import LedgerEntry
from harvests.models import HarvestBatch, BatchStock, BatchGrade
from harvests.services import compute_phi_safe_date
from logs.models import FarmLogInput, FarmLog
from sales.models import Sale, Payment, Buyer


def get_profit_loss_report(farm, season: Optional[Season] = None,
                           date_from: Optional[date] = None,
                           date_to: Optional[date] = None) -> Dict[str, Any]:
    """
    Báo cáo lãi lỗ theo mùa vụ hoặc khoảng thời gian.

    BR-15: Doanh thu bán hàng chỉ lấy từ Sale (status=CONFIRMED).
    Thu khác và Chi phí lấy từ LedgerEntry (status=ACTIVE).
    """
    sales_qs = Sale.objects.filter(farm=farm, status=Sale.Status.CONFIRMED)
    ledger_qs = LedgerEntry.objects.filter(farm=farm, status=LedgerEntry.Status.ACTIVE)

    if season:
        sales_qs = sales_qs.filter(season=season)
        ledger_qs = ledger_qs.filter(season=season)
    else:
        if date_from:
            sales_qs = sales_qs.filter(sale_date__gte=date_from)
            ledger_qs = ledger_qs.filter(txn_date__gte=date_from)
        if date_to:
            sales_qs = sales_qs.filter(sale_date__lte=date_to)
            ledger_qs = ledger_qs.filter(txn_date__lte=date_to)

    # 1. Doanh thu bán hàng & tiền đã thu
    sale_agg = sales_qs.aggregate(
        total_sales=Sum("total_amount"),
        total_paid=Sum("paid_amount"),
        count=Count("id"),
    )
    sales_revenue = sale_agg["total_sales"] or Decimal(0)
    sales_paid = sale_agg["total_paid"] or Decimal(0)
    receivables = sales_revenue - sales_paid

    # 2. Thu khác
    other_income = (ledger_qs.filter(type=LedgerEntry.Type.OTHER_INCOME)
                    .aggregate(total=Sum("amount"))["total"] or Decimal(0))

    total_revenue = sales_revenue + other_income

    # 3. Chi phí theo danh mục
    expenses_qs = ledger_qs.filter(type=LedgerEntry.Type.EXPENSE)
    category_totals: Dict[str, Decimal] = {}
    for choice, label in LedgerEntry.Category.choices:
        category_totals[choice] = Decimal(0)

    for item in expenses_qs.values("category").annotate(total=Sum("amount")):
        cat = item["category"]
        category_totals[cat] = item["total"] or Decimal(0)

    total_expense = sum(category_totals.values(), Decimal(0))

    # 4. Lợi nhuận ròng & Tỷ suất
    net_profit = total_revenue - total_expense
    margin_percent = ((net_profit / total_revenue) * Decimal(100)) if total_revenue > 0 else Decimal(0)

    return {
        "season_id": season.id if season else None,
        "season_name": season.name if season else "Tất cả",
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "revenue": {
            "sales_revenue": sales_revenue,
            "sales_paid": sales_paid,
            "receivables": receivables,
            "other_income": other_income,
            "total_revenue": total_revenue,
            "sales_count": sale_agg["count"] or 0,
        },
        "expenses": {
            "total_expense": total_expense,
            "by_category": [
                {
                    "category": cat,
                    "category_display": dict(LedgerEntry.Category.choices).get(cat, cat),
                    "amount": amt,
                    "percentage": ((amt / total_expense) * 100).quantize(Decimal("0.01")) if total_expense > 0 else Decimal(0),
                }
                for cat, amt in category_totals.items()
            ],
        },
        "profit": {
            "net_profit": net_profit,
            "margin_percent": margin_percent.quantize(Decimal("0.01")),
        },
    }


def get_cost_per_kg_report(farm, season: Season) -> Dict[str, Any]:
    """
    BR-24: Báo cáo giá thành theo kg theo mùa vụ.
    Quy tắc phân bổ:
    - Chi phí trực tiếp: LedgerEntry có plot_id cụ thể.
    - Chi phí chung (plot_id is NULL): Phân bổ cho từng lô đất theo tỷ lệ diện tích (area_ha).
    - Sản lượng (kg): Tổng HarvestBatch.total_kg trong mùa vụ của lô đất đó (loại trừ VOIDED).
    - Giá thành / kg = Tổng chi phí lô đất / Sản lượng kg.
    """
    plots = list(Plot.objects.filter(farm=farm, is_active=True))
    total_farm_area = sum((p.area_ha for p in plots), Decimal(0))

    # Chi phí trực tiếp từng plot
    direct_expenses = {p.id: Decimal(0) for p in plots}
    plot_direct_qs = (LedgerEntry.objects
                      .filter(farm=farm, season=season, type=LedgerEntry.Type.EXPENSE,
                              status=LedgerEntry.Status.ACTIVE, plot__isnull=False)
                      .values("plot_id")
                      .annotate(total=Sum("amount")))
    for item in plot_direct_qs:
        direct_expenses[item["plot_id"]] = item["total"] or Decimal(0)

    # Chi phí chung (plot is NULL)
    general_expense = (LedgerEntry.objects
                       .filter(farm=farm, season=season, type=LedgerEntry.Type.EXPENSE,
                               status=LedgerEntry.Status.ACTIVE, plot__isnull=True)
                       .aggregate(total=Sum("amount"))["total"] or Decimal(0))

    # Sản lượng thu hoạch từng plot
    harvest_qs = (HarvestBatch.objects
                  .filter(farm=farm, season=season)
                  .exclude(status=HarvestBatch.Status.VOIDED)
                  .values("plot_id")
                  .annotate(total_kg=Sum("total_kg")))
    harvest_by_plot = {item["plot_id"]: item["total_kg"] or Decimal(0) for item in harvest_qs}

    plots_report = []
    total_direct_all = Decimal(0)
    total_allocated_all = Decimal(0)
    total_cost_all = Decimal(0)
    total_kg_all = Decimal(0)

    for p in plots:
        direct_cost = direct_expenses.get(p.id, Decimal(0))
        # Phân bổ chi phí chung theo tỷ lệ diện tích
        if total_farm_area > 0:
            area_ratio = p.area_ha / total_farm_area
            allocated_general = (general_expense * area_ratio).quantize(Decimal("1"))
        else:
            area_ratio = Decimal(0)
            allocated_general = Decimal(0)

        total_plot_cost = direct_cost + allocated_general
        total_kg = harvest_by_plot.get(p.id, Decimal(0))
        cost_per_kg = (total_plot_cost / total_kg).quantize(Decimal("1")) if total_kg > 0 else None

        plots_report.append({
            "plot_id": p.id,
            "plot_name": p.name,
            "area_ha": p.area_ha,
            "area_percentage": (area_ratio * 100).quantize(Decimal("0.01")),
            "direct_cost": direct_cost,
            "allocated_general_cost": allocated_general,
            "total_cost": total_plot_cost,
            "harvested_kg": total_kg,
            "cost_per_kg": cost_per_kg,
        })

        total_direct_all += direct_cost
        total_allocated_all += allocated_general
        total_cost_all += total_plot_cost
        total_kg_all += total_kg

    farm_cost_per_kg = (total_cost_all / total_kg_all).quantize(Decimal("1")) if total_kg_all > 0 else None

    return {
        "season_id": season.id,
        "season_name": season.name,
        "total_farm_area_ha": total_farm_area,
        "general_expense_pool": general_expense,
        "summary": {
            "total_direct_cost": total_direct_all,
            "total_general_cost": general_expense,
            "total_cost": total_cost_all,
            "total_harvested_kg": total_kg_all,
            "average_cost_per_kg": farm_cost_per_kg,
        },
        "plots": plots_report,
    }


def get_receivables_report(farm) -> Dict[str, Any]:
    """
    Báo cáo công nợ người mua (từ Sale và Buyer).
    """
    sales = (Sale.objects
             .filter(farm=farm, status=Sale.Status.CONFIRMED)
             .select_related("buyer")
             .order_by("-sale_date"))

    # Gom theo Buyer (hoặc customer_name nếu chưa gắn Buyer)
    buyers_data: Dict[str, Dict[str, Any]] = {}

    total_invoiced = Decimal(0)
    total_collected = Decimal(0)

    for sale in sales:
        total_invoiced += sale.total_amount
        total_collected += sale.paid_amount
        debt = sale.total_amount - sale.paid_amount

        key = str(sale.buyer_id) if sale.buyer_id else f"raw_{sale.customer_name}"
        if key not in buyers_data:
            buyers_data[key] = {
                "buyer_id": sale.buyer_id,
                "customer_name": sale.buyer.name if sale.buyer else sale.customer_name,
                "phone": sale.buyer.phone if sale.buyer else sale.customer_phone,
                "is_export": sale.buyer.is_export if sale.buyer else (sale.destination == "EXPORT"),
                "total_invoiced": Decimal(0),
                "total_collected": Decimal(0),
                "total_debt": Decimal(0),
                "sales_count": 0,
                "unpaid_sales": [],
            }

        rec = buyers_data[key]
        rec["total_invoiced"] += sale.total_amount
        rec["total_collected"] += sale.paid_amount
        rec["total_debt"] += debt
        rec["sales_count"] += 1

        if debt > 0:
            rec["unpaid_sales"].append({
                "sale_id": sale.id,
                "sale_code": sale.sale_code,
                "sale_date": str(sale.sale_date),
                "total_amount": sale.total_amount,
                "paid_amount": sale.paid_amount,
                "debt_amount": debt,
                "payment_status": sale.payment_status,
            })

    total_debt = total_invoiced - total_collected

    return {
        "summary": {
            "total_invoiced": total_invoiced,
            "total_collected": total_collected,
            "total_debt": total_debt,
            "buyers_count": len(buyers_data),
        },
        "buyers": sorted(list(buyers_data.values()), key=lambda x: x["total_debt"], reverse=True),
    }


def get_stock_inventory_report(farm) -> Dict[str, Any]:
    """
    Báo cáo tồn kho sầu riêng phân theo phẩm cấp (grade).
    """
    stocks = (BatchStock.objects
              .filter(batch__farm=farm)
              .exclude(batch__status=HarvestBatch.Status.VOIDED)
              .select_related("batch", "batch__plot"))

    by_grade: Dict[str, Dict[str, Any]] = {}
    for grade_code, grade_label in BatchGrade.choices:
        by_grade[grade_code] = {
            "grade": grade_code,
            "grade_display": grade_label,
            "initial_kg": Decimal(0),
            "remaining_kg": Decimal(0),
            "sold_kg": Decimal(0),
            "estimated_value": Decimal(0),
        }

    active_batches: Dict[int, Dict[str, Any]] = {}

    for s in stocks:
        g = by_grade[s.grade]
        g["initial_kg"] += s.qty_kg
        g["remaining_kg"] += s.remaining_kg
        sold = s.qty_kg - s.remaining_kg
        g["sold_kg"] += sold
        if s.estimated_price_per_kg:
            g["estimated_value"] += s.remaining_kg * s.estimated_price_per_kg

        # Tồn theo lô còn dư
        if s.remaining_kg > 0:
            b_id = s.batch_id
            if b_id not in active_batches:
                active_batches[b_id] = {
                    "batch_id": b_id,
                    "batch_code": s.batch.batch_code,
                    "plot_name": s.batch.plot.name,
                    "harvest_date": str(s.batch.harvest_date),
                    "status": s.batch.status,
                    "status_display": s.batch.get_status_display(),
                    "stocks": [],
                }
            active_batches[b_id]["stocks"].append({
                "grade": s.grade,
                "grade_display": s.get_grade_display(),
                "remaining_kg": s.remaining_kg,
                "estimated_price_per_kg": s.estimated_price_per_kg,
            })

    total_initial = sum((g["initial_kg"] for g in by_grade.values()), Decimal(0))
    total_remaining = sum((g["remaining_kg"] for g in by_grade.values()), Decimal(0))
    total_sold = sum((g["sold_kg"] for g in by_grade.values()), Decimal(0))
    total_val = sum((g["estimated_value"] for g in by_grade.values()), Decimal(0))

    return {
        "summary": {
            "total_initial_kg": total_initial,
            "total_remaining_kg": total_remaining,
            "total_sold_kg": total_sold,
            "total_estimated_value": total_val,
        },
        "by_grade": list(by_grade.values()),
        "available_batches": list(active_batches.values()),
    }


def get_phi_warnings_report(farm, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Cảnh báo ngày cách ly thuốc BVTV (PHI) cho các lô đất trong vườn.
    """
    as_of = as_of_date or date.today()
    plots = Plot.objects.filter(farm=farm, is_active=True).order_by("name")

    plot_warnings = []
    safe_count = 0
    warning_count = 0
    violated_count = 0

    for p in plots:
        phi_safe = compute_phi_safe_date(plot_id=p.id, before_date=as_of + timedelta(days=90))

        # Tìm lần phun gần nhất
        latest_spray = (FarmLogInput.objects
                        .filter(
                            log__plot=p,
                            log__status=FarmLog.Status.ACTIVE,
                            product__kind="PESTICIDE",
                            product__phi_days__isnull=False,
                        )
                        .select_related("product", "log")
                        .order_by("-log__activity_date")
                        .first())

        if phi_safe is None or latest_spray is None:
            status = "SAFE"
            days_left = 0
            safe_count += 1
        else:
            diff = (phi_safe - as_of).days
            days_left = max(0, diff)
            if diff <= 0:
                status = "SAFE"
                safe_count += 1
            elif diff <= 3:
                status = "WARNING"
                warning_count += 1
            else:
                status = "RESTRICTED"
                violated_count += 1

        plot_warnings.append({
            "plot_id": p.id,
            "plot_name": p.name,
            "area_ha": p.area_ha,
            "variety_name": p.variety.name if p.variety else "",
            "growth_stage": p.growth_stage,
            "status": status,
            "phi_safe_date": str(phi_safe) if phi_safe else None,
            "days_remaining": days_left,
            "latest_spray": {
                "activity_date": str(latest_spray.log.activity_date) if latest_spray else None,
                "product_name": latest_spray.product.name if latest_spray else None,
                "phi_days": latest_spray.product.phi_days if latest_spray else None,
            } if latest_spray else None,
        })

    return {
        "as_of_date": str(as_of),
        "summary": {
            "total_plots": len(plots),
            "safe_count": safe_count,
            "warning_count": warning_count,
            "restricted_count": violated_count,
        },
        "plots": plot_warnings,
    }
