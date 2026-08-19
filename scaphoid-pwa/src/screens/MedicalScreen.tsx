import { useState } from 'react';
import { useApp } from '../context/AppContext';
import type { MedicalDoc, MedDocType } from '../types';
import { todayStr, formatDateFA } from '../utils/dateUtils';

const DOC_TYPES: { value: MedDocType; label: string; icon: string }[] = [
  { value: 'ct_report', label: 'گزارش CT', icon: '📋' },
  { value: 'ct_images', label: 'تصاویر DICOM / CT', icon: '🗂️' },
  { value: 'doctor_notes', label: 'یادداشت پزشک', icon: '📝' },
  { value: 'prescriptions', label: 'نسخه', icon: '💊' },
  { value: 'appointments', label: 'وقت ملاقات', icon: '📅' },
  { value: 'other', label: 'سایر', icon: '📁' },
];

function typeInfo(type: MedDocType) {
  return DOC_TYPES.find(t => t.value === type) ?? DOC_TYPES[DOC_TYPES.length - 1];
}

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

export default function MedicalScreen() {
  const { medicalDocs, addMedicalDoc, updateMedicalDoc, deleteMedicalDoc } = useApp();
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  const sorted = [...medicalDocs].sort((a, b) => b.date.localeCompare(a.date));

  return (
    <div className="screen">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>مدارک پزشکی</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>مراجع و یادداشت‌ها</div>
        </div>
        {!adding && !editId && (
          <button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>
            + افزودن
          </button>
        )}
      </div>

      {adding && (
        <DocForm
          onSave={doc => {
            addMedicalDoc({ ...doc, id: genId() });
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      )}

      {sorted.length === 0 && !adding && (
        <div className="empty-state">
          <div className="empty-state-icon">📁</div>
          <div className="empty-state-text">هنوز مدرکی اضافه نشده</div>
          <button className="btn btn-secondary" onClick={() => setAdding(true)}>
            افزودن مدرک اول
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="doc-list">
          {sorted.map(doc => {
            const info = typeInfo(doc.type);
            return editId === doc.id ? (
              <DocForm
                key={doc.id}
                initial={doc}
                onSave={updated => {
                  updateMedicalDoc(doc.id, updated);
                  setEditId(null);
                }}
                onCancel={() => setEditId(null)}
              />
            ) : (
              <div key={doc.id} className="doc-card">
                <div className="doc-icon">{info.icon}</div>
                <div className="doc-body">
                  <div className="doc-title">{doc.title || info.label}</div>
                  <div className="doc-meta">
                    {info.label} — {formatDateFA(doc.date)}
                  </div>
                  {doc.note && <div className="doc-note">{doc.note}</div>}
                  {doc.reference && (
                    <div className="doc-ref">📎 {doc.reference}</div>
                  )}
                </div>
                <div className="doc-actions">
                  <button
                    className="icon-btn"
                    aria-label="ویرایش"
                    onClick={() => setEditId(doc.id)}
                  >
                    <PencilIcon />
                  </button>
                  <button
                    className="icon-btn"
                    aria-label="حذف"
                    style={{ color: 'var(--red)' }}
                    onClick={() => {
                      if (confirm('این مدرک حذف شود؟')) deleteMedicalDoc(doc.id);
                    }}
                  >
                    <TrashIcon />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{
        marginTop: 20,
        padding: '12px 14px',
        background: 'var(--bg-card-alt)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        color: 'var(--text-muted)',
        lineHeight: 1.5,
      }}>
        همه داده‌ها فقط در این دستگاه ذخیره می‌شوند. برای بک‌آپ به تنظیمات مراجعه کنید.
      </div>
    </div>
  );
}

interface DocFormProps {
  initial?: Partial<MedicalDoc>;
  onSave: (doc: Omit<MedicalDoc, 'id'>) => void;
  onCancel: () => void;
}

function DocForm({ initial, onSave, onCancel }: DocFormProps) {
  const [type, setType] = useState<MedDocType>(initial?.type ?? 'ct_report');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [date, setDate] = useState(initial?.date ?? todayStr());
  const [note, setNote] = useState(initial?.note ?? '');
  const [reference, setReference] = useState(initial?.reference ?? '');

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
        {initial ? 'ویرایش مدرک' : 'افزودن مدرک'}
      </div>

      <div className="form-group">
        <label className="form-label">نوع مدرک</label>
        <select
          className="form-select"
          value={type}
          onChange={e => setType(e.target.value as MedDocType)}
        >
          {DOC_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.icon} {t.label}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">عنوان (اختیاری)</label>
        <input
          className="form-input"
          placeholder={typeInfo(type).label}
          value={title}
          onChange={e => setTitle(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label className="form-label">تاریخ</label>
        <input
          className="form-input"
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          style={{ direction: 'ltr', textAlign: 'right' }}
        />
      </div>

      <div className="form-group">
        <label className="form-label">یادداشت</label>
        <textarea
          className="note-textarea"
          placeholder="توضیحات مختصر..."
          value={note}
          onChange={e => setNote(e.target.value)}
          rows={2}
        />
      </div>

      <div className="form-group">
        <label className="form-label">مرجع / نام فایل</label>
        <input
          className="form-input"
          placeholder='مثلاً: CT_report_Aug2026.pdf'
          value={reference}
          onChange={e => setReference(e.target.value)}
          style={{ direction: 'ltr', textAlign: 'right' }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          className="btn btn-primary"
          style={{ flex: 1 }}
          onClick={() => onSave({ type, title, date, note, reference })}
        >
          ذخیره
        </button>
        <button className="btn btn-secondary" onClick={onCancel}>
          لغو
        </button>
      </div>
    </div>
  );
}

function PencilIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  );
}
