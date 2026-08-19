import { useState } from 'react';
import { useApp } from '../context/AppContext';
import {
  daysSinceInjury, weeksSinceInjury, elapsedFraction,
  addWeeks, formatDateFA, nextGateLabel, milestoneProgress,
} from '../utils/dateUtils';
import {
  CT_DATE, CT_REVIEW_DATE,
  CT_FINDINGS_FA, PHYSICIAN_REVIEW_FA,
  CAST_DO_FA, CAST_DONT_FA,
  MOVEMENT_SAFE_FA, MOVEMENT_APPROVAL_FA, MOVEMENT_AVOID_FA,
  PROTEIN_FOODS_FA, CALCIUM_FOODS_FA,
} from '../data/clinicalProfile';
import Collapsible from '../components/Collapsible';

export default function HomeScreen() {
  const { settings, todayLog } = useApp();
  const { injuryDate } = settings;

  const days = daysSinceInjury(injuryDate);
  const week = weeksSinceInjury(injuryDate);
  const pct = Math.round(elapsedFraction(injuryDate) * 100);
  const gate = nextGateLabel(settings);
  const mp = milestoneProgress(injuryDate);

  const week8Date = addWeeks(injuryDate, 8);
  const week12Date = addWeeks(injuryDate, 12);

  const completedToday = [
    todayLog.castOk,
    todayLog.fingersMoving,
    todayLog.noWarningSymptoms,
    todayLog.proteinNutrition,
    todayLog.calciumNutrition,
    todayLog.safeActivity,
  ].filter(Boolean).length;

  return (
    <div className="screen">
      {/* ── Header Card ─────────────────────────────────── */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 4 }}>
          درمان محافظه‌کارانه • اسکافویید راست
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          گچ Thumb-Spica بلند — آرنج ۹۰°
        </div>
      </div>

      {/* ── Three Stat Cards ────────────────────────────── */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value">{days}</div>
          <div className="stat-label">روز</div>
          <div className="stat-sublabel">از آسیب</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{week}</div>
          <div className="stat-label">هفته</div>
          <div className="stat-sublabel">بهبودی</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: 20 }}>
            {gate.daysLeft !== null && gate.daysLeft >= 0 ? gate.daysLeft : '—'}
          </div>
          <div className="stat-label" style={{ fontSize: 10 }}>
            {gate.label}
          </div>
          <div className="stat-sublabel">روز مانده</div>
        </div>
      </div>

      {/* ── Immobilisation Timeline Progress ────────────── */}
      <div className="timeline-progress">
        <div className="timeline-progress-header">
          <span className="timeline-progress-title">تایم‌لاین ایموبیلیزاسیون</span>
          <span className="timeline-progress-pct">{pct}٪</span>
        </div>
        <div className="timeline-progress-warning">
          این نشانگر <strong>زمان سپری‌شده</strong> است، نه میزان التیام استخوان.
          برداشت گچ به شواهد بالینی و تصویربرداری بستگی دارد، نه به شمارش معکوس.
        </div>

        <ProgressBar pct={pct} milestones={mp} />

        <div className="progress-labels">
          <span>آسیب</span>
          <span>هفته ۱۲ ({formatDateFA(week12Date)})</span>
        </div>
      </div>

      {/* ── Today's Quick Status ─────────────────────────── */}
      <div className="card mb-12">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
              چک روزانه
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {completedToday} از ۶ مورد تکمیل شده
            </div>
          </div>
          <div style={{
            width: 40, height: 40, borderRadius: '50%',
            background: completedToday === 6 ? 'var(--green-bg)' : 'var(--bg-card-alt)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20,
          }}>
            {completedToday === 6 ? '✅' : '⭕'}
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <MiniProgressBar value={completedToday} max={6} />
        </div>
      </div>

      {/* ── Red Flags ───────────────────────────────────── */}
      <RedFlagsSection />

      {/* ── Clinical Status ─────────────────────────────── */}
      <ClinicalStatusCard week8Date={week8Date} />

      {/* ── Cast Care ───────────────────────────────────── */}
      <Collapsible icon="🩹" title="مراقبت از گچ" subtitle="بایدها و نبایدها">
        <div className="do-dont-grid">
          <div className="do-list">
            <div className="do-header">✓ باید</div>
            {CAST_DO_FA.map((item, i) => (
              <div key={i} className="do-item">{item}</div>
            ))}
          </div>
          <div className="dont-list">
            <div className="dont-header">✕ نباید</div>
            {CAST_DONT_FA.map((item, i) => (
              <div key={i} className="dont-item">{item}</div>
            ))}
          </div>
        </div>
        <div style={{
          marginTop: 12, padding: '10px 12px',
          background: 'var(--amber-bg)', borderRadius: 'var(--radius-sm)',
          fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5,
          border: '1px solid var(--amber-border)',
        }}>
          چون این گچ <strong>بلند</strong> است و آرنج عمداً ایموبیلیزه شده، تمرینات حرکتی آرنج را بدون تأیید پزشک انجام ندهید.
        </div>
      </Collapsible>

      {/* ── Movement ────────────────────────────────────── */}
      <Collapsible icon="🏃" title="حرکت ایمن" subtitle="چه کاری ایمن است؟">
        <div className="movement-section">
          <div className="movement-section-title" style={{ color: 'var(--green)' }}>
            مناسب
          </div>
          <div className="movement-items">
            {MOVEMENT_SAFE_FA.map((item, i) => (
              <span key={i} className="movement-tag tag-green">{item}</span>
            ))}
          </div>
        </div>
        <div className="movement-section">
          <div className="movement-section-title" style={{ color: 'var(--amber)' }}>
            نیاز به تأیید پزشک
          </div>
          <div className="movement-items">
            {MOVEMENT_APPROVAL_FA.map((item, i) => (
              <span key={i} className="movement-tag tag-amber">{item}</span>
            ))}
          </div>
        </div>
        <div className="movement-section">
          <div className="movement-section-title" style={{ color: 'var(--red)' }}>
            در حال حاضر اجتناب کنید
          </div>
          <div className="movement-items">
            {MOVEMENT_AVOID_FA.map((item, i) => (
              <span key={i} className="movement-tag tag-red">{item}</span>
            ))}
          </div>
        </div>
        <div style={{
          marginTop: 12, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4,
        }}>
          این راهنما جانشین فیزیوتراپی نیست. هر سؤال مربوط به حرکت را با پزشک مطرح کنید.
        </div>
      </Collapsible>

      {/* ── Nutrition ───────────────────────────────────── */}
      <Collapsible icon="🥗" title="تغذیه برای ترمیم استخوان" subtitle="سه هدف اصلی">
        <div className="nutrition-goals">
          <div className="nutrition-goal">
            <div className="nutrition-goal-title">🥩 پروتئین</div>
            <div className="nutrition-goal-desc">
              پروتئین کافی در وعده‌های اصلی — برای حمایت از ترمیم بافت
            </div>
            <div className="nutrition-examples">
              {PROTEIN_FOODS_FA.map((f, i) => <span key={i} className="nutrition-tag">{f}</span>)}
            </div>
          </div>

          <div className="nutrition-goal">
            <div className="nutrition-goal-title">🥛 کلسیم</div>
            <div className="nutrition-goal-desc">
              هدف: حدود ۱۰۰۰ میلی‌گرم در روز از مجموع رژیم غذایی (برای بزرگسال جوان). ابتدا از غذا تأمین کنید.
            </div>
            <div className="nutrition-examples">
              {CALCIUM_FOODS_FA.map((f, i) => <span key={i} className="nutrition-tag">{f}</span>)}
            </div>
          </div>

          <div className="nutrition-goal">
            <div className="nutrition-goal-title">☀️ ویتامین D</div>
            <div className="nutrition-goal-desc">
              مرجع: حدود ۶۰۰ IU / ۱۵ میکروگرم در روز برای بزرگسال جوان. مکمل فقط در صورت کمبود نشان‌داده‌شده.
            </div>
          </div>
        </div>
      </Collapsible>

      {/* ── Supplements ─────────────────────────────────── */}
      <Collapsible icon="💊" title="مکمل‌ها" subtitle="هیچ استک اجباری وجود ندارد">
        <div style={{
          fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12,
          padding: '8px 10px', background: 'var(--bg-card-alt)',
          borderRadius: 'var(--radius-sm)', lineHeight: 1.5,
        }}>
          مکمل‌ها باید کمبود واقعی یا محتمل را جبران کنند، نه جای غذا را بگیرند.
        </div>
        <div className="supplement-table">
          {SUPPLEMENTS.map(s => (
            <div key={s.name} className="supplement-row">
              <div className="supplement-name">{s.name}</div>
              <div className="supplement-note">{s.note}</div>
            </div>
          ))}
        </div>
      </Collapsible>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function ProgressBar({ pct, milestones }: {
  pct: number;
  milestones: ReturnType<typeof milestoneProgress>;
}) {
  // RTL: progress fills from right, position markers from right
  const curPos = Math.min(100, Math.max(0, pct));

  return (
    <div className="progress-track" style={{ marginBottom: 32 }}>
      {/* Fill — from right edge */}
      <div
        className="progress-fill"
        style={{ width: `${curPos}%` }}
      />

      {/* Milestone markers */}
      {([
        { pct: milestones.week2 * 100, label: 'CT\nهفته ۲', color: 'var(--blue)' },
        { pct: milestones.week6 * 100, label: 'هفته ۶\nبررسی', color: 'var(--amber)' },
        { pct: milestones.week8 * 100, label: 'هفته ۸\nارزیابی', color: 'var(--amber)' },
      ] as const).map((m, i) => (
        <div key={i}>
          <div
            className="progress-marker"
            style={{
              right: `${m.pct}%`,
              background: m.color,
            }}
          />
          <div
            className="progress-marker-label"
            style={{ right: `${m.pct}%` }}
          >
            {m.label.split('\n').map((l, j) => (
              <div key={j}>{l}</div>
            ))}
          </div>
        </div>
      ))}

      {/* Current position indicator */}
      {curPos > 0 && curPos < 100 && (
        <div
          style={{
            position: 'absolute',
            right: `${curPos}%`,
            top: -4,
            transform: 'translateX(50%)',
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: 'var(--blue)',
            border: '3px solid var(--bg-card)',
            boxShadow: 'var(--shadow-md)',
          }}
        />
      )}
    </div>
  );
}

