import { useState, useEffect } from 'react';
import { Cookie, CheckCircle2, XCircle, Save, ExternalLink, Copy, Key } from 'lucide-react';
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
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: cookieInput }),
      });
      setSaved(true);
      setCookieValid(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  const steps = [
    { icon: '1', text: '打开豆包/即梦网站', sub: '访问 jimeng.jianying.com', link: 'https://jimeng.jianying.com' },
    { icon: '2', text: '登录你的账号', sub: '确保已登录豆包账号' },
    { icon: '3', text: '打开开发者工具', sub: '按 F12 或 Ctrl+Shift+I' },
    { icon: '4', text: '找到 Cookies', sub: 'Application → Cookies → 复制全部' },
  ];

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-white mb-1">豆包 Cookie 配置</h1>
        <p className="text-sm text-zinc-500">配置豆包Cookie以使用AI图片和视频生成功能</p>
      </div>

      {/* Status */}
      <div className={`glass-card p-4 mb-6 flex items-center gap-3 ${cookieValid ? 'border-emerald-500/30' : 'border-red-500/30'}`}>
        {cookieValid ? (
          <CheckCircle2 size={20} className="text-emerald-400" />
        ) : (
          <XCircle size={20} className="text-red-400" />
        )}
        <div>
          <div className={`text-sm font-semibold ${cookieValid ? 'text-emerald-400' : 'text-red-400'}`}>
            {cookieValid ? 'Cookie 已配置' : 'Cookie 未配置'}
          </div>
          <div className="text-xs text-zinc-500">
            {cookieValid ? '图片和视频生成功能可用' : '需要配置Cookie才能使用生成功能'}
          </div>
        </div>
      </div>

      {/* Guide */}
      <div className="glass-card p-5 mb-6">
        <h3 className="text-sm font-semibold text-white mb-4">📋 配置步骤</h3>
        <div className="space-y-4">
          {steps.map((s, i) => (
            <div key={i} className="flex gap-3">
              <div className="w-7 h-7 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-indigo-400">{s.icon}</span>
              </div>
              <div className="flex-1">
                <div className="text-sm text-zinc-200">{s.text}</div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  {s.sub}
                  {s.link && (
                    <a href={s.link} target="_blank" className="ml-2 text-indigo-400 hover:underline inline-flex items-center gap-1">
                      打开 <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Key size={16} className="text-indigo-400" />
          粘贴 Cookie
        </h3>
        <textarea
          value={cookieInput}
          onChange={e => setCookieInput(e.target.value)}
          placeholder='粘贴从浏览器复制的Cookie JSON...'
          className="w-full h-32 bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500/50 transition-colors resize-none font-mono"
        />
        <div className="flex gap-2 mt-3">
          <button
            onClick={handleSave}
            disabled={!cookieInput.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white text-sm font-medium hover:bg-indigo-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            {saved ? <CheckCircle2 size={16} /> : <Save size={16} />}
            {saved ? '已保存' : '保存 Cookie'}
          </button>
          <button
            onClick={async () => {
              try { const t = await navigator.clipboard.readText(); setCookieInput(t); } catch {}
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-700 text-zinc-300 text-sm hover:bg-zinc-600 transition-colors"
          >
            <Copy size={16} /> 从剪贴板粘贴
          </button>
        </div>
      </div>
    </div>
  );
}
