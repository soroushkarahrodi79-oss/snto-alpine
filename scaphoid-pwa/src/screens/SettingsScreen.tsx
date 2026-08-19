import { useState, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { addWeeks, formatDateFA } from '../utils/dateUtils';

interface Props {
  onClose: () => void;
}

export default function SettingsScreen({ onClose }: Props) {
  const { settings, updateSettings, exportData, importData, resetData } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState('');
  const [importOk, setImportOk] = useState(false);

  const week8 = addWeeks(settings.injuryDate, 8);
  const week12 = addWeeks(settings.injuryDate, 12);

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const text = ev.target?.result as string;
      const ok = importData(text);
      if (ok) {
        setImportOk(true);
        setImportError('');
        setTimeout(() => setImportOk(false), 3000);
      } else {
        setImportError('فایل نامعتبر است');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function handleReset() {
    if (window.confirm('تمام داده‌های ذخیره‌شده حذف می‌شوند. مطمئن هستید؟')) {
      resetData();
      onClose();
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'var(--bg)',
      overflowY: 'auto',
    }}>
      {/* Header */}
      <div className="header">
        <button
          className="icon-btn"
          aria-label="بستن"
          onClick={onClose}
          style={{ marginRight: -4 }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <span className="header-title">تنظیمات</span>
        <div style={{ width: 36 }} />
      </div>

      <div className="screen" style={{ paddingTop: 16 }}>

        {/* ── Recovery Profile ─────────────────────────── */}
        <div className="settings-group">
          <div className="settings-group-title">پروفایل بهبودی</div>

          <div className="settings-row">
            <div>
              <div className="settings-label">تاریخ آسیب</div>
              <div className="settings-sublabel">تمام محاسبات از این تاریخ</div>
            </div>
            <input
              type="date"
              className="settings-input"
              value={settings.injuryDate}
              onChange={e => updateSettings({ injuryDate: e.target.value })}
            />
          </div>

          <div className="settings-row">
            <div className="settings-label">طرف آسیب</div>
            <select
              className="settings-input"
              value={settings.side}
              onChange={e => updateSettings({ side: e.target.value as 'right' | 'left' })}
              style={{ minWidth: 'auto', width: 100 }}
            >
              <option value="right">راست</option>
              <option value="left">چپ</option>
            </select>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">هفته ۸ (محاسبه‌شده)</div>
              <div className="settings-sublabel">ارزیابی کلیدی</div>
            </div>
            <span className="settings-value">{formatDateFA(week8)}</span>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">هفته ۱۲ (افق)</div>
              <div className="settings-sublabel">حداکثر برنامه‌ریزی</div>
            </div>
            <span className="settings-value">{formatDateFA(week12)}</span>
          </div>
        </div>

        {/* ── Clinical Appointments ────────────────────── */}
        <div className="settings-group">
          <div className="settings-group-title">قرارها و تصویربرداری</div>

          <div className="settings-row" style={{ flexWrap: 'wrap', gap: 8 }}>
            <div className="settings-label">ویزیت بعدی</div>
            <input
              type="date"
              className="settings-input"
              value={settings.nextAppointment ?? ''}
              onChange={e => updateSettings({ nextAppointment: e.target.value || null })}
            />
          </div>

          <div className="settings-row" style={{ flexWrap: 'wrap', gap: 8 }}>
            <div className="settings-label">تصویربرداری بعدی</div>
            <input
              type="date"
              className="settings-input"
              value={settings.nextImaging ?? ''}
              onChange={e => updateSettings({ nextImaging: e.target.value || null })}
            />
          </div>

          <div className="settings-row" style={{ flexWrap: 'wrap', gap: 8 }}>
            <div className="settings-label">پزشک / کلینیک</div>
            <input
              className="settings-input"
              placeholder="اختیاری"
              value={settings.doctorClinic}
              onChange={e => updateSettings({ doctorClinic: e.target.value })}
              style={{ direction: 'rtl' }}
            />
          </div>
        </div>

        {/* ── Display ──────────────────────────────────── */}
        <div className="settings-group">
          <div className="settings-group-title">نمایش</div>

          <div className="settings-row">
            <div className="settings-label">حالت تاریک</div>
            <Toggle
              checked={settings.darkMode}
              onChange={v => updateSettings({ darkMode: v })}
            />
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">مخفی کردن چک‌باکس نیکوتین</div>
              <div className="settings-sublabel">اگر سیگاری نیستید</div>
            </div>
            <Toggle
              checked={settings.hideNicotineCheck}
              onChange={v => updateSettings({ hideNicotineCheck: v })}
            />
          </div>
        </div>

        {/* ── Data ─────────────────────────────────────── */}
        <div className="settings-group">
          <div className="settings-group-title">داده‌ها</div>

          <div className="settings-row">
            <div>
              <div className="settings-label">صادرات بک‌آپ</div>
              <div className="settings-sublabel">ذخیره فایل JSON</div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={exportData}>
              صادرات
            </button>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">وارد کردن بک‌آپ</div>
              <div className="settings-sublabel">بازیابی از فایل JSON</div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => fileRef.current?.click()}>
              انتخاب فایل
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              style={{ display: 'none' }}
              onChange={handleImport}
            />
          </div>

          {importOk && (
            <div style={{ padding: '8px 16px', fontSize: 13, color: 'var(--green)', fontWeight: 600 }}>
              ✓ داده‌ها با موفقیت وارد شدند
            </div>
          )}
          {importError && (
            <div style={{ padding: '8px 16px', fontSize: 13, color: 'var(--red)' }}>
              ✕ {importError}
            </div>
          )}
        </div>

        {/* ── Danger Zone ──────────────────────────────── */}
        <div className="settings-group" style={{ borderColor: 'var(--red-border)' }}>
          <div className="settings-group-title" style={{ color: 'var(--red)' }}>ناحیه خطر</div>
          <div className="settings-row">
            <div>
              <div className="settings-label">بازنشانی همه داده‌ها</div>
              <div className="settings-sublabel">قابل بازگشت نیست</div>
            </div>
            <button className="btn btn-danger btn-sm" onClick={handleReset}>
              بازنشانی
            </button>
          </div>
        </div>

        {/* ── About ────────────────────────────────────── */}
        <div style={{ textAlign: 'center', padding: '20px 0', fontSize: 12, color: 'var(--text-muted)' }}>
          <div>Scaphoid Recovery v0.1</div>
          <div style={{ marginTop: 4 }}>
            این اپ جانشین پزشک نیست.
          </div>
          <div style={{ marginTop: 2 }}>
            همه داده‌ها فقط روی این دستگاه ذخیره می‌شوند.
          </div>
        </div>
      </div>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle" aria-label="toggle">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
      />
      <span className="toggle-track" />
      <span className="toggle-thumb" />
    </label>
  );
}
