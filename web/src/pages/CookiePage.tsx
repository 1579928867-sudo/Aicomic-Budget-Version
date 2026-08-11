import { useState, useEffect, useRef } from 'react';
import { CheckCircle2, XCircle, Save, Key, ClipboardPaste, Monitor, Loader2, ArrowRight, Play } from 'lucide-react';
import { settings } from '../api';

export function CookiePage() {
  const [cookieValid, setCookieValid] = useState(false);
  const [cookieInput, setCookieInput] = useState('');
  const [saved, setSaved] = useState(false);

  // ── 一键自动登录状态 ──
  const [autoState, setAutoState] = useState<'idle' | 'starting' | 'waiting' | 'saving' | 'success' | 'error'>('idle');
  const [autoError, setAutoError] = useState('');
  const pollRef = useRef<any>(null);

  useEffect(() => {
    settings.cookieStatus().then(r => setCookieValid(r.valid)).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
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

  const handleAutoLogin = async () => {
    setAutoState('starting');
    setAutoError('');
    try {
      await settings.cookieAuto();
      setAutoState('waiting');
    } catch (e: any) {
      setAutoState('error');
      setAutoError(e.message || '启动失败');
    }
  };

  const handleConfirmLogin = async () => {
    setAutoState('saving');
    try {
      const res = await settings.cookieAutoConfirm();
      setAutoState('success');
      setCookieValid(true);
      setAutoError(res.message || '');
    } catch (e: any) {
      setAutoState('error');
      setAutoError(e.message || '确认失败');
    }
  };

  const handleCancelLogin = async () => {
    try { await settings.cookieAutoCancel(); } catch {}
    setAutoState('idle');
    setAutoError('');
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

      {/* ── 一键自动登录 ── */}
      <div style={{
        background: 'var(--surface)', border: `1px solid ${autoState === 'success' ? 'var(--success)' : autoState === 'error' ? 'var(--error)' : 'var(--border)'}`,
        borderRadius: 16, padding: '24px 28px', marginBottom: 28,
        ...(autoState === 'waiting' ? { borderColor: '#3B82C0', boxShadow: '0 0 0 3px rgba(59,130,192,0.1)' } : {}),
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Monitor size={17} style={{ color: 'var(--accent)' }} />
          一键自动登录
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '3px 10px', borderRadius: 100,
            background: 'var(--accent-light)', color: 'var(--accent)',
            letterSpacing: '0.03em',
          }}>推荐</span>
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 18, lineHeight: 1.6 }}>
          自动打开浏览器 → 你在浏览器中扫码或输入手机号登录 → 系统自动检测登录成功并保存 Cookie
        </p>

        {/* Auto login flow visual */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px', borderRadius: 12,
          background: 'var(--surface-alt)', border: '1px solid var(--border)',
          marginBottom: 18,
        }}>
          {/* Step indicators */}
          {[
            { label: '打开浏览器', done: autoState !== 'idle' },
            { label: '手动登录', done: autoState === 'saving' || autoState === 'success' },
            { label: '自动保存', done: autoState === 'success', active: autoState === 'saving' },
          ].map((s, i, arr) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, flex: i === 1 ? 1 : 'none' }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, flexShrink: 0,
                ...(s.done
                  ? { background: 'var(--success)', color: '#fff' }
                  : (autoState === 'waiting' && i === 1) || s.active
                  ? { background: '#3B82C0', color: '#fff', animation: 'pulse 1.5s ease-in-out infinite' }
                  : { background: 'var(--surface-hover)', color: 'var(--text-tertiary)' }),
              }}>
                {s.done ? <CheckCircle2 size={13} /> : ((autoState === 'waiting' && i === 1) || s.active ? <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite' }} /> : i + 1)}
              </div>
              <span style={{
                fontSize: 12, fontWeight: 500,
                color: s.done ? 'var(--text)' : 'var(--text-tertiary)',
              }}>{s.label}</span>
              {i < arr.length - 1 && (
                <ArrowRight size={14} style={{ color: 'var(--text-tertiary)', opacity: 0.4, margin: '0 6px' }} />
              )}
            </div>
          ))}
        </div>

        {/* Status messages */}
        {autoState === 'waiting' && (
          <div style={{
            padding: '16px 18px', borderRadius: 10,
            background: '#E8F2FD', border: '1px solid #B8D8F0',
            marginBottom: 18,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <Loader2 size={15} style={{ color: '#3B82C0', animation: 'spin 0.7s linear infinite', flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1a5a8a' }}>浏览器已打开</div>
                <div style={{ fontSize: 12, color: '#4a8ab0', marginTop: 2 }}>
                  浏览器窗口已打开，请在浏览器中扫码或输入手机号登录豆包。<strong>登录成功后请在下方点击「确认已登录」。</strong>
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleConfirmLogin}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  padding: '10px 24px', borderRadius: 10,
                  border: 'none', background: '#3B82C0', color: '#fff',
                  fontFamily: 'inherit', fontSize: 13, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = '#2563A0'; }}
                onMouseLeave={e => { e.currentTarget.style.background = '#3B82C0'; }}
              >
                <CheckCircle2 size={15} /> 确认已登录
              </button>
              <button
                onClick={handleCancelLogin}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  padding: '10px 20px', borderRadius: 10,
                  border: '1px solid #B8D8F0', background: '#fff',
                  color: '#5C5A57', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                <XCircle size={15} /> 取消
              </button>
            </div>
          </div>
        )}
        {autoState === 'saving' && (
          <div style={{
            padding: '16px 18px', borderRadius: 10,
            background: '#FFF8E7', border: '1px solid #F0D89A',
            marginBottom: 18, display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <Loader2 size={15} style={{ color: '#D4A017', animation: 'spin 0.7s linear infinite', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#8B6914' }}>保存中…</div>
              <div style={{ fontSize: 12, color: '#A68A32', marginTop: 2 }}>
                正在检测登录状态并保存 Cookie，请稍候…
              </div>
            </div>
          </div>
        )}
        {autoState === 'success' && (
          <div style={{
            padding: '12px 16px', borderRadius: 10,
            background: 'var(--success-bg)', border: '1px solid var(--success)40',
            marginBottom: 18, display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <CheckCircle2 size={16} style={{ color: 'var(--success)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--success)' }}>已保存 ✓</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Cookie 已保存，浏览器已关闭。{autoError ? `（${autoError}）` : '现在可以使用 AI 生成功能了！'}
              </div>
            </div>
          </div>
        )}
        {autoState === 'error' && (
          <div style={{
            padding: '12px 16px', borderRadius: 10,
            background: 'var(--error-bg)', border: '1px solid var(--error)40',
            marginBottom: 18, display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <XCircle size={16} style={{ color: 'var(--error)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--error)' }}>自动登录失败</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                {autoError || '请确认 Playwright 已安装：pip install playwright && playwright install chromium'}<br />
                你也可以使用下方手动方式粘贴 Cookie。
              </div>
            </div>
          </div>
        )}

        <button
          onClick={handleAutoLogin}
          disabled={autoState === 'waiting' || autoState === 'starting' || autoState === 'saving'}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 10,
            padding: '12px 28px', borderRadius: 12,
            border: 'none',
            background: (autoState === 'waiting' || autoState === 'saving')
              ? 'var(--surface-hover)'
              : 'linear-gradient(135deg, #3B82C0 0%, #2563A0 100%)',
            color: (autoState === 'waiting' || autoState === 'saving') ? 'var(--text-tertiary)' : '#fff',
            fontFamily: 'inherit', fontSize: 14, fontWeight: 700,
            cursor: autoState === 'waiting' ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s',
            boxShadow: (autoState === 'waiting' || autoState === 'saving') ? 'none' : '0 4px 16px rgba(59,130,192,0.3)',
          }}
          onMouseEnter={e => {
            if (autoState !== 'waiting' && autoState !== 'starting' && autoState !== 'saving') {
              e.currentTarget.style.transform = 'translateY(-1px)';
              e.currentTarget.style.boxShadow = '0 6px 24px rgba(59,130,192,0.4)';
            }
          }}
          onMouseLeave={e => {
            if (autoState !== 'waiting' && autoState !== 'starting' && autoState !== 'saving') {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(59,130,192,0.3)';
            }
          }}
        >
          {autoState === 'starting' ? (
            <><Loader2 size={18} style={{ animation: 'spin 0.7s linear infinite' }} /> 启动中…</>
          ) : autoState === 'waiting' ? (
            <><Loader2 size={18} style={{ animation: 'spin 0.7s linear infinite' }} /> 等待登录…</>
          ) : autoState === 'saving' ? (
            <><Loader2 size={18} style={{ animation: 'spin 0.7s linear infinite' }} /> 保存中…</>
          ) : (
            <><Play size={18} /> 打开浏览器自动登录</>
          )}
        </button>

        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 14 }}>
          需要安装 Playwright 和 Chromium
        </span>
      </div>

      {/* ── 手动方式 (折叠) ── */}
      <details style={{ marginBottom: 28 }}>
        <summary style={{
          padding: '10px 0', cursor: 'pointer',
          fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)',
          userSelect: 'none',
        }}>
          或手动复制 Cookie（备用方式）
        </summary>

        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 16, padding: '24px 28px', marginTop: 12,
        }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 22 }}>
            📋 手动配置步骤
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {steps.map((s, i) => (
              <div key={i} style={{ display: 'flex', gap: 16 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 28, flexShrink: 0 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: '50%',
                    background: 'var(--accent)', color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 700,
                  }}>{s.step}</div>
                  {i < steps.length - 1 && <div style={{ width: 1, flex: 1, minHeight: 16, background: 'var(--border)', margin: '4px 0' }} />}
                </div>
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

          {/* Input */}
          <div style={{
            background: 'var(--surface)', borderTop: '1px solid var(--border)',
            marginTop: 8, paddingTop: 20,
          }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Key size={17} style={{ color: 'var(--accent)' }} />
              粘贴 Cookie
            </h3>
            <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 16 }}>将复制的 Cookie 内容粘贴到下方</p>
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
              <button onClick={handleSave} disabled={!cookieInput.trim()} style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '9px 22px', borderRadius: 10,
                border: 'none', background: 'var(--accent)', color: '#fff',
                fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
                cursor: cookieInput.trim() ? 'pointer' : 'not-allowed',
                opacity: cookieInput.trim() ? 1 : 0.4,
                transition: 'all 0.15s',
              }}>
                {saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
                {saved ? '已保存' : '保存 Cookie'}
              </button>
              <button onClick={async () => {
                try { setCookieInput(await navigator.clipboard.readText()); } catch {}
              }} style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '9px 22px', borderRadius: 10,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text-secondary)', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
                cursor: 'pointer', transition: 'all 0.15s',
              }}>
                <ClipboardPaste size={15} />
                从剪贴板读取
              </button>
            </div>
          </div>
        </div>
      </details>

      {/* Spin + pulse keyframes */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(59,130,192,0.4); } 50% { box-shadow: 0 0 0 8px rgba(59,130,192,0); } }
      `}</style>
    </div>
  );
}
