import { lazy, Suspense, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { ChatPage } from './pages/ChatPage';
import { LibraryPage } from './pages/LibraryPage';
import { VideosPage } from './pages/VideosPage';
import { CookiePage } from './pages/CookiePage';
import { TasksPage } from './pages/TasksPage';
import { SettingsPage } from './pages/SettingsPage';

const HomePage = lazy(() => import('./pages/HomePage'));

function LoadingScreen() {
  return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <div style={{
        width: 40, height: 40, borderRadius: '50%',
        border: '3px solid var(--border)', borderTopColor: 'var(--accent)',
        animation: 'spin 0.7s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// URL path → page key and component
const PAGES: Record<string, React.ComponentType> = {
  chat: ChatPage, library: LibraryPage, videos: VideosPage,
  cookie: CookiePage, tasks: TasksPage, settings: SettingsPage,
};

const PATH_TO_KEY: Record<string, string> = {
  '/chat': 'chat', '/library': 'library', '/videos': 'videos',
  '/cookie': 'cookie', '/tasks': 'tasks', '/settings': 'settings',
};

// All inner pages always mounted to preserve state (chat messages, scroll, etc.)
function WorkArea() {
  const location = useLocation();
  const loadedPages = useRef<Set<string>>(new Set(['chat']));
  const pageKey = PATH_TO_KEY[location.pathname] || 'chat';
  loadedPages.current.add(pageKey);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      {Object.entries(PAGES).map(([key, Component]) => (
        loadedPages.current.has(key) ? (
          <main key={key} className="flex-1 overflow-auto" style={{ padding: '40px', display: key === pageKey ? 'block' : 'none' }}>
            <Component />
          </main>
        ) : null
      ))}
    </div>
  );
}

export default function App() {
  const location = useLocation();

  if (location.pathname === '/') {
    return (
      <Suspense fallback={<LoadingScreen />}>
        <HomePage />
      </Suspense>
    );
  }

  return <WorkArea />;
}
