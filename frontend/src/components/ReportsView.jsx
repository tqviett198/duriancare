import React, { useState } from 'react';
import { MOCK_DATA } from '../api';

export default function ReportsView({ currentRole }) {
  const [subTab, setSubTab] = useState('cost_per_kg');

  const { costPerKg, profitLoss, receivables, inventory, phiWarnings } = MOCK_DATA;

  const isFinancialBlocked = currentRole !== 'OWNER';

  return (
    <div className="reports-view">
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 className="title-xl">Báo cáo & Thống kê Quản trị</h1>
        <p className="subtitle">Tính toán tự động theo quy tắc nghiệp vụ BR-15, BR-24 và ma trận phân quyền.</p>
      </div>

      {/* Tabs */}
      <div className="tab-group">
        <button
          className={`tab-btn ${subTab === 'cost_per_kg' ? 'active' : ''}`}
          onClick={() => setSubTab('cost_per_kg')}
        >
          Giá thành / kg (BR-24)
        </button>
        <button
          className={`tab-btn ${subTab === 'profit_loss' ? 'active' : ''}`}
          onClick={() => setSubTab('profit_loss')}
        >
          Lãi & Lỗ (P&L)
        </button>
        <button
          className={`tab-btn ${subTab === 'receivables' ? 'active' : ''}`}
          onClick={() => setSubTab('receivables')}
        >
          Công nợ người mua
        </button>
        <button
          className={`tab-btn ${subTab === 'inventory' ? 'active' : ''}`}
          onClick={() => setSubTab('inventory')}
        >
          Tồn kho theo Grade
        </button>
        <button
          className={`tab-btn ${subTab === 'phi' ? 'active' : ''}`}
          onClick={() => setSubTab('phi')}
        >
          Cảnh báo an toàn PHI
        </button>
      </div>

      {/* Subtab: Giá thành / kg (BR-24 & Mục 16.2) */}
      {subTab === 'cost_per_kg' && (
        isFinancialBlocked ? (
          <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <span className="badge badge-danger">403 FORBIDDEN</span>
            <p style={{ marginTop: '0.75rem', color: 'var(--text-muted)' }}>Chỉ vai trò <strong>OWNER (Chủ vườn)</strong> mới có quyền truy cập báo cáo tài chính.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="glass-panel" style={{ padding: '1.5rem', borderLeft: '4px solid var(--primary)' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem' }}>Quy tắc phân bổ giá thành (BR-24)</h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Chi phí trực tiếp ghi nhận vào từng lô đất. Chi phí chung toàn vườn (điện, nước, thuê đất, máy móc) được phân bổ theo <strong>tỷ lệ diện tích (area_ha)</strong>.
              </p>
            </div>

            <div className="table-container glass-panel">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tên Lô Đất</th>
                    <th>Diện Tích (ha)</th>
                    <th>Tỷ Lệ (%)</th>
                    <th>Chi Phí Trực Tiếp (đ)</th>
                    <th>Chi Phí Phân Bổ (đ)</th>
                    <th>Tổng Chi Phí (đ)</th>
                    <th>Sản Lượng (kg)</th>
                    <th>Giá Thành / kg</th>
                  </tr>
                </thead>
                <tbody>
                  {costPerKg.plots.map((p, idx) => (
                    <tr key={idx}>
                      <td><strong>{p.plot_name}</strong></td>
                      <td>{p.area_ha.toFixed(1)} ha</td>
                      <td>{p.area_percentage}%</td>
                      <td>{p.direct_cost.toLocaleString('vi-VN')} đ</td>
                      <td style={{ color: 'var(--accent-gold)' }}>+{p.allocated_general_cost.toLocaleString('vi-VN')} đ</td>
                      <td><strong>{p.total_cost.toLocaleString('vi-VN')} đ</strong></td>
                      <td>{p.harvested_kg.toLocaleString('vi-VN')} kg</td>
                      <td>
                        <span className="badge badge-success" style={{ fontSize: '0.85rem' }}>
                          {p.cost_per_kg.toLocaleString('vi-VN')} đ / kg
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr style={{ background: 'rgba(255,255,255,0.05)', fontWeight: 700 }}>
                    <td>TỔNG BÌNH QUÂN</td>
                    <td>5.0 ha</td>
                    <td>100%</td>
                    <td>{(75000000).toLocaleString('vi-VN')} đ</td>
                    <td style={{ color: 'var(--accent-gold)' }}>{(50000000).toLocaleString('vi-VN')} đ</td>
                    <td>{costPerKg.total_cost.toLocaleString('vi-VN')} đ</td>
                    <td>{costPerKg.total_harvested_kg.toLocaleString('vi-VN')} kg</td>
                    <td style={{ color: '#34d399', fontSize: '1.05rem' }}>
                      {costPerKg.average_cost_per_kg.toLocaleString('vi-VN')} đ / kg
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )
      )}

      {/* Subtab: Lãi & Lỗ (P&L) */}
      {subTab === 'profit_loss' && (
        isFinancialBlocked ? (
          <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <span className="badge badge-danger">403 FORBIDDEN</span>
            <p style={{ marginTop: '0.75rem', color: 'var(--text-muted)' }}>Chỉ vai trò <strong>OWNER</strong> mới có quyền xem báo cáo lãi lỗ.</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Cơ cấu Doanh Thu (BR-15)</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Doanh thu bán hàng</span>
                  <strong>{profitLoss.revenue.sales_revenue.toLocaleString('vi-VN')} đ</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#34d399' }}>
                  <span>Tiền đã thu về</span>
                  <span>{profitLoss.revenue.sales_paid.toLocaleString('vi-VN')} đ</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--accent-red)' }}>
                  <span>Công nợ còn thiếu</span>
                  <span>{profitLoss.revenue.receivables.toLocaleString('vi-VN')} đ</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Thu nhập khác</span>
                  <span>{profitLoss.revenue.other_income.toLocaleString('vi-VN')} đ</span>
                </div>
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '1.1rem', fontWeight: 800 }}>
                  <span>TỔNG DOANH THU</span>
                  <span style={{ color: '#fbbf24' }}>{profitLoss.revenue.total_revenue.toLocaleString('vi-VN')} đ</span>
                </div>
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Cơ cấu Chi Phí theo Danh Mục</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {profitLoss.expenses.by_category.map((c, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{c.category_display} <small style={{ color: 'var(--text-muted)' }}>({c.percentage}%)</small></span>
                    <span>{c.amount.toLocaleString('vi-VN')} đ</span>
                  </div>
                ))}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '1.1rem', fontWeight: 800 }}>
                  <span>TỔNG CHI PHÍ</span>
                  <span style={{ color: '#fb7185' }}>{profitLoss.expenses.total_expense.toLocaleString('vi-VN')} đ</span>
                </div>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', marginTop: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 700 }}>LỢI NHUẬN RÒNG (NET)</span>
                  <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#34d399' }}>+{profitLoss.profit.net_profit.toLocaleString('vi-VN')} đ ({profitLoss.profit.margin_percent}%)</span>
                </div>
              </div>
            </div>
          </div>
        )
      )}

      {/* Subtab: Công nợ người mua */}
      {subTab === 'receivables' && (
        isFinancialBlocked ? (
          <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <span className="badge badge-danger">403 FORBIDDEN</span>
            <p style={{ marginTop: '0.75rem', color: 'var(--text-muted)' }}>Chỉ vai trò <strong>OWNER</strong> mới có quyền xem công nợ.</p>
          </div>
        ) : (
          <div className="table-container glass-panel">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Khách Mua / Doanh Nghiệp</th>
                  <th>Số Điện Thoại</th>
                  <th>Thị Trường</th>
                  <th>Tổng Tiền Mua</th>
                  <th>Đã Thanh Toán</th>
                  <th>Công Nợ Còn Lại</th>
                  <th>Số Phiếu Bán</th>
                </tr>
              </thead>
              <tbody>
                {receivables.buyers.map((b, i) => (
                  <tr key={i}>
                    <td><strong>{b.customer_name}</strong></td>
                    <td>{b.phone}</td>
                    <td>
                      <span className={`badge ${b.is_export ? 'badge-info' : 'badge-warning'}`}>
                        {b.is_export ? 'Xuất khẩu' : 'Nội địa'}
                      </span>
                    </td>
                    <td>{b.total_invoiced.toLocaleString('vi-VN')} đ</td>
                    <td style={{ color: '#34d399' }}>{b.total_collected.toLocaleString('vi-VN')} đ</td>
                    <td style={{ color: '#fb7185', fontWeight: 700 }}>{b.total_debt.toLocaleString('vi-VN')} đ</td>
                    <td>{b.sales_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Subtab: Tồn kho theo Grade */}
      {subTab === 'inventory' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="kpi-grid">
            {inventory.by_grade.map((g, i) => (
              <div key={i} className="glass-panel kpi-card">
                <span className="kpi-label">{g.grade_display}</span>
                <span className="kpi-value">{g.remaining_kg.toLocaleString('vi-VN')} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>kg</small></span>
                <span className="kpi-footer">
                  Ước tính giá trị: {g.estimated_value.toLocaleString('vi-VN')} đ
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Subtab: Cảnh báo an toàn PHI */}
      {subTab === 'phi' && (
        <div className="table-container glass-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>Lô Canh Tác</th>
                <th>Giai Đoạn Cây</th>
                <th>Ngày An Toàn Thu Hoạch</th>
                <th>Số Ngày Còn Lại</th>
                <th>Trạng Thái Cách Ly</th>
              </tr>
            </thead>
            <tbody>
              {phiWarnings.plots.map((p, i) => (
                <tr key={i}>
                  <td><strong>{p.plot_name}</strong></td>
                  <td>{p.growth_stage}</td>
                  <td>{p.phi_safe_date}</td>
                  <td>{p.days_remaining === 0 ? 'Đã hết cách ly' : `${p.days_remaining} ngày`}</td>
                  <td>
                    <span className={`badge ${p.status === 'SAFE' ? 'badge-success' : 'badge-warning'}`}>
                      {p.status === 'SAFE' ? 'An toàn thu hoạch' : 'Đang cách ly PHI'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
