import { useState, useRef, useEffect } from 'react';
import { Send, Upload, Loader2, Bot, User, Sparkles } from 'lucide-react';
import { chat } from '../api';
import { useAppStore } from '../stores/app';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'assistant', content: '你好！我是AI漫剧助手 🎬\n\n我可以帮你：\n• 生成新的漫画章节\n• 重新生成角色/场景图片\n• 查询素材信息\n• 管理视频制作\n\n请告诉我你想做什么？' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const chapterId = useAppStore(s => s.selectedChapterId);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await chat.send({ message: msg, chapter_id: chapterId ?? undefined });
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: res.reply }]);
    } catch (e: any) {
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: `抱歉，出错了: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Sparkles size={16} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">AI漫剧助手</h1>
            <p className="text-xs text-zinc-500">智能对话 · 意图识别 · 一键生成</p>
          </div>
          {chapterId && (
            <span className="ml-auto px-3 py-1 rounded-full bg-indigo-500/10 text-indigo-400 text-xs border border-indigo-500/20">
              当前章节 #{chapterId}
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto px-6 py-4 space-y-4">
        {messages.map(msg => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
                <Bot size={16} className="text-indigo-400" />
              </div>
            )}
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
              msg.role === 'user'
                ? 'bg-indigo-500 text-white rounded-br-md'
                : 'bg-zinc-800/50 border border-zinc-700/50 text-zinc-200 rounded-bl-md'
            }`}>
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-lg bg-zinc-700 border border-zinc-600 flex items-center justify-center shrink-0">
                <User size={16} className="text-zinc-300" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <Bot size={16} className="text-indigo-400" />
            </div>
            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-2xl rounded-bl-md px-4 py-3">
              <Loader2 size={18} className="text-indigo-400 animate-spin" />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-zinc-800 bg-zinc-950/80 backdrop-blur-sm">
        <div className="flex gap-2">
          <button className="p-2.5 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition-colors">
            <Upload size={18} />
          </button>
          <div className="flex-1 relative">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息，Enter 发送..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-zinc-600">
              Enter ↵
            </span>
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="p-2.5 rounded-xl bg-indigo-500 text-white hover:bg-indigo-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
