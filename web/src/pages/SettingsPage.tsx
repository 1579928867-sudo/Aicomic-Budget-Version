import { useState, useEffect } from 'react';
import { Settings, Zap, Server, Key, ShieldAlert, CheckCircle2, Save } from 'lucide-react';
import { settings } from '../api';

export function SettingsPage() {
  const [llmConfig, setLlmConfig] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [backend, setBackend] = useState('deepseek');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    settings.llm().then(c => {
      setLlmConfig(c);
      setBackend(c.backend || 'deepseek');
      setModel(c.model || '');
      setBaseUrl(c.base_url || '');
    }).catch(() => {});
    fetch('/api/health').then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings/llm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          backend, api_key: apiKey, model,
          base_url: baseUrl,
        }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
        // 重新加载脱敏后的配置
        settings.llm().then(setLlmConfig).catch(() => {});
      }
    } catch {}
    setSaving(false);
  };

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 28 }}>系统设置</h1>

      {/* System Status */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '22px 28px', marginBottom: 20 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Server size={16} style={{ color: 'var(--accent)' }} /> 系统状态
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <StatusItem label="API 服务" ok={!!health} detail={health?.version || '未知'} />
          <StatusItem label="AI 引擎" ok={health?.orchestrator_ready} detail={health?.orchestrator_ready ? '已就绪' : '未就绪'} />
        </div>
      </div>

      {/* LLM Config — editable */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '24px 28px', marginBottom: 20 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Zap size={16} style={{ color: '#D49B4A' }} /> LLM 配置
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 20 }}>
          配置你自己的大模型 API，每个人的 Key 独立存储，不会共享
        </p>

        {/* Notice */}
        <div style={{ display: 'flex', gap: 10, padding: '12px 16px', borderRadius: 10, background: '#FDF5E8', border: '1px solid #F0D0A0', marginBottom: 20 }}>
          <ShieldAlert size={16} style={{ color: '#D49B4A', flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 12, color: '#8A6A30', lineHeight: 1.6 }}>
            你的 API Key 仅存储在你的本地服务器配置文件 <code style={{ background: 'rgba(0,0,0,0.06)', padding: '1px 6px', borderRadius: 3, fontSize: 11 }}>config/settings.yaml</code> 中，不会被其他人看到或使用。
          </div>
        </div>

        {/* Backend */}
        <label style={{ display: 'block', marginBottom: 14 }}>
          <span style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>LLM 后端</span>
          <select
            value={backend}
            onChange={e => setBackend(e.target.value)}
            style={{
              width: '100%', padding: '10px 14px', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text)', fontFamily: 'inherit', fontSize: 14, outline: 'none',
              cursor: 'pointer', transition: 'border-color 0.15s',
            }}
            onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
          >
            <option value="deepseek">DeepSeek</option>
            <option value="claude">Claude (Anthropic)</option>
          </select>
        </label>

        {/* API Key */}
        <label style={{ display: 'block', marginBottom: 14 }}>
          <span style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            API Key
            {llmConfig?.has_key && <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: 8 }}>当前: {llmConfig?.api_key_masked}</span>}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={llmConfig?.has_key ? '输入新 Key 以替换，留空则保留当前' : '输入你的 API Key'}
              style={{
                flex: 1, padding: '10px 14px', borderRadius: 10,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text)', fontFamily: 'inherit', fontSize: 14,
                outline: 'none', transition: 'border-color 0.15s',
              }}
              onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
              onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
            />
            <button
              onClick={() => setShowKey(!showKey)}
              style={{
                padding: '10px 14px', borderRadius: 10, border: '1px solid var(--border)',
                background: 'var(--surface)', color: 'var(--text-tertiary)', fontFamily: 'inherit', fontSize: 12,
                cursor: 'pointer', whiteSpace: 'nowrap', transition: 'all 0.12s',
              }}
            >{showKey ? '隐藏' : '显示'}</button>
          </div>
        </label>

        {/* Model */}
        <label style={{ display: 'block', marginBottom: 14 }}>
          <span style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>模型</span>
          <input
            type="text" value={model}
            onChange={e => setModel(e.target.value)}
            placeholder={backend === 'deepseek' ? 'deepseek-chat' : 'claude-sonnet-5-20251001'}
            style={{
              width: '100%', padding: '10px 14px', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text)', fontFamily: 'inherit', fontSize: 14,
              outline: 'none', transition: 'border-color 0.15s',
            }}
            onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
          />
        </label>

        {/* Base URL (for DeepSeek-compatible) */}
        {backend === 'deepseek' && (
          <label style={{ display: 'block', marginBottom: 20 }}>
            <span style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>API 地址 (可选)</span>
            <input
              type="text" value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="https://api.deepseek.com"
              style={{
                width: '100%', padding: '10px 14px', borderRadius: 10,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text)', fontFamily: 'inherit', fontSize: 14,
                outline: 'none', transition: 'border-color 0.15s',
              }}
              onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
              onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
            />
          </label>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '10px 24px', borderRadius: 10, border: 'none',
            background: 'var(--accent)', color: '#fff',
            fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer',
            opacity: saving ? 0.5 : 1, transition: 'all 0.15s',
          }}
          onMouseEnter={e => { if (!saving) e.currentTarget.style.background = 'var(--accent-hover)'; }}
          onMouseLeave={e => { if (!saving) e.currentTarget.style.background = 'var(--accent)'; }}
        >
          {saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
          {saved ? '已保存' : '保存配置'}
        </button>
      </div>

      {/* About */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '22px 28px' }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Key size={16} style={{ color: 'var(--success)' }} /> 关于
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Row label="版本" value="v0.2.0" />
          <Row label="技术栈" value="FastAPI + React + SQLite" />
          <Row label="图片引擎" value="豆包 Browser Automation" />
          <Row label="LLM" value="DeepSeek / Claude (用户自配)" />
          <Row label="字体" value="Noto Sans SC + Inter" />
        </div>
      </div>
    </div>
  );
}

function StatusItem({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', borderRadius: 10, background: 'var(--surface-alt)', border: '1px solid var(--border)' }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: ok ? 'var(--success)' : 'var(--text-tertiary)' }} />
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 1 }}>{detail}</div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{value}</span>
    </div>
  );
}
