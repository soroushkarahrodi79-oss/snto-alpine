import type { Settings } from '../types';

export function parseDate(dateStr: string): Date {
  // Parse YYYY-MM-DD as local date, not UTC
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function daysSinceInjury(injuryDate: string): number {
  const injury = parseDate(injuryDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  injury.setHours(0, 0, 0, 0);
  return Math.floor((today.getTime() - injury.getTime()) / (1000 * 60 * 60 * 24));
}

export function weeksSinceInjury(injuryDate: string): number {
  return Math.floor(daysSinceInjury(injuryDate) / 7) + 1;
}

export function addDays(dateStr: string, days: number): string {
  const d = parseDate(dateStr);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function addWeeks(dateStr: string, weeks: number): string {
  return addDays(dateStr, weeks * 7);
}

export function daysUntil(targetDate: string): number {
  const target = parseDate(targetDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

// Elapsed fraction of 12-week horizon (0.0 – 1.0, capped at 1.0)
// This is TIME elapsed, NOT bone healing.
export function elapsedFraction(injuryDate: string): number {
  const days = daysSinceInjury(injuryDate);
  return Math.min(1, Math.max(0, days / 84)); // 12 weeks = 84 days
}

export function formatDateFA(dateStr: string): string {
  const d = parseDate(dateStr);
  const months = [
    'ژانویه', 'فوریه', 'مارس', 'آوریل', 'مه', 'ژوئن',
    'ژوئیه', 'اوت', 'سپتامبر', 'اکتبر', 'نوامبر', 'دسامبر',
  ];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

export function isoWeekKey(dateStr: string): string {
  const d = parseDate(dateStr);
  const jan4 = new Date(d.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const diff = d.getTime() - startOfWeek1.getTime();
  const week = Math.floor(diff / (7 * 24 * 60 * 60 * 1000)) + 1;
  return `${d.getFullYear()}-W${String(week).padStart(2, '0')}`;
}

export function currentWeekKey(): string {
  return isoWeekKey(todayStr());
}

export function milestoneProgress(injuryDate: string): {
  week2: number;
  week6: number;
  week8: number;
  week12: number;
  current: number;
} {
  // All positions as fraction 0–1 of the 12-week (84-day) horizon
  return {
    week2: 14 / 84,
    week6: 42 / 84,
    week8: 56 / 84,
    week12: 1.0,
    current: elapsedFraction(injuryDate),
  };
}

export function nextGateLabel(settings: Settings): { label: string; date: string | null; daysLeft: number | null } {
  const candidates: Array<{ label: string; date: string }> = [];

  if (settings.nextAppointment) {
    candidates.push({ label: 'ویزیت بعدی', date: settings.nextAppointment });
  }
  if (settings.nextImaging) {
    candidates.push({ label: 'تصویربرداری بعدی', date: settings.nextImaging });
  }

  const today = todayStr();
  const future = candidates
    .filter(c => c.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date));

  if (future.length === 0) {
    // Fall back to 8-week checkpoint
    const week8Date = addWeeks(settings.injuryDate, 8);
    const d = daysUntil(week8Date);
    return { label: 'پنجره ارزیابی هفته ۸', date: week8Date, daysLeft: d };
  }

  const next = future[0];
  return { label: next.label, date: next.date, daysLeft: daysUntil(next.date) };
}
