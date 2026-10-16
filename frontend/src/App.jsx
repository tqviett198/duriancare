import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import ReportsView from './components/ReportsView';
import HarvestsView from './components/HarvestsView';
import SalesView from './components/SalesView';
import TasksView from './components/TasksView';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [currentRole, setCurrentRole] = useState('OWNER');

  return (
    <div className="app-container">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        currentRole={currentRole}
        setCurrentRole={setCurrentRole}
      />

      <main className="main-content">
        {activeTab === 'dashboard' && (
          <Dashboard setActiveTab={setActiveTab} currentRole={currentRole} />
        )}
        {activeTab === 'reports' && (
          <ReportsView currentRole={currentRole} />
        )}
        {activeTab === 'harvests' && (
          <HarvestsView currentRole={currentRole} />
        )}
        {activeTab === 'sales' && (
          <SalesView currentRole={currentRole} />
        )}
        {activeTab === 'tasks' && (
          <TasksView currentRole={currentRole} />
        )}
      </main>

      <footer style={{ borderTop: '1px solid var(--border-subtle)', padding: '1.25rem', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-subtle)' }}>
        DurianCare © 2026 — Nền tảng quản lý vườn sầu riêng thông minh, an toàn VietGAP/GlobalGAP & phục vụ xuất khẩu chính ngạch.
      </footer>
    </div>
  );
}
