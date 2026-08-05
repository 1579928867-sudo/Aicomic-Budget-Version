import { MessageCircle, Library, Film, Cookie, ListTodo, Settings } from 'lucide-react';
import { useAppStore } from '../stores/app';

const NAV = [
  { key: 'chat', label: 'AI漫剧助手', icon: MessageCircle },
  { key: 'library', label: '漫剧素材库', icon: Library },
  { key: 'videos', label: '漫剧视频', icon: Film },
  { key: 'cookie', label: '豆包Cookie', icon: Cookie },
  { key: 'tasks', label: '任务中心', icon: ListTodo },
  { key: 'settings', label: '系统设置', icon: Settings },
];

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  return (
    <aside style={{
      width: 240, minHeight: '100vh', flexShrink: 0,
      background: 'var(--surface-alt)', borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Logo */}
      <div style={{ padding: '28px 20px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 12,
            background: 'var(--accent)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20,
          }}>🎬</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3 }}>AI漫剧</div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 1 }}>Comic Video Studio</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {NAV.map(({ key, label, icon: Icon }) => {
          const active = activePage === key;
          return (
            <button
              key={key}
              onClick={() => setActivePage(key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '11px 16px', borderRadius: 10,
                border: active ? '1px solid var(--accent-border)' : '1px solid transparent',
                background: active ? 'var(--accent-light)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--text-secondary)',
                fontSize: 14, fontWeight: 500,
                cursor: 'pointer', transition: 'all 0.15s ease',
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--text)'; }}}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}}
            >
              <Icon size={18} style={{ opacity: active ? 1 : 0.55 }} />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>v0.2 · 运行中</span>
      </div>
    </aside>
  );
}
