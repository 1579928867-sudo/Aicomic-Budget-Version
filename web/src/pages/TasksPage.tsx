import { useState, useEffect, useRef } from 'react';
import { ListTodo, Loader2, RefreshCw, XCircle, CheckCircle2, Clock, Play, StopCircle, Trash2 } from 'lucide-react';
import { tasks } from '../api';
import type { Task } from '../types';

const STATUS: Record<string, { icon: any; color: string; bg: string; label: string }> = {
  pending:  { icon: Clock,          color: '#D49B4A', bg: '#FDF5E8', label: '等待中' },
  running:  { icon: Loader2,         color: '#3B82C0', bg: '#E8F2FD', label: '运行中' },
  done:     { icon: CheckCircle2,    color: '#5B8C5A', bg: '#EDF5EC', label: '已完成' },
  failed:   { icon: XCircle,         color: '#C45C4C', bg: '#FDF0ED', label: '失败' },
  cancelled:{ icon: StopCircle,      color: '#9C9994', bg: '#F5F3F0', label: '已取消' },
};

export function TasksPage() {
  const [taskList, setTaskList] = useState<Task[]>([]);
  const intervalRef = useRef<any>(null);

  const fetchTasks = async () => {
    try { setTaskList(await tasks.list()); } catch {}
  };

  useEffect(() => {
    fetchTasks();
    intervalRef.current = setInterval(fetchTasks, 4000);
    return () => clearInterval(intervalRef.current);
  }, []);

  const handleCancel = async (id: string) => { await tasks.cancel(id); fetchTasks(); };
  const handleRetry = async (id: string) => { await tasks.retry(id); fetchTasks(); };
  const handleDelete = async (id: string) => {
    await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
    fetchTasks();
  };
  const handleClearCompleted = async () => {
    const doneCount = taskList.filter(t => t.status === 'done' || t.status === 'failed' || t.status === 'cancelled').length;
    if (doneCount === 0) return;
    if (!window.confirm(`确定删除全部 ${doneCount} 个已完成/失败的任务？此操作不可撤销。`)) return;
    await fetch('/api/tasks', { method: 'DELETE' });
    fetchTasks();
  };

  const fmt = (ts: string) => new Date(ts + 'Z').toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>任务中心</h1>
          <p style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>监控和管理所有后台任务</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={handleClearCompleted}
            disabled={!taskList.some(t => t.status === 'done' || t.status === 'failed' || t.status === 'cancelled')}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 9,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text-tertiary)', fontFamily: 'inherit', fontSize: 12, fontWeight: 500,
              cursor: 'pointer', transition: 'all 0.15s',
              opacity: taskList.some(t => t.status === 'done' || t.status === 'failed' || t.status === 'cancelled') ? 1 : 0.4,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'var(--error-bg)';
              e.currentTarget.style.color = 'var(--error)';
              e.currentTarget.style.borderColor = 'var(--error)40';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'var(--surface)';
              e.currentTarget.style.color = 'var(--text-tertiary)';
              e.currentTarget.style.borderColor = 'var(--border)';
            }}
          >
            <Trash2 size={13} /> 清空已完成
          </button>
          <button
            onClick={fetchTasks}
            style={{
              width: 38, height: 38, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-tertiary)',
              cursor: 'pointer', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--text)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text-tertiary)'; }}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {taskList.length === 0 ? (
        <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--text-tertiary)' }}>
          <ListTodo size={44} style={{ marginBottom: 12, opacity: 0.3 }} />
          <p style={{ fontSize: 14 }}>暂无任务</p>
          <p style={{ fontSize: 12, marginTop: 4 }}>通过 Chat 页面触发生成来创建新任务</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {taskList.map(t => {
            const st = STATUS[t.status] || STATUS.pending;
            const Icon = st.icon;
            const isActive = t.status === 'running' || t.status === 'pending';
            return (
              <div key={t.id} style={{
                padding: '18px 22px', borderRadius: 14,
                background: 'var(--surface)', border: `1px solid ${isActive ? st.color + '30' : 'var(--border)'}`,
                transition: 'box-shadow 0.15s',
              }}
                onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                  <Icon size={18} style={{ color: st.color, marginTop: 2, ...(t.status === 'running' ? { animation: 'spin 0.7s linear infinite' } : {}) }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{t.type}</span>
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '2px 10px', borderRadius: 100,
                        background: st.bg, color: st.color, letterSpacing: '0.03em',
                      }}>{st.label}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-tertiary)' }}>
                      <span>ID: {t.id}</span>
                      {t.chapter_id && <span>章节 #{t.chapter_id}</span>}
                      <span>{fmt(t.created_at)}</span>
                    </div>
                    {isActive && (
                      <div style={{ marginTop: 12, height: 4, background: 'var(--surface-alt)', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', borderRadius: 2,
                          background: `linear-gradient(90deg, ${st.color}, ${st.color}99)`,
                          width: `${Math.max(t.progress * 100, 8)}%`,
                          transition: 'width 0.6s ease',
                        }} />
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {isActive && (
                      <button onClick={() => handleCancel(t.id)} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '6px 14px',
                        borderRadius: 8, border: '1px solid var(--error-border, #F0C0B8)', background: 'var(--error-bg)', color: 'var(--error)',
                        fontFamily: 'inherit', fontSize: 12, fontWeight: 500, cursor: 'pointer', transition: 'all 0.12s',
                      }}>取消</button>
                    )}
                    {(t.status === 'failed' || t.status === 'cancelled') && (
                      <button onClick={() => handleRetry(t.id)} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '6px 14px',
                        borderRadius: 8, border: '1px solid var(--accent-border)', background: 'var(--accent-light)', color: 'var(--accent)',
                        fontFamily: 'inherit', fontSize: 12, fontWeight: 500, cursor: 'pointer', transition: 'all 0.12s',
                      }}>
                        <Play size={11} /> 重试
                      </button>
                    )}
                    {(t.status === 'done' || t.status === 'failed' || t.status === 'cancelled') && (
                      <button onClick={() => handleDelete(t.id)} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 2, padding: '6px 10px',
                        borderRadius: 8, border: '1px solid var(--border)',
                        background: 'var(--surface)', color: 'var(--text-tertiary)',
                        fontFamily: 'inherit', fontSize: 12, fontWeight: 500, cursor: 'pointer',
                        transition: 'all 0.12s',
                      }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = 'var(--error-bg)';
                          e.currentTarget.style.color = 'var(--error)';
                          e.currentTarget.style.borderColor = 'var(--error)40';
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = 'var(--surface)';
                          e.currentTarget.style.color = 'var(--text-tertiary)';
                          e.currentTarget.style.borderColor = 'var(--border)';
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
                {t.error && (
                  <div style={{ marginTop: 10, padding: '8px 14px', borderRadius: 8, background: 'var(--error-bg)', fontSize: 12, color: 'var(--error)', lineHeight: 1.5 }}>
                    {t.error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
