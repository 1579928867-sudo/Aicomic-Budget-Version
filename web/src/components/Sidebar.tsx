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
    <aside className="w-56 h-screen bg-zinc-950 border-r border-zinc-800 flex flex-col shrink-0">
      {/* Logo */}
      <div className="p-5 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-lg">
            🎬
          </div>
          <div>
            <div className="text-sm font-bold text-white tracking-tight">AI漫剧</div>
            <div className="text-[10px] text-zinc-500">Comic Video Studio</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-3 space-y-1">
        {NAV.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActivePage(key)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 group ${
              activePage === key
                ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 border border-transparent'
            }`}
          >
            <Icon size={18} className={activePage === key ? 'text-indigo-400' : 'text-zinc-500 group-hover:text-zinc-300'} />
            <span className="font-medium">{label}</span>
            {activePage === key && (
              <div className="ml-auto w-1.5 h-1.5 rounded-full bg-indigo-400" />
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-zinc-800">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          v0.1.0
        </div>
      </div>
    </aside>
  );
}
