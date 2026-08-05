import { useState, useEffect } from 'react';
import { Settings, Key, Zap, Server, CheckCircle2 } from 'lucide-react';
import { settings } from '../api';

export function SettingsPage() {
  const [llmConfig, setLlmConfig] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    settings.llm().then(setLlmConfig).catch(() => {});
    fetch('/api/health').then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-xl font-bold text-white mb-6">系统设置</h1>

      {/* System Status */}
      <div className="glass-card p-5 mb-4">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Server size={16} className="text-indigo-400" /> 系统状态
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <StatusItem label="API 服务" ok={!!health} detail={health?.version} />
          <StatusItem label="AI引擎就绪" ok={health?.orchestrator_ready} detail={health?.orchestrator_ready ? '已就绪' : '未就绪'} />
        </div>
      </div>

      {/* LLM Config */}
      <div className="glass-card p-5 mb-4">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Zap size={16} className="text-amber-400" /> LLM 配置
        </h3>
        {llmConfig && (
          <div className="space-y-3">
            <ConfigRow label="后端" value={llmConfig.backend?.toUpperCase()} />
            <ConfigRow label="模型" value={llmConfig.model} />
            <ConfigRow label="API Key" value={llmConfig.api_key || '未配置'} />
          </div>
        )}
        <p className="text-[11px] text-zinc-600 mt-4">
          修改 LLM 配置请编辑 config/settings.yaml 或设置环境变量后重启服务
        </p>
      </div>

      {/* Performance */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Key size={16} className="text-emerald-400" /> 关于
        </h3>
        <div className="space-y-3">
          <ConfigRow label="版本" value="v0.1.0" />
          <ConfigRow label="技术栈" value="FastAPI + React + SQLite" />
          <ConfigRow label="图片引擎" value="豆包/即梦 Browser Automation" />
          <ConfigRow label="LLM" value="DeepSeek / Claude" />
        </div>
      </div>
    </div>
  );
}

function StatusItem({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center gap-2 p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-400 pulse-glow' : 'bg-zinc-600'}`} />
      <div>
        <div className="text-xs font-medium text-zinc-300">{label}</div>
        <div className="text-[11px] text-zinc-500">{detail || (ok ? '正常' : '异常')}</div>
      </div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-zinc-800/50 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-xs text-zinc-200 font-mono">{value}</span>
    </div>
  );
}
