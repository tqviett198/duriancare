import React, { useState } from 'react';

export default function SalesView({ currentRole }) {
  const [sales, setSales] = useState([
    {
      id: 1,
      sale_code: "SALE-EXP-001",
      sale_date: "2026-10-16",
      customer_name: "Công ty Nông sản Quốc tế An Phát",
      destination: "EXPORT",
      total_amount: 380000000,
      paid_amount: 340000000,
      payment_status: "PARTIAL",
      status: "CONFIRMED",
      grade: "Loại 1 (GRADE_1)",
    },
    {
      id: 2,
      sale_code: "SALE-DOM-002",
      sale_date: "2026-10-15",
      customer_name: "Vựa Sầu Riêng Chín Sài Gòn",
      destination: "DOMESTIC",
      total_amount: 100000000,
      paid_amount: 80000000,
      payment_status: "PARTIAL",
      status: "CONFIRMED",
      grade: "Loại 2 (GRADE_2)",
    }
  ]);

  const [showPayModal, setShowPayModal] = useState(false);
  const [selectedSale, setSelectedSale] = useState(null);
  const [payAmount, setPayAmount] = useState('');

  const isFinancialBlocked = currentRole !== 'OWNER';

  const handleOpenPay = (sale) => {
    setSelectedSale(sale);
    setPayAmount('');
    setShowPayModal(true);
  };

  const handleAddPayment = (e) => {
    e.preventDefault();
    const amt = parseFloat(payAmount);
    if (amt <= 0) return;

    setSales(sales.map(s => {
      if (s.id === selectedSale.id) {
        const newPaid = s.paid_amount + amt;
        const newStatus = newPaid >= s.total_amount ? 'PAID' : 'PARTIAL';
        return { ...s, paid_amount: newPaid, payment_status: newStatus };
      }
      return s;
    }));
    setShowPayModal(false);
  };

  if (isFinancialBlocked) {
    return (
      <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
        <span className="badge badge-danger">403 FORBIDDEN</span>
        <p style={{ marginTop: '0.75rem', color: 'var(--text-muted)' }}>
          Theo đặc tả và phân quyền hệ thống, vai trò <strong>{currentRole}</strong> không được xem hoặc tạo phiếu bán hàng & tài chính.
        </p>
      </div>
    );
  }

  return (
    <div className="sales-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="title-xl">Quản Lý Bán Hàng & Xuất Khẩu</h1>
          <p className="subtitle">Kiểm tra chỉ tiêu xuất khẩu (BR-13), trừ tồn kho tự động (BR-17) và thu tiền (/payments/).</p>
        </div>
      </div>

      <div className="table-container glass-panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mã Phiếu Bán</th>
              <th>Ngày Bán</th>
              <th>Khách Mua (Buyer)</th>
              <th>Thị Trường (BR-13)</th>
              <th>Phẩm Cấp</th>
              <th>Tổng Tiền</th>
              <th>Đã Thu</th>
              <th>Trạng Thái Thu</th>
              <th>Hành Động</th>
            </tr>
          </thead>
          <tbody>
            {sales.map(s => (
              <tr key={s.id}>
                <td><strong>{s.sale_code}</strong></td>
                <td>{s.sale_date}</td>
                <td>{s.customer_name}</td>
                <td>
                  <span className={`badge ${s.destination === 'EXPORT' ? 'badge-info' : 'badge-warning'}`}>
                    {s.destination === 'EXPORT' ? '✈️ XUẤT KHẨU' : '🏠 NỘI ĐỊA'}
                  </span>
                </td>
                <td>{s.grade}</td>
                <td><strong>{s.total_amount.toLocaleString('vi-VN')} đ</strong></td>
                <td style={{ color: '#34d399' }}>{s.paid_amount.toLocaleString('vi-VN')} đ</td>
                <td>
                  <span className={`badge ${s.payment_status === 'PAID' ? 'badge-success' : 'badge-warning'}`}>
                    {s.payment_status === 'PAID' ? 'Đủ tiền' : 'Còn thiếu'}
                  </span>
                </td>
                <td>
                  {s.paid_amount < s.total_amount && (
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                      onClick={() => handleOpenPay(s)}
                    >
                      + Thu tiền (/payments/)
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPayModal && selectedSale && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="glass-panel" style={{ background: '#101c18', padding: '1.75rem', width: '100%', maxWidth: '420px', border: '1px solid var(--border-strong)' }}>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, marginBottom: '0.5rem' }}>Thêm Khoản Thu Tiền</h3>
            <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Phiếu: <strong>{selectedSale.sale_code}</strong> · Còn thiếu: <strong>{(selectedSale.total_amount - selectedSale.paid_amount).toLocaleString('vi-VN')} đ</strong>
            </p>
            <form onSubmit={handleAddPayment} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Số tiền thu (VNĐ)</label>
                <input
                  type="number"
                  className="form-input"
                  value={payAmount}
                  onChange={e => setPayAmount(e.target.value)}
                  placeholder="Ví dụ: 20000000"
                  max={selectedSale.total_amount - selectedSale.paid_amount}
                  required
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowPayModal(false)}>Hủy</button>
                <button type="submit" className="btn btn-primary">Xác nhận thu tiền</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
