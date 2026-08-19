import { useState } from 'react';
import { AppProvider, useApp } from './context/AppContext';
import BottomNav from './components/BottomNav';
import HomeScreen from './screens/HomeScreen';
import TodayScreen from './screens/TodayScreen';
import TimelineScreen from './screens/TimelineScreen';
import MedicalScreen from './screens/MedicalScreen';
import SettingsScreen from './screens/SettingsScreen';
import type { Tab } from './types';
import { daysSinceInjury, weeksSinceInjury } from './utils/dateUtils';

function AppShell() {
  const [tab, setTab] = useState<Tab>('home');
  const [showSettings, setShowSettings] = useState(false);
  const { settings } = useApp();

  const days = daysSinceInjury(settings.injuryDate);
  const week = weeksSinceInjury(settings.injuryDate);

  const headerTitles: Record<Tab, string> = {
    home: '🦴 بهبود اسکافویید',
    today: 'امروز',
    timeline: 'تایم‌لاین',
    medical: 'مدارک پزشکی',
  };

  const headerSubs: Record<Tab, string> = {
    home: `روز ${days} — هفته ${week}`,
    today: 'چک روزانه',
    timeline: 'رویدادهای بالینی',
    medical: 'مراجع و فایل‌ها',
  };

  return (
    <div className="app-shell">
      {/* ── Header ───────────────────────────────────── */}
      <header className="header">
        <div>
          <div className="header-title">{headerTitles[tab]}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {headerSubs[tab]}
          </div>
        </div>
        <div className="header-actions">
          <button
            className="icon-btn"
            aria-label="تنظیمات"
            onClick={() => setShowSettings(true)}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── Main Content ─────────────────────────────── */}
      <main className="main-content" role="main">
        {tab === 'home' && <HomeScreen />}
        {tab === 'today' && <TodayScreen />}
        {tab === 'timeline' && <TimelineScreen />}
        {tab === 'medical' && <MedicalScreen />}
      </main>

      {/* ── Bottom Navigation ────────────────────────── */}
      <BottomNav active={tab} onChange={setTab} />

      {/* ── Settings Overlay ─────────────────────────── */}
      {showSettings && <SettingsScreen onClose={() => setShowSettings(false)} />}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
