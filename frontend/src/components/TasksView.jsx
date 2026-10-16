import React, { useState } from 'react';
import { MOCK_DATA } from '../api';

export default function TasksView({ currentRole }) {
  const [tasks, setTasks] = useState(MOCK_DATA.tasks);
  const [showModal, setShowModal] = useState(false);
  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState(new Date().toISOString().split('T')[0]);
  const [isRecurring, setIsRecurring] = useState(false);
  const [intervalDays, setIntervalDays] = useState(7);

  const handleComplete = (id) => {
    setTasks(tasks.map(t => {
      if (t.id === id) {
        // BR-22: sinh việc tiếp theo nếu là recurring
        if (t.is_recurring) {
          const nextDueDate = new Date();
          nextDueDate.setDate(nextDueDate.getDate() + (t.recurring_interval_days || 7));
          setTimeout(() => {
            setTasks(prev => [
              ...prev,
              {
                id: prev.length + 1,
                title: t.title,
                task_type_display: t.task_type_display,
                priority_display: t.priority_display,
                status: "PENDING",
                due_date: nextDueDate.toISOString().split('T')[0],
                is_recurring: true,
                recurring_interval_days: t.recurring_interval_days,
                description: `${t.description} (Chu kỳ tiếp theo tự động sinh bởi BR-22)`,
              }
            ]);
          }, 300);
        }
        return { ...t, status: 'COMPLETED' };
      }
      return t;
    }));
  };

  const handleCreate = (e) => {
    e.preventDefault();
    const newTask = {
      id: tasks.length + 1,
      title,
      due_date: dueDate,
      task_type_display: "Chung",
      priority_display: "Trung bình",
      status: "PENDING",
      is_recurring: isRecurring,
      recurring_interval_days: isRecurring ? parseInt(intervalDays) : null,
      description: isRecurring ? `Công việc lặp chu kỳ ${intervalDays} ngày (BR-22).` : "Công việc làm vườn bình thường.",
    };
    setTasks([newTask, ...tasks]);
    setShowModal(false);
    setTitle('');
  };

  return (
    <div className="tasks-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="title-xl">Quản Lý Công Việc & Nhắc Nhở</h1>
          <p className="subtitle">Hỗ trợ việc lặp tự sinh (BR-22) và bảo vệ việc hệ thống không cho phép sửa (BR-23).</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          + Giao việc mới
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {tasks.map(t => (
          <div key={t.id} className="glass-panel" style={{ padding: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <strong style={{ fontSize: '1.05rem', textDecoration: t.status === 'COMPLETED' ? 'line-through' : 'none', color: t.status === 'COMPLETED' ? 'var(--text-muted)' : '#fff' }}>
                  {t.title}
                </strong>
                {t.is_system && (
                  <span className="badge badge-info" title="BR-23: Công việc hệ thống không thể sửa">
                    ⚙️ Hệ thống (BR-23)
                  </span>
                )}
                {t.is_recurring && (
                  <span className="badge badge-warning" title="BR-22: Tự động sinh việc tiếp theo khi hoàn thành">
                    🔁 Lặp lại ({t.recurring_interval_days || 7} ngày)
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{t.description}</p>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-subtle)', display: 'flex', gap: '1rem' }}>
                <span>📅 Hạn: <strong>{t.due_date}</strong></span>
                <span>🏷️ Loại: <strong>{t.task_type_display}</strong></span>
                <span>⚡ Mức độ: <strong>{t.priority_display}</strong></span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span className={`badge ${t.status === 'COMPLETED' ? 'badge-success' : 'badge-warning'}`}>
                {t.status === 'COMPLETED' ? 'Đã hoàn thành' : 'Đang thực hiện'}
              </span>
              {t.status !== 'COMPLETED' && (
                <button className="btn btn-primary" style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }} onClick={() => handleComplete(t.id)}>
                  ✓ Hoàn thành
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="glass-panel" style={{ background: '#101c18', padding: '1.75rem', width: '100%', maxWidth: '460px', border: '1px solid var(--border-strong)' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: '1rem' }}>Tạo Công Việc Làm Vườn</h3>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tiêu đề công việc</label>
                <input className="form-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="Tưới nước, bón phân, tỉa cành..." required />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Ngày hết hạn</label>
                <input type="date" className="form-input" value={dueDate} onChange={e => setDueDate(e.target.value)} required />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input type="checkbox" id="rec" checked={isRecurring} onChange={e => setIsRecurring(e.target.checked)} />
                <label htmlFor="rec" style={{ fontSize: '0.85rem' }}>Công việc lặp lại định kỳ (BR-22)</label>
              </div>
              {isRecurring && (
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Số ngày giữa các chu kỳ lặp</label>
                  <input type="number" min="1" className="form-input" value={intervalDays} onChange={e => setIntervalDays(e.target.value)} required />
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Hủy</button>
                <button type="submit" className="btn btn-primary">Tạo việc</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
