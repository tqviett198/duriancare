import React from 'react';

export default function Navbar({ activeTab, setActiveTab, currentRole, setCurrentRole }) {
  const roles = [
    { key: 'OWNER', label: 'Chủ vườn (OWNER)' },
    { key: 'ADVISOR', label: 'Kỹ thuật viên (ADVISOR)' },
    { key: 'WORKER', label: 'Người làm vườn (WORKER)' },
  ];

  return (
    <header className="navbar">
      <div className="brand">
        <div className="brand-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span>DurianCare</span>
      </div>

      <nav className="nav-links">
        <button
          className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Tổng quan
        </button>
        <button
          className={`nav-item ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          Báo cáo thống kê
        </button>
        <button
          className={`nav-item ${activeTab === 'harvests' ? 'active' : ''}`}
          onClick={() => setActiveTab('harvests')}
        >
          Lô & Kiểm nghiệm
        </button>
        <button
          className={`nav-item ${activeTab === 'sales' ? 'active' : ''}`}
          onClick={() => setActiveTab('sales')}
        >
          Bán hàng & Xuất khẩu
        </button>
        <button
          className={`nav-item ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => setActiveTab('tasks')}
        >
          Công việc & Cảnh báo
        </button>
      </nav>

      <div className="nav-controls">
        <select
          className="form-select"
          style={{ width: 'auto', padding: '0.4rem 0.8rem', fontSize: '0.8rem', background: '#13211c' }}
          value={currentRole}
          onChange={(e) => setCurrentRole(e.target.value)}
        >
          {roles.map(r => (
            <option key={r.key} value={r.key}>{r.label}</option>
          ))}
        </select>
        <div className="role-badge">
          <span>●</span> {currentRole}
        </div>
      </div>
    </header>
  );
}
