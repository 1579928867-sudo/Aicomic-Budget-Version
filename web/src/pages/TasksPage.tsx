import { useState, useEffect, useRef } from 'react';
import { ListTodo, Loader2, RefreshCw, XCircle, CheckCircle2, Clock, Play } from 'lucide-react';
import { tasks } from '../api';
import type { Task } from '../types';

const STATUS_ICON: Record<string, any> = {
  pending: Clock, running: Loader2, done: CheckCircle2, failed: XCircle, cancelled: XCircle,
};
const STATUS_COLOR: Record<string, string> = {
  pending: 'text-amber-400', running: 'text-blue-400', done: 'text-emerald-400', failed: 'text-red-400', cancelled: 'text-zinc-500',
};
const STATUS_BG: Record<string, string> = {
  pending: 'bg-amber-500/10 border-amber-500/20', running: 'bg-blue-500/10 border-blue-500/20', done: 'bg-emerald-500/10 border-emerald-500/20', failed: 'bg-red-500/10 border-red-500/20', cancelled: 'bg-zinc-700/30 border-zinc-600/30',
};

export function TasksPage() {
  const [taskList, setTaskList] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<any>(null);

  const fetchTasks = async () => {
    try {
      const list = await tasks.list();
      setTaskList(list);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchTasks();
    intervalRef.current = setInterval(fetchTasks, 3000);
    return () => clearInterval(intervalRef.current);
  }, []);

  const handleCancel = async (id: string) => {
    await tasks.cancel(id);
    fetchTasks();
  };

  const handleRetry = async (id: string) => {
    await tasks.retry(id);
    fetchTasks();
  };

  const formatTime = (ts: string) => {
    const d = new Date(ts + 'Z');
    return d.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">任务中心</h1>
          <p className="text-sm text-zinc-500">监控和管理所有后台任务</p>
        </div>
        <button onClick={fetchTasks} className="p-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-white transition-colors">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {taskList.length === 0 ? (
        <div className="text-center py-12 text-zinc-600">
          <ListTodo size={48} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">暂无任务</p>
        </div>
      ) : (
        <div className="space-y-3">
          {taskList.map(t => {
            const Icon = STATUS_ICON[t.status] || Clock;
            const isActive = t.status === 'running' || t.status === 'pending';
            return (
              <div key={t.id} className={`glass-card p-4 ${STATUS_BG[t.status] || ''}`}>
                <div className="flex items-center gap-3">
                  <Icon size={18} className={`${STATUS_COLOR[t.status]} ${t.status === 'running' ? 'animate-spin' : ''}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">{t.type}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${STATUS_BG[t.status]}`}>{t.status}</span>
                    </div>
                    <div className="flex gap-3 mt-1 text-[11px] text-zinc-500">
                      <span>ID: {t.id}</span>
                      {t.chapter_id && <span>章节 #{t.chapter_id}</span>}
                      <span>{formatTime(t.created_at)}</span>
                    </div>
                    {isActive && (
                      <div className="mt-2 w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500 animate-gradient"
                          style={{ width: `${Math.max(t.progress * 100, 5)}%`, backgroundSize: '300% 300%' }}
                        />
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1">
                    {isActive && (
                      <button onClick={() => handleCancel(t.id)} className="px-2 py-1 rounded text-[11px] bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors">
                        取消
                      </button>
                    )}
                    {(t.status === 'failed' || t.status === 'cancelled') && (
                      <button onClick={() => handleRetry(t.id)} className="flex items-center gap-1 px-2 py-1 rounded text-[11px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors">
                        <Play size={10} /> 重试
                      </button>
                    )}
                  </div>
                </div>
                {t.error && (
                  <div className="mt-2 text-[11px] text-red-400 bg-red-500/5 rounded-lg px-2 py-1">{t.error}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
