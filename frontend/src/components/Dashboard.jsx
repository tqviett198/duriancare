import React from 'react';
import { MOCK_DATA } from '../api';

export default function Dashboard({ setActiveTab, currentRole }) {
  const kpis = MOCK_DATA.kpis;

  return (
    <div className="dashboard-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="title-xl">Trang trại Sầu riêng Mekong Delta</h1>
          <p className="subtitle">Mùa vụ hiện tại: <strong>Vụ Thuận 2026</strong> · Quy mô: <strong>5.0 ha (2 lô canh tác)</strong></p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={() => setActiveTab('reports')}>
            Xem báo cáo P&L
          </button>
          {currentRole === 'OWNER' && (
            <button className="btn btn-primary" onClick={() => setActiveTab('sales')}>
              + Tạo phiếu bán hàng
            </button>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="glass-panel kpi-card" style={{ '--kpi-glow': 'rgba(16, 185, 129, 0.2)' }}>
          <span className="kpi-label">Sản lượng đã thu hoạch</span>
          <span className="kpi-value">{(kpis.harvestedKg).toLocaleString('vi-VN')} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>kg</small></span>
          <span className="kpi-footer">
            <span style={{ color: '#34d399' }}>✓ 100%</span> đã qua kiểm nghiệm an toàn
          </span>
        </div>

        <div className="glass-panel kpi-card" style={{ '--kpi-glow': 'rgba(245, 158, 11, 0.2)' }}>
          <span className="kpi-label">Doanh thu bán hàng</span>
          <span className="kpi-value" style={{ color: '#fbbf24' }}>{(kpis.salesRevenue / 1000000).toFixed(0)} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>tr đ</small></span>
          <span className="kpi-footer">
            Đã thu {(420).toLocaleString('vi-VN')} tr · Nợ 60 tr
          </span>
        </div>

        <div className="glass-panel kpi-card" style={{ '--kpi-glow': 'rgba(56, 189, 248, 0.2)' }}>
          <span className="kpi-label">Tồn kho sầu riêng</span>
          <span className="kpi-value" style={{ color: '#38bdf8' }}>{(kpis.remainingStockKg).toLocaleString('vi-VN')} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>kg</small></span>
          <span className="kpi-footer">
            Loại 1: 1.800 kg · Loại 2: 850 kg
          </span>
        </div>

        <div className="glass-panel kpi-card" style={{ '--kpi-glow': 'rgba(244, 63, 94, 0.2)' }}>
          <span className="kpi-label">Cách ly an toàn (PHI)</span>
          <span className="kpi-value" style={{ color: '#34d399' }}>{kpis.safePlotsCount}/{kpis.totalPlotsCount} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>lô</small></span>
          <span className="kpi-footer">
            <span className="badge badge-success">An toàn thu hoạch</span>
          </span>
        </div>
      </div>

      {/* Highlights Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Quick status */}
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Chỉ số giá thành & Hiệu quả (BR-24)</h3>
            <span className="badge badge-info">Mục 16.2</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Giá thành bình quân toàn vườn</span>
              <strong style={{ color: '#34d399', fontSize: '1.15rem' }}>16.667 đ / kg</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Giá thành Lô A1 (Ri6)</span>
              <strong>20.000 đ / kg</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Giá thành Lô A2 (Monthong)</span>
              <strong>15.000 đ / kg</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Tỷ suất lợi nhuận ròng</span>
              <strong style={{ color: '#fbbf24' }}>71.7%</strong>
            </div>
          </div>
        </div>

        {/* Actionable Tasks */}
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Việc làm vườn hôm nay</h3>
            <button className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }} onClick={() => setActiveTab('tasks')}>
              Xem tất cả
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {MOCK_DATA.tasks.map(t => (
              <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{t.title}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Hạn: {t.due_date} · Loại: {t.task_type_display}</div>
                </div>
                <span className={`badge ${t.status === 'COMPLETED' ? 'badge-success' : 'badge-warning'}`}>
                  {t.status === 'COMPLETED' ? 'Hoàn thành' : 'Đang xử lý'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
