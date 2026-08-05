import { MessageCircle, Library, Film, Cookie, ListTodo, Settings, Home } from 'lucide-react';
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
      backgroundImage: 'url(/nav-bg.webp)',
      backgroundSize: 'cover', backgroundPosition: 'center',
      position: 'relative',
      display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--border)',
    }}>
      {/* Texture overlay for readability */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(180deg, rgba(250,248,245,0.93) 0%, rgba(245,243,240,0.96) 50%, rgba(240,237,232,0.97) 100%)',
        zIndex: 0, pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Home button */}
        <div style={{ padding: '20px 20px 8px' }}>
          <button
            onClick={() => setActivePage('home')}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px', borderRadius: 10,
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text-secondary)', fontFamily: 'inherit',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
              width: '100%', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--text)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
          >
            <Home size={17} /> 返回首页
          </button>
        </div>

        {/* Logo */}
        <div style={{ padding: '8px 20px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 42, height: 42, borderRadius: 12,
              background: 'var(--accent)', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20, boxShadow: 'var(--shadow-md)',
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
                  fontSize: 14, fontWeight: 500, fontFamily: 'inherit',
                  cursor: 'pointer', transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text)'; }}}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}}
              >
                <Icon size={18} style={{ opacity: active ? 1 : 0.55 }} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>

        {/* Footer */}
        <div style={{ position: 'relative', zIndex: 1, padding: '16px 20px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>v0.3 · 运行中</span>
        </div>
      </div>
    </aside>
  );
}
