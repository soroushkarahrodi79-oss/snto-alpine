import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { todayStr, formatDateFA, currentWeekKey, daysSinceInjury } from '../utils/dateUtils';
import type { WeeklyCheckIn } from '../types';

type DailyCheckKey = 'castOk' | 'fingersMoving' | 'noWarningSymptoms' |
  'proteinNutrition' | 'calciumNutrition' | 'safeActivity' | 'noNicotine';

interface CheckItem {
  key: DailyCheckKey;
  label: string;
  desc: string;
  alwaysShow?: boolean;
}

const CHECKS: CheckItem[] = [
  {
    key: 'castOk',
    label: 'گچ سالم است',
    desc: 'خشک، سالم، نه خیلی تنگ و نه خیلی شل',
    alwaysShow: true,
  },
  {
    key: 'fingersMoving',
    label: 'انگشتان حرکت می‌کنند',
    desc: 'حرکت طبیعی انگشتان آزاد',
    alwaysShow: true,
  },
  {
    key: 'noWarningSymptoms',
    label: 'علائم هشداری جدید نیست',
    desc: 'بی‌حسی، تغییر رنگ یا درد شدید نیست',
    alwaysShow: true,
  },
  {
    key: 'proteinNutrition',
    label: 'تغذیه پروتئینی',
    desc: 'پروتئین کافی در وعده‌های امروز',
    alwaysShow: true,
  },
  {
    key: 'calciumNutrition',
    label: 'کلسیم / تغذیه متعادل',
    desc: 'غذاهای حاوی کلسیم یا جایگزین‌های مناسب',
    alwaysShow: true,
  },
  {
    key: 'safeActivity',
    label: 'فعالیت ایمن',
    desc: 'حرکت با بدن، بدون آسیب به گچ',
    alwaysShow: true,
  },
  {
    key: 'noNicotine',
    label: 'بدون نیکوتین',
    desc: 'نیکوتین بهبود استخوان را کند می‌کند',
    alwaysShow: false,
  },
];