function MiniProgressBar({ value, max }: { value: number; max: number }) {
  const pct = (value / max) * 100;
  return (
    <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
      <div
        style={{
          height: '100%',
          width: `${pct}%`,
          background: value === max ? 'var(--green)' : 'var(--blue)',
          borderRadius: 3,
          transition: 'width 0.3s ease',
        }}
      />
    </div>
  );
}

function RedFlagsSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="red-flag-card">
      <div
        className="red-flag-header"
        onClick={() => setOpen(o => !o)}
        role="button"
        aria-expanded={open}
      >
        <span className="red-flag-title">
          🚨 با تیم پزشکی تماس بگیرید
        </span>
        <ChevronDown open={open} />
      </div>
      {open && (
        <div className="red-flag-body">
          <ul className="red-flag-list">
            {[
              'درد به‌طور قابل‌توجهی افزایش یابد',
              'تورم جدید یا رو به افزایش',
              'بی‌حسی جدید',
              'گزگز جدید',
              'انگشتان آبی، کم‌رنگ یا غیرمعمول سرد شوند',
              'ناتوانی در حرکت انگشتان آزاد',
              'گچ خیلی تنگ یا خیلی شل شود',
              'شکستگی گچ',
              'خیس شدن گچ',
              'بوی بد یا ترشح',
              'سقوط یا ضربه جدید به اندام آسیب‌دیده',
            ].map((f, i) => <li key={i}>{f}</li>)}
          </ul>
          <div className="red-flag-urgent">
            در صورت علائم شدید یا بدتر شدن سریع، فوری به پزشک مراجعه کنید.
          </div>
        </div>
      )}
    </div>
  );
}

