import { Link, useLocation } from 'react-router-dom';
import { MessageCircle, Library, Film, Cookie, ListTodo, Settings, Home } from 'lucide-react';

const NAV = [
  { key: 'chat', path: '/chat', label: 'AI漫剧助手', icon: MessageCircle },
  { key: 'library', path: '/library', label: '漫剧素材库', icon: Library },
  { key: 'videos', path: '/videos', label: '漫剧视频', icon: Film },
  { key: 'cookie', path: '/cookie', label: '豆包Cookie', icon: Cookie },
  { key: 'tasks', path: '/tasks', label: '任务中心', icon: ListTodo },
  { key: 'settings', path: '/settings', label: '系统设置', icon: Settings },
];

export function Sidebar() {
  const location = useLocation();
  const activeKey = (() => {
    for (const n of NAV) { if (location.pathname === n.path) return n.key; }
    return null;
  })();

  return (
    <aside style={{
      width: 240, height: '100vh', flexShrink: 0, overflow: 'hidden',
      backgroundImage: 'url(/nav-bg.webp)',
      backgroundSize: 'cover', backgroundPosition: 'center',
      position: 'relative',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Texture overlay — solid at edges, translucent in middle */}
      <div style={{
        position: 'absolute', inset: 0,
        background: `
          rgba(100,88,76,0.80)
        `,
        zIndex: 0, pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Home button */}
        <div style={{ padding: '20px 20px 8px' }}>
          <Link
            to="/"
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px', borderRadius: 10,
              border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.85)', fontFamily: 'inherit',
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              width: '100%', transition: 'all 0.15s',
              textDecoration: 'none', boxSizing: 'border-box',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.18)'; e.currentTarget.style.color = '#fff'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = 'rgba(255,255,255,0.85)'; }}
          >
            <Home size={17} /> 返回首页
          </Link>
        </div>

        {/* Logo */}
        <div style={{ padding: '8px 20px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 42, height: 42, borderRadius: 12,
              background: 'var(--accent)', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20, boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
            }}>🎬</div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', lineHeight: 1.3 }}>AI漫剧</div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginTop: 1 }}>Comic Video Studio</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {NAV.map(({ key, path, label, icon: Icon }) => {
            const active = activeKey === key;
            return (
              <Link
                key={key}
                to={path}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '11px 16px', borderRadius: 10,
                  border: active ? '1px solid rgba(255,255,255,0.15)' : '1px solid transparent',
                  background: active ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: active ? '#fff' : 'rgba(255,255,255,0.75)',
                  fontSize: 14, fontWeight: 600, fontFamily: 'inherit',
                  cursor: 'pointer', transition: 'all 0.15s ease',
                  textDecoration: 'none',
                }}
                onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'rgba(255,255,255,0.07)'; e.currentTarget.style.color = 'rgba(255,255,255,0.9)'; }}}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'rgba(255,255,255,0.6)'; }}}
              >
                <Icon size={18} style={{ opacity: active ? 1 : 0.5 }} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div style={{ position: 'relative', zIndex: 1, padding: '16px 20px', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
          <span style={{ fontSize: 11, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>v0.4 · 运行中</span>
        </div>
      </div>
    </aside>
  );
}
