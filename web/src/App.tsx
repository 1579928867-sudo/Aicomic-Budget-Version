import { lazy, Suspense } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatPage } from './pages/ChatPage';
import { LibraryPage } from './pages/LibraryPage';
import { VideosPage } from './pages/VideosPage';
import { CookiePage } from './pages/CookiePage';
import { TasksPage } from './pages/TasksPage';
import { SettingsPage } from './pages/SettingsPage';
import { useAppStore } from './stores/app';

const HomePage = lazy(() => import('./pages/HomePage'));

const PAGES: Record<string, React.ComponentType> = {
  chat: ChatPage, library: LibraryPage, videos: VideosPage,
  cookie: CookiePage, tasks: TasksPage, settings: SettingsPage,
};

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

export default function App() {
  const activePage = useAppStore(s => s.activePage);

  if (activePage === 'home') {
    return (
      <Suspense fallback={<LoadingScreen />}>
        <HomePage />
      </Suspense>
    );
  }

  const Page = PAGES[activePage] || ChatPage;

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="flex-1 overflow-auto" style={{ padding: '40px' }}>
        <Page />
      </main>
    </div>
  );
}
