import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  daysSinceInjury,
  weeksSinceInjury,
  addWeeks,
  daysUntil,
  elapsedFraction,
  formatDateFA,
  isoWeekKey,
  currentWeekKey,
  todayStr,
} from '../dateUtils';
import type { Settings } from '../../types';
import { nextGateLabel } from '../dateUtils';

// Mock "today" to 2026-08-19 for deterministic tests
const FIXED_TODAY = new Date(2026, 7, 19); // Aug 19 2026

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_TODAY);
});

afterEach(() => {
  vi.useRealTimers();
});

const INJURY = '2026-07-30';

describe('daysSinceInjury', () => {
  it('returns 20 days from 2026-07-30 to 2026-08-19', () => {
    expect(daysSinceInjury(INJURY)).toBe(20);
  });

  it('returns 0 on the same day as injury', () => {
    vi.setSystemTime(new Date(2026, 6, 30));
    expect(daysSinceInjury(INJURY)).toBe(0);
  });
});

describe('weeksSinceInjury', () => {
  it('returns week 3 at day 20 (floor(20/7)+1 = 3)', () => {
    expect(weeksSinceInjury(INJURY)).toBe(3);
  });
});

describe('addWeeks', () => {
  it('8 weeks from 2026-07-30 is 2026-09-24', () => {
    expect(addWeeks(INJURY, 8)).toBe('2026-09-24');
  });

  it('12 weeks from 2026-07-30 is 2026-10-22', () => {
    expect(addWeeks(INJURY, 12)).toBe('2026-10-22');
  });
});

describe('daysUntil', () => {
  it('returns positive days for a future date', () => {
    expect(daysUntil('2026-09-01')).toBeGreaterThan(0);
  });

  it('returns negative days for a past date', () => {
    expect(daysUntil('2026-08-01')).toBeLessThan(0);
  });

  it('returns 0 for today', () => {
    expect(daysUntil(todayStr())).toBe(0);
  });
});

describe('elapsedFraction', () => {
  it('returns a value between 0 and 1', () => {
    const f = elapsedFraction(INJURY);
    expect(f).toBeGreaterThanOrEqual(0);
    expect(f).toBeLessThanOrEqual(1);
  });

  it('is ~0.238 at day 20 of 84', () => {
    // 20/84 ≈ 0.238
    const f = elapsedFraction(INJURY);
    expect(f).toBeCloseTo(20 / 84, 2);
  });

  it('never labels elapsed time as bone healing — value must be ≤ 1', () => {
    // injury 200 days ago
    const old = '2026-02-01';
    expect(elapsedFraction(old)).toBeLessThanOrEqual(1);
  });

  it('caps at 1.0 even past 12 weeks', () => {
    vi.setSystemTime(new Date(2027, 0, 1));
    expect(elapsedFraction(INJURY)).toBe(1);
  });
});

describe('elapsedFraction — no healing percentage semantics', () => {
  it('is strictly called "elapsed fraction" not healing fraction in code', () => {
    // This is a documentation/semantic test:
    // The function is named elapsedFraction and its returned value
    // must never be displayed as "X% healed" — only as "X% of 12-week horizon elapsed"
    // We verify the value is the same as time-based calculation:
    const expected = Math.min(1, Math.max(0, 20 / 84));
    expect(elapsedFraction(INJURY)).toBe(expected);
  });
});

describe('formatDateFA', () => {
  it('formats 2026-08-13 correctly in Persian calendar labels', () => {
    // Should contain the year 2026 and day 13
    const result = formatDateFA('2026-08-13');
    expect(result).toContain('2026');
    expect(result).toContain('13');
    expect(result).toContain('اوت'); // August
  });
});

describe('isoWeekKey', () => {
  it('returns a string in YYYY-Www format', () => {
    const key = isoWeekKey('2026-08-19');
    expect(key).toMatch(/^\d{4}-W\d{2}$/);
  });

  it('same day returns same key as currentWeekKey', () => {
    expect(isoWeekKey(todayStr())).toBe(currentWeekKey());
  });
});

describe('nextGateLabel', () => {
  const baseSettings: Settings = {
    injuryDate: INJURY,
    side: 'right',
    nextAppointment: null,
    nextImaging: null,
    doctorClinic: '',
    hideNicotineCheck: false,
    darkMode: false,
  };

  it('falls back to week-8 checkpoint when no appointments set', () => {
    const gate = nextGateLabel(baseSettings);
    expect(gate.label).toContain('هفته ۸');
    expect(gate.date).toBe(addWeeks(INJURY, 8));
  });

  it('uses nextAppointment when it is in the future', () => {
    const s = { ...baseSettings, nextAppointment: '2026-09-10' };
    const gate = nextGateLabel(s);
    expect(gate.label).toBe('ویزیت بعدی');
    expect(gate.date).toBe('2026-09-10');
  });

  it('picks the soonest future date when both appointment and imaging set', () => {
    const s = { ...baseSettings, nextAppointment: '2026-09-10', nextImaging: '2026-09-01' };
    const gate = nextGateLabel(s);
    expect(gate.date).toBe('2026-09-01');
  });

  it('ignores past appointments', () => {
    const s = { ...baseSettings, nextAppointment: '2026-08-01' }; // past
    const gate = nextGateLabel(s);
    expect(gate.label).toContain('هفته ۸');
  });
});

describe('todayStr', () => {
  it('returns YYYY-MM-DD format', () => {
    expect(todayStr()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('matches the mocked date', () => {
    expect(todayStr()).toBe('2026-08-19');
  });
});