function ClinicalStatusCard({ week8Date }: { week8Date: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="clinical-card"
      style={{ cursor: 'pointer', marginBottom: 12 }}
      onClick={() => setOpen(o => !o)}
      role="button"
      aria-expanded={open}
    >
      <div className="clinical-card-title">
        🩻 وضعیت بالینی فعلی
        <ChevronDown open={open} />
      </div>

      <div className="clinical-row">
        <span className="clinical-row-label">تشخیص:</span>
        <span className="clinical-row-value">شکستگی کمر اسکافویید (Scaphoid waist fracture)</span>
      </div>
      <div className="clinical-row">
        <span className="clinical-row-label">CT:</span>
        <span className="clinical-row-value">{formatDateFA(CT_DATE)}</span>
      </div>
      <div className="clinical-row">
        <span className="clinical-row-label">درمان:</span>
        <span className="clinical-row-value">گچ Thumb-Spica بلند — محافظه‌کارانه</span>
      </div>

      {open && (
        <>
          <div className="clinical-findings">
            <div className="clinical-finding-title">یافته‌های CT:</div>
            <ul className="clinical-finding-list">
              {CT_FINDINGS_FA.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          </div>
          <div className="clinical-findings">
            <div className="clinical-finding-title">بررسی پزشک معالج ({formatDateFA(CT_REVIEW_DATE)}):</div>
            <ul className="clinical-finding-list">
              {PHYSICIAN_REVIEW_FA.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          </div>
          <div className="clinical-note">
            پزشک معالج تصاویر CT را مستقیماً بررسی کرد و ادامه ایموبیلیزاسیون با گچ را انتخاب نمود. هیچ نیازی به جراحی در این مرحله مطرح نشده است.
          </div>
          <div className="clinical-note" style={{ marginTop: 6 }}>
            ارزیابی هفته ۸: {formatDateFA(week8Date)}
          </div>
        </>
      )}
    </div>
  );
}

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      className={`chevron${open ? ' open' : ''}`}
      style={{ marginRight: 'auto', marginLeft: 0, flexShrink: 0 }}
      width="16" height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

const SUPPLEMENTS = [
  { name: 'ویتامین D', note: 'فقط در صورت کمبود یا توصیه پزشک' },
  { name: 'کلسیم', note: 'اول از غذا؛ مکمل فقط در صورت لزوم' },
  { name: 'پروتئین وی', note: 'ابزار کمکی فقط اگر غذا کافی نیست' },
  { name: 'کلاژن', note: 'اختیاری — پیش‌فرض لازم نیست' },
  { name: 'منیزیم', note: 'برای این شکستگی اجباری نیست' },
  { name: 'روی (زینک)', note: 'پیش‌فرض لازم نیست' },
  { name: 'ویتامین K2', note: 'پیش‌فرض لازم نیست' },
];
