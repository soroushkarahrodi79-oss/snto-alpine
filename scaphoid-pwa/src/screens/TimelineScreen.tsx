import { useApp } from '../context/AppContext';
import { addWeeks, formatDateFA, todayStr } from '../utils/dateUtils';
import { CT_DATE, CT_REVIEW_DATE } from '../data/clinicalProfile';

interface TimelineEvent {
  date: string;
  title: string;
  desc: string;
  status: 'past' | 'current' | 'future';
  editable?: boolean;
}

export default function TimelineScreen() {
  const { settings } = useApp();
  const { injuryDate, nextAppointment, nextImaging } = settings;
  const today = todayStr();

  const week2Date = addWeeks(injuryDate, 2);
  const week6Start = addWeeks(injuryDate, 6);
  const week8Date = addWeeks(injuryDate, 8);
  const week12Date = addWeeks(injuryDate, 12);

  function status(date: string): 'past' | 'current' | 'future' {
    if (date < today) return 'past';
    if (date === today) return 'current';
    return 'future';
  }

  const events: TimelineEvent[] = [
    {
      date: injuryDate,
      title: 'آسیب',
      desc: 'شکستگی اسکافویید مشکوک / تشخیص اولیه — اقدام اولیه و آتل‌بندی',
      status: status(injuryDate),
    },
    {
      date: week2Date,
      title: 'بررسی هفته ۲',
      desc: 'گچ Thumb-Spica بلند — آرنج ۹۰° ایموبیلیزه شد',
      status: status(week2Date),
    },
    {
      date: CT_DATE,
      title: 'CT اسکن',
      desc: 'شکستگی کمر اسکافویید تأیید شد — گزارش رادیولوژی صادر گردید',
      status: status(CT_DATE),
    },
    {
      date: CT_REVIEW_DATE,
      title: 'بررسی CT توسط پزشک معالج',
      desc: 'کورتکس قدامی سالم — جابه‌جایی قابل‌توجه نیست — درمان محافظه‌کارانه ادامه یافت',
      status: status(CT_REVIEW_DATE),
    },
  ];

  if (nextAppointment) {
    events.push({
      date: nextAppointment,
      title: 'ویزیت بعدی',
      desc: settings.doctorClinic || 'ویزیت متخصص',
      status: status(nextAppointment),
      editable: true,
    });
  }

  if (nextImaging) {
    events.push({
      date: nextImaging,
      title: 'تصویربرداری بعدی',
      desc: 'ارزیابی رادیولوژی / CT',
      status: status(nextImaging),
      editable: true,
    });
  }

  // Add horizon events
  events.push({
    date: week6Start,
    title: 'پنجره بررسی هفته ۶',
    desc: 'شروع بازه ارزیابی بالینی / رادیولوژی — بسته به صلاحدید پزشک',
    status: status(week6Start),
  });

  events.push({
    date: week8Date,
    title: 'نقطه کلیدی هفته ۸',
    desc: 'ارزیابی عمده — تصمیم ادامه یا تغییر درمان بر اساس شواهد بالینی و تصویربرداری',
    status: status(week8Date),
  });

  events.push({
    date: week12Date,
    title: 'افق برنامه‌ریزی هفته ۱۲',
    desc: 'حداکثر افق زمانی ایموبیلیزاسیون — برداشت گچ به شواهد التیام بستگی دارد، نه به این تاریخ به‌تنهایی',
    status: status(week12Date),
  });

  // Sort by date
  events.sort((a, b) => a.date.localeCompare(b.date));

  return (
    <div className="screen">
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
          تایم‌لاین بالینی
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          ترتیب زمانی رویدادها
        </div>
      </div>

      <div style={{
        marginBottom: 16,
        padding: '12px 14px',
        background: 'var(--blue-bg)',
        border: '1px solid var(--blue-border)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        color: 'var(--text-secondary)',
        lineHeight: 1.5,
      }}>
        تاریخ‌های آینده <strong>افق زمانی</strong> هستند، نه تضمین برداشت گچ. زمان‌بندی واقعی بر اساس شواهد التیام بالینی و تصویربرداری توسط پزشک تعیین می‌شود.
      </div>

      <div className="timeline-list">
        {events.map((event, i) => (
          <div
            key={i}
            className={`timeline-event${event.status === 'current' ? ' current' : ''}`}
          >
            <div className={`timeline-dot dot-${event.status}`} />
            <div className="timeline-event-card">
              <div className="timeline-event-date">{formatDateFA(event.date)}</div>
              <div className="timeline-event-title">
                {event.title}
                {event.editable && (
                  <span style={{
                    fontSize: 10, fontWeight: 500, marginRight: 6,
                    color: 'var(--blue)',
                    background: 'var(--blue-bg)',
                    padding: '1px 6px', borderRadius: 8,
                  }}>
                    قابل ویرایش
                  </span>
                )}
              </div>
              <div className="timeline-event-desc">{event.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{
        marginTop: 16,
        padding: '12px 14px',
        background: 'var(--bg-card-alt)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        color: 'var(--text-muted)',
        lineHeight: 1.5,
      }}>
        برای ویرایش تاریخ ویزیت یا تصویربرداری، به بخش تنظیمات (آیکن چرخ‌دنده) مراجعه کنید.
      </div>
    </div>
  );
}
