import React, { useState } from 'react';

export default function HarvestsView({ currentRole }) {
  const [showModal, setShowModal] = useState(false);
  const [labTests, setLabTests] = useState([
    {
      id: 1,
      batch_code: "LOT-2026-RI6-01",
      tested_date: "2026-10-15",
      lab_name: "Trung tâm Khảo kiểm nghiệm Eurofins Sài Gòn",
      result: "PASS",
      analyte: "Cadmium (Kim loại nặng)",
      result_value: "0.0200",
      limit_value: "0.0500",
      valid_until: "2027-01-15",
      status: "ACTIVE",
    },
    {
      id: 2,
      batch_code: "LOT-2026-MON-01",
      tested_date: "2026-10-14",
      lab_name: "Viện Cây Ăn Quả Miền Nam (SOFRI)",
      result: "PASS",
      analyte: "Dư lượng Chlorpyrifos",
      result_value: "0.0050",
      limit_value: "0.0100",
      valid_until: "2027-01-14",
      status: "ACTIVE",
    }
  ]);

  const [form, setForm] = useState({
    batch_code: "LOT-2026-RI6-01",
    tested_date: new Date().toISOString().split('T')[0],
    lab_name: "Eurofins Cần Thơ",
    result: "PASS",
    analyte: "Cadmium",
    result_value: "0.025",
    limit_value: "0.050",
    valid_until: "2027-01-15",
  });

  const handleAdd = (e) => {
    e.preventDefault();
    const newTest = {
      id: labTests.length + 1,
      ...form,
      status: "ACTIVE",
    };
    setLabTests([newTest, ...labTests]);
    setShowModal(false);
  };

  const handleVoid = (id) => {
    if (currentRole !== 'OWNER') {
      alert('Chỉ OWNER mới có quyền hủy kết quả kiểm nghiệm!');
      return;
    }
    const reason = prompt('Nhập lý do hủy kết quả kiểm nghiệm:');
    if (reason) {
      setLabTests(labTests.map(t => t.id === id ? { ...t, status: 'VOIDED', void_reason: reason } : t));
    }
  };

  return (
    <div className="harvests-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="title-xl">Lô Thu Hoạch & Kết Quả Kiểm Nghiệm</h1>
          <p className="subtitle">Quản lý mã lô (/batches/), chỉ tiêu kiểm nghiệm an toàn (BR-12, BR-13).</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          + Nhập kết quả kiểm nghiệm (LabTest)
        </button>
      </div>

      {/* Lab Tests Table */}
      <div className="table-container glass-panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mã Lô</th>
              <th>Ngày Kiểm</th>
              <th>Phòng Thí Nghiệm</th>
              <th>Chỉ Tiêu Đo</th>
              <th>Kết Quả vs Ngưỡng (MRL)</th>
              <th>Hạn Hiệu Lực</th>
              <th>Đánh Giá</th>
              <th>Trạng Thái</th>
              <th>Hành Động</th>
            </tr>
          </thead>
          <tbody>
            {labTests.map(t => (
              <tr key={t.id} style={{ opacity: t.status === 'VOIDED' ? 0.6 : 1 }}>
                <td><strong>{t.batch_code}</strong></td>
                <td>{t.tested_date}</td>
                <td>{t.lab_name}</td>
                <td><span className="badge badge-info">{t.analyte}</span></td>
                <td>
                  <strong>{t.result_value}</strong> / {t.limit_value} ppm
                </td>
                <td>{t.valid_until}</td>
                <td>
                  <span className={`badge ${t.result === 'PASS' ? 'badge-success' : 'badge-danger'}`}>
                    {t.result === 'PASS' ? 'ĐẠT (PASS)' : 'KHÔNG ĐẠT'}
                  </span>
                </td>
                <td>
                  <span className={`badge ${t.status === 'ACTIVE' ? 'badge-success' : 'badge-danger'}`}>
                    {t.status === 'ACTIVE' ? 'Hiệu lực' : 'Đã hủy (VOIDED)'}
                  </span>
                </td>
                <td>
                  {t.status === 'ACTIVE' && (
                    <button
                      className="btn btn-danger"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                      onClick={() => handleVoid(t.id)}
                    >
                      Hủy kết quả
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal Add Test */}
      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="glass-panel" style={{ background: '#101c18', padding: '1.75rem', width: '100%', maxWidth: '500px', border: '1px solid var(--border-strong)' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: '1rem' }}>Thêm Kết Quả Kiểm Nghiệm (LabTest)</h3>
            <form onSubmit={handleAdd} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Mã lô thu hoạch</label>
                <input className="form-input" value={form.batch_code} onChange={e => setForm({...form, batch_code: e.target.value})} required />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Ngày kiểm nghiệm</label>
                  <input type="date" className="form-input" value={form.tested_date} onChange={e => setForm({...form, tested_date: e.target.value})} required />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Hạn hiệu lực (valid_until)</label>
                  <input type="date" className="form-input" value={form.valid_until} onChange={e => setForm({...form, valid_until: e.target.value})} required />
                </div>
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tên phòng kiểm nghiệm</label>
                <input className="form-input" value={form.lab_name} onChange={e => setForm({...form, lab_name: e.target.value})} required />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Chỉ tiêu kiểm nghiệm (analyte)</label>
                <input className="form-input" value={form.analyte} onChange={e => setForm({...form, analyte: e.target.value})} placeholder="Cadmium, Chlorpyrifos..." required />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Giá trị đo được</label>
                  <input type="number" step="0.0001" className="form-input" value={form.result_value} onChange={e => setForm({...form, result_value: e.target.value})} required />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Ngưỡng tối đa (limit)</label>
                  <input type="number" step="0.0001" className="form-input" value={form.limit_value} onChange={e => setForm({...form, limit_value: e.target.value})} required />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Hủy</button>
                <button type="submit" className="btn btn-primary">Lưu kết quả</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
