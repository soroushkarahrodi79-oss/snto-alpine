import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { Settings, DailyLog, WeeklyCheckIn, MedicalDoc, AppData } from '../types';
import { DEFAULT_INJURY_DATE } from '../data/clinicalProfile';
import { todayStr } from '../utils/dateUtils';

const STORAGE_KEYS = {
  settings: 'scaphoid_settings',
  dailyLogs: 'scaphoid_daily_logs',
  weeklyCheckIns: 'scaphoid_weekly_checkins',
  medicalDocs: 'scaphoid_medical_docs',
};

const DEFAULT_SETTINGS: Settings = {
  injuryDate: DEFAULT_INJURY_DATE,
  side: 'right',
  nextAppointment: null,
  nextImaging: null,
  doctorClinic: '',
  hideNicotineCheck: false,
  darkMode: false,
};

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage quota exceeded — silently fail
  }
}

interface AppContextValue {
  settings: Settings;
  updateSettings: (patch: Partial<Settings>) => void;

  dailyLogs: DailyLog[];
  todayLog: DailyLog;
  updateTodayLog: (patch: Partial<DailyLog>) => void;

  weeklyCheckIns: WeeklyCheckIn[];
  upsertWeeklyCheckIn: (data: WeeklyCheckIn) => void;

  medicalDocs: MedicalDoc[];
  addMedicalDoc: (doc: MedicalDoc) => void;
  updateMedicalDoc: (id: string, patch: Partial<MedicalDoc>) => void;
  deleteMedicalDoc: (id: string) => void;

  exportData: () => void;
  importData: (json: string) => boolean;
  resetData: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

function emptyLog(date: string): DailyLog {
  return {
    date,
    castOk: false,
    fingersMoving: false,
    noWarningSymptoms: false,
    proteinNutrition: false,
    calciumNutrition: false,
    safeActivity: false,
    noNicotine: false,
    note: '',
  };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() =>
    load(STORAGE_KEYS.settings, DEFAULT_SETTINGS)
  );
  const [dailyLogs, setDailyLogs] = useState<DailyLog[]>(() =>
    load(STORAGE_KEYS.dailyLogs, [])
  );
  const [weeklyCheckIns, setWeeklyCheckIns] = useState<WeeklyCheckIn[]>(() =>
    load(STORAGE_KEYS.weeklyCheckIns, [])
  );
  const [medicalDocs, setMedicalDocs] = useState<MedicalDoc[]>(() =>
    load(STORAGE_KEYS.medicalDocs, [])
  );

  // Apply dark mode to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.darkMode ? 'dark' : 'light');
  }, [settings.darkMode]);

  useEffect(() => { save(STORAGE_KEYS.settings, settings); }, [settings]);
  useEffect(() => { save(STORAGE_KEYS.dailyLogs, dailyLogs); }, [dailyLogs]);
  useEffect(() => { save(STORAGE_KEYS.weeklyCheckIns, weeklyCheckIns); }, [weeklyCheckIns]);
  useEffect(() => { save(STORAGE_KEYS.medicalDocs, medicalDocs); }, [medicalDocs]);

  const updateSettings = useCallback((patch: Partial<Settings>) => {
    setSettings(s => ({ ...s, ...patch }));
  }, []);

  const today = todayStr();
  const todayLog: DailyLog =
    dailyLogs.find(l => l.date === today) ?? emptyLog(today);

  const updateTodayLog = useCallback((patch: Partial<DailyLog>) => {
    setDailyLogs(logs => {
      const existing = logs.find(l => l.date === today);
      if (existing) {
        return logs.map(l => l.date === today ? { ...l, ...patch } : l);
      }
      return [...logs, { ...emptyLog(today), ...patch }];
    });
  }, [today]);

  const upsertWeeklyCheckIn = useCallback((data: WeeklyCheckIn) => {
    setWeeklyCheckIns(list => {
      const idx = list.findIndex(w => w.weekKey === data.weekKey);
      if (idx >= 0) {
        const next = [...list];
        next[idx] = data;
        return next;
      }
      return [...list, data];
    });
  }, []);

  const addMedicalDoc = useCallback((doc: MedicalDoc) => {
    setMedicalDocs(d => [...d, doc]);
  }, []);

  const updateMedicalDoc = useCallback((id: string, patch: Partial<MedicalDoc>) => {
    setMedicalDocs(d => d.map(doc => doc.id === id ? { ...doc, ...patch } : doc));
  }, []);

  const deleteMedicalDoc = useCallback((id: string) => {
    setMedicalDocs(d => d.filter(doc => doc.id !== id));
  }, []);

  const exportData = useCallback(() => {
    const data: AppData = { settings, dailyLogs, weeklyCheckIns, medicalDocs };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `scaphoid-recovery-backup-${today}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [settings, dailyLogs, weeklyCheckIns, medicalDocs, today]);

  const importData = useCallback((json: string): boolean => {
    try {
      const data = JSON.parse(json) as AppData;
      if (data.settings) setSettings(data.settings);
      if (data.dailyLogs) setDailyLogs(data.dailyLogs);
      if (data.weeklyCheckIns) setWeeklyCheckIns(data.weeklyCheckIns);
      if (data.medicalDocs) setMedicalDocs(data.medicalDocs);
      return true;
    } catch {
      return false;
    }
  }, []);

  const resetData = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
    setDailyLogs([]);
    setWeeklyCheckIns([]);
    setMedicalDocs([]);
  }, []);

  return (
    <AppContext.Provider value={{
      settings, updateSettings,
      dailyLogs, todayLog, updateTodayLog,
      weeklyCheckIns, upsertWeeklyCheckIn,
      medicalDocs, addMedicalDoc, updateMedicalDoc, deleteMedicalDoc,
      exportData, importData, resetData,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