export default function TodayScreen() {
  const { todayLog, updateTodayLog, settings, weeklyCheckIns, upsertWeeklyCheckIn } = useApp();
  const today = todayStr();
  const weekKey = currentWeekKey();
  const daysIn = daysSinceInjury(settings.injuryDate);

  const thisWeekCheckIn = weeklyCheckIns.find(w => w.weekKey === weekKey);
  const showWeekly = daysIn >= 7 && !thisWeekCheckIn;

  const completed = CHECKS.filter(c => {
    if (c.key === 'noNicotine' && settings.hideNicotineCheck) return false;
    return todayLog[c.key];
  }).length;

  const total = CHECKS.filter(c =>
    c.key === 'noNicotine' ? !settings.hideNicotineCheck : true
  ).length;

  return (
    <div className="screen">
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
          امروز
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          {formatDateFA(today)}
        </div>
      </div>

      {/* ── Daily Checklist ──────────────────────────────── */}
      <div className="section-card" style={{ marginBottom: 12 }}>
        <div style={{
          padding: '14px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid var(--border-light)',
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>چک روزانه</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {completed} از {total} تکمیل شده
            </div>
          </div>
          {completed === total && (
            <span className="badge badge-green">✓ کامل</span>
          )}
        </div>

        <div style={{ padding: '0 16px' }}>
          <div className="checklist">
            {CHECKS.map(item => {
              if (item.key === 'noNicotine' && settings.hideNicotineCheck) return null;
              const checked = Boolean(todayLog[item.key]);
              return (
                <div
                  key={item.key}
                  className="check-item"
                  onClick={() => updateTodayLog({ [item.key]: !checked })}
                  role="checkbox"
                  aria-checked={checked}
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && updateTodayLog({ [item.key]: !checked })}
                >
                  <div className={`check-box${checked ? ' checked' : ''}`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <div className="check-text">
                    <div className={`check-title${checked ? ' done' : ''}`}>{item.label}</div>
                    <div className="check-desc">{item.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Note */}
        <div style={{ padding: '0 16px 16px' }}>
          <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
              یادداشت اختیاری
            </div>
            <textarea
              className="note-textarea"
              placeholder='مثلاً: "گچ امشب کمی ناراحت بود"'
              value={todayLog.note}
              onChange={e => updateTodayLog({ note: e.target.value })}
              rows={2}
            />
          </div>
        </div>
      </div>

      {/* ── Weekly Check-in (when due) ───────────────────── */}
      {showWeekly && <WeeklyCheckInCard weekKey={weekKey} onComplete={upsertWeeklyCheckIn} />}

      {/* ── Completed weekly this week ───────────────────── */}
      {thisWeekCheckIn && (
        <div className="card" style={{ borderColor: 'var(--green-border)', background: 'var(--green-bg)' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--green)', display: 'flex', gap: 6 }}>
            ✓ بررسی هفتگی این هفته تکمیل شد
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
            {formatDateFA(thisWeekCheckIn.completedDate)}
          </div>
        </div>
      )}

      {/* ── Reminder note ───────────────────────────────── */}
      <div style={{
        marginTop: 16,
        padding: '12px',
        background: 'var(--bg-card-alt)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        color: 'var(--text-muted)',
        lineHeight: 1.5,
      }}>
        اگر هر یک از موارد بالا ناگهان تغییر کرد یا نگرانی داشتید، با تیم پزشکی تماس بگیرید.
      </div>
    </div>
  );
}

interface WeeklyCheckInProps {
  weekKey: string;
  onComplete: (data: WeeklyCheckIn) => void;
}

function WeeklyCheckInCard({ weekKey, onComplete }: WeeklyCheckInProps) {
  const today = todayStr();
  const [state, setState] = useState<Omit<WeeklyCheckIn, 'weekKey' | 'completedDate'>>({
    castComfortable: false,
    fingerMovementNormal: false,
    noNewSymptoms: false,
    noFallOrTrauma: false,
    appointmentConfirmed: false,
    unusualNote: '',
  });

  const weekly5: Array<{ key: keyof typeof state; label: string }> = [
    { key: 'castComfortable', label: 'گچ همچنان سالم و نسبتاً راحت است؟' },
    { key: 'fingerMovementNormal', label: 'حرکت انگشتان آزاد طبیعی است؟' },
    { key: 'noNewSymptoms', label: 'بی‌حسی، تورم یا تغییر رنگ جدیدی نیست؟' },
    { key: 'noFallOrTrauma', label: 'سقوط یا ضربه جدیدی نبوده؟' },
    { key: 'appointmentConfirmed', label: 'قرار ملاقات بعدی تأیید شده؟' },
  ];

  const handleSubmit = () => {
    onComplete({
      weekKey,
      completedDate: today,
      ...state,
    });
  };

  return (
    <div className="weekly-card" style={{ marginBottom: 12 }}>
      <div className="weekly-header">
        <div className="weekly-title">🗓 بررسی هفتگی</div>
        <div className="weekly-subtitle">پنج سؤال — مدت: ۳۰ ثانیه</div>
      </div>
      <div className="weekly-body">
        <div className="checklist">
          {weekly5.map(item => {
            const checked = Boolean(state[item.key as keyof typeof state]);
            return (
              <div
                key={item.key}
                className="check-item"
                onClick={() => setState(s => ({ ...s, [item.key]: !s[item.key as keyof typeof s] }))}
                role="checkbox"
                aria-checked={checked}
                tabIndex={0}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setState(s => ({ ...s, [item.key]: !s[item.key as keyof typeof s] }));
                  }
                }}
              >
                <div className={`check-box${checked ? ' checked' : ''}`}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
                <div className="check-text">
                  <div className={`check-title${checked ? ' done' : ''}`}>{item.label}</div>
                </div>
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
            چیز غیرعادی این هفته؟ (اختیاری)
          </div>
          <textarea
            className="note-textarea"
            placeholder="..."
            value={state.unusualNote}
            onChange={e => setState(s => ({ ...s, unusualNote: e.target.value }))}
            rows={2}
          />
        </div>
        <button
          className="btn btn-primary btn-full"
          style={{ marginTop: 12 }}
          onClick={handleSubmit}
        >
          ثبت بررسی هفتگی
        </button>
      </div>
    </div>
  );
}
