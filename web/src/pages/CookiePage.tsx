import { useState, useEffect } from 'react';
import { Cookie, CheckCircle2, XCircle, Save, Copy, Key, ClipboardPaste } from 'lucide-react';
import { settings } from '../api';

export function CookiePage() {
  const [cookieValid, setCookieValid] = useState(false);
  const [cookieInput, setCookieInput] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    settings.cookieStatus().then(r => setCookieValid(r.valid)).catch(() => {});
  }, []);

  const handleSave = async () => {
    try {
      await fetch('/api/settings/cookie', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: cookieInput }),
      });
      setSaved(true); setCookieValid(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) { console.error(e); }
  };

  const steps = [
    { step: 1, title: '打开豆包网站', desc: '在浏览器中访问 www.doubao.com', link: 'https://www.doubao.com', linkLabel: '打开豆包' },
    { step: 2, title: '登录你的豆包账号', desc: '确保已经成功登录，可以使用 AI 生图功能' },
    { step: 3, title: '打开浏览器开发者工具', desc: '按键盘上的 F12 或 Ctrl+Shift+I 打开 DevTools' },
    { step: 4, title: '找到并复制 Cookies', desc: '在顶部标签栏点击 "Application"（应用程序），左侧菜单找到 "Cookies"，点击域名，然后全选复制右侧显示的 Cookie 内容' },
  ];

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>豆包 Cookie 配置</h1>
        <p style={{ fontSize: 14, color: 'var(--text-tertiary)' }}>配置豆包 Cookie 以使用 AI 图片和视频生成功能</p>
      </div>

      {/* Status */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '18px 22px',
        borderRadius: 14, marginBottom: 28,
        background: cookieValid ? 'var(--success-bg)' : 'var(--error-bg)',
        border: `1px solid ${cookieValid ? 'var(--success)' : 'var(--error)'}20`,
      }}>
        {cookieValid ? <CheckCircle2 size={22} style={{ color: 'var(--success)' }} /> : <XCircle size={22} style={{ color: 'var(--error)' }} />}
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: cookieValid ? 'var(--success)' : 'var(--error)' }}>
            {cookieValid ? 'Cookie 已配置' : 'Cookie 未配置'}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
            {cookieValid ? '图片和视频生成功能可用' : '需要配置 Cookie 才能使用 AI 生成功能'}
          </div>
        </div>
      </div>

      {/* Guide */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: '24px 28px', marginBottom: 28,
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 22 }}>
          📋 配置步骤
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 16 }}>
              {/* Timeline */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 28, flexShrink: 0 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: '50%',
                  background: 'var(--accent)', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 13, fontWeight: 700,
                }}>{s.step}</div>
                {i < steps.length - 1 && <div style={{ width: 1, flex: 1, minHeight: 16, background: 'var(--border)', margin: '4px 0' }} />}
              </div>
              {/* Content */}
              <div style={{ paddingBottom: 28 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>{s.title}</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {s.desc}
                  {s.link && (
                    <a href={s.link} target="_blank" rel="noopener" style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      marginLeft: 10, color: 'var(--accent)', fontWeight: 500,
                      textDecoration: 'none', fontSize: 12,
                    }}>
                      {s.linkLabel} →
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Input */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: '24px 28px',
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Key size={17} style={{ color: 'var(--accent)' }} />
          粘贴 Cookie
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 16 }}>将上一步复制的 Cookie 内容粘贴到下方</p>
        <textarea
          value={cookieInput}
          onChange={e => setCookieInput(e.target.value)}
          placeholder='[{"name":"session","value":"abc123..."},{"name":"token","value":"xyz..."}]'
          style={{
            width: '100%', height: 120, padding: '14px 16px',
            borderRadius: 12, border: '1px solid var(--border)',
            background: 'var(--bg)', color: 'var(--text)',
            fontFamily: 'JetBrains Mono, monospace', fontSize: 12, lineHeight: 1.6,
            resize: 'vertical', outline: 'none', transition: 'border-color 0.15s',
          }}
          onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
          onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
        />
        <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
          <button
            onClick={handleSave}
            disabled={!cookieInput.trim()}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              padding: '9px 22px', borderRadius: 10,
              border: 'none', background: 'var(--accent)', color: '#fff',
              fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
              cursor: cookieInput.trim() ? 'pointer' : 'not-allowed',
              opacity: cookieInput.trim() ? 1 : 0.4,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { if (cookieInput.trim()) e.currentTarget.style.background = 'var(--accent-hover)'; }}
            onMouseLeave={e => { if (cookieInput.trim()) e.currentTarget.style.background = 'var(--accent)'; }}
          >
            {saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
            {saved ? '已保存' : '保存 Cookie'}
          </button>
          <button
            onClick={async () => {
              try { setCookieInput(await navigator.clipboard.readText()); } catch { /* permission denied */ }
            }}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              padding: '9px 22px', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text-secondary)', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
              cursor: 'pointer', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; }}
          >
            <ClipboardPaste size={15} />
            从剪贴板读取
          </button>
        </div>
      </div>
    </div>
  );
}
