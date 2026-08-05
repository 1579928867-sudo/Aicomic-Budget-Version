import { Sidebar } from './components/Sidebar';
import { ChatPage } from './pages/ChatPage';
import { LibraryPage } from './pages/LibraryPage';
import { VideosPage } from './pages/VideosPage';
import { CookiePage } from './pages/CookiePage';
import { TasksPage } from './pages/TasksPage';
import { SettingsPage } from './pages/SettingsPage';
import { useAppStore } from './stores/app';

const PAGES: Record<string, React.ComponentType> = {
  chat: ChatPage,
  library: LibraryPage,
  videos: VideosPage,
  cookie: CookiePage,
  tasks: TasksPage,
  settings: SettingsPage,
};

export default function App() {
  const activePage = useAppStore(s => s.activePage);
  const Page = PAGES[activePage] || ChatPage;

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <Page />
      </main>
    </div>
  );
}
