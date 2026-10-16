/**
 * API client cho DurianCare
 */
const BASE_URL = '/api/v1';

export async function fetchJson(endpoint, options = {}) {
  try {
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Lỗi HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.warn(`API call ${endpoint} failed, using local demo data:`, err.message);
    throw err;
  }
}

// Fallback demo data khi chạy độc lập không có backend
export const MOCK_DATA = {
  kpis: {
    harvestedKg: 7500,
    salesRevenue: 480000000,
    remainingStockKg: 2850,
    safePlotsCount: 4,
    totalPlotsCount: 4,
  },
  costPerKg: {
    average_cost_per_kg: 16667,
    total_cost: 125000000,
    total_harvested_kg: 7500,
    plots: [
      {
        plot_name: "Lô A1 — Ri6 Thử nghiệm",
        area_ha: 2.0,
        area_percentage: 40.0,
        direct_cost: 30000000,
        allocated_general_cost: 20000000,
        total_cost: 50000000,
        harvested_kg: 2500,
        cost_per_kg: 20000,
      },
      {
        plot_name: "Lô A2 — Monthong Mở rộng",
        area_ha: 3.0,
        area_percentage: 60.0,
        direct_cost: 45000000,
        allocated_general_cost: 30000000,
        total_cost: 75000000,
        harvested_kg: 5000,
        cost_per_kg: 15000,
      }
    ]
  },
  profitLoss: {
    revenue: {
      sales_revenue: 480000000,
      sales_paid: 420000000,
      receivables: 60000000,
      other_income: 15000000,
      total_revenue: 495000000,
    },
    expenses: {
      total_expense: 140000000,
      by_category: [
        { category_display: "Phân bón", amount: 48000000, percentage: 34.3 },
        { category_display: "Thuốc BVTV", amount: 32000000, percentage: 22.9 },
        { category_display: "Nhân công", amount: 40000000, percentage: 28.6 },
        { category_display: "Điện nước", amount: 12000000, percentage: 8.6 },
        { category_display: "Khác", amount: 8000000, percentage: 5.7 }
      ]
    },
    profit: {
      net_profit: 355000000,
      margin_percent: 71.7,
    }
  },
  receivables: {
    summary: {
      total_invoiced: 480000000,
      total_collected: 420000000,
      total_debt: 60000000,
    },
    buyers: [
      {
        customer_name: "Công ty Nông sản Quốc tế An Phát",
        phone: "0908 123 456",
        is_export: true,
        total_invoiced: 380000000,
        total_collected: 340000000,
        total_debt: 40000000,
        sales_count: 3
      },
      {
        customer_name: "Vựa Sầu Riêng Chín Sài Gòn",
        phone: "0912 987 654",
        is_export: false,
        total_invoiced: 100000000,
        total_collected: 80000000,
        total_debt: 20000000,
        sales_count: 2
      }
    ]
  },
  inventory: {
    summary: {
      total_initial_kg: 7500,
      total_remaining_kg: 2850,
      total_sold_kg: 4650,
      total_estimated_value: 236500000
    },
    by_grade: [
      { grade: "GRADE_1", grade_display: "Loại 1 (xuất khẩu)", remaining_kg: 1800, sold_kg: 3200, estimated_value: 171000000 },
      { grade: "GRADE_2", grade_display: "Loại 2 (nội địa cao cấp)", remaining_kg: 850, sold_kg: 1150, estimated_value: 59500000 },
      { grade: "GRADE_3", grade_display: "Loại 3 (nội địa thường)", remaining_kg: 200, sold_kg: 300, estimated_value: 6000000 }
    ]
  },
  phiWarnings: {
    summary: { safe_count: 3, warning_count: 1, restricted_count: 0 },
    plots: [
      { plot_name: "Lô A1 — Ri6 Thử nghiệm", status: "SAFE", days_remaining: 0, phi_safe_date: "2026-10-10", growth_stage: "HARVEST" },
      { plot_name: "Lô A2 — Monthong Mở rộng", status: "SAFE", days_remaining: 0, phi_safe_date: "2026-10-12", growth_stage: "HARVEST" },
      { plot_name: "Lô B1 — Musang King", status: "WARNING", days_remaining: 2, phi_safe_date: "2026-10-18", growth_stage: "FRUIT_DEVELOPMENT" }
    ]
  },
  tasks: [
    {
      id: 1,
      title: "Lấy mẫu kiểm nghiệm Cadmium & Chlorpyrifos xuất khẩu",
      task_type_display: "Kiểm nghiệm",
      priority_display: "Khẩn cấp",
      status: "COMPLETED",
      due_date: "2026-10-16",
      is_system: true,
      description: "Lô A1 thu hoạch chuẩn bị xuất khẩu sang Trung Quốc (BR-13)."
    },
    {
      id: 2,
      title: "Bón thúc đợt 2 phân Kali Sunfat (SOP)",
      task_type_display: "Bón phân",
      priority_display: "Cao",
      status: "PENDING",
      due_date: "2026-10-20",
      is_recurring: true,
      recurring_interval_days: 14,
      description: "Bón 500g/cây cho toàn bộ Lô A2 (mẫu chu kỳ lặp lại BR-22)."
    },
    {
      id: 3,
      title: "Kiểm tra hệ thống tưới bù áp",
      task_type_display: "Tưới nước",
      priority_display: "Trung bình",
      status: "IN_PROGRESS",
      due_date: "2026-10-19",
      is_recurring: false,
      description: "Vệ sinh lọc đĩa và đo áp suất tại béc tưới."
    }
  ]
};
