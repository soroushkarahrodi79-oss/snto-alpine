import { useState } from 'react';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  icon?: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  variant?: 'default' | 'red' | 'amber';
}

export default function Collapsible({
  title, icon, subtitle, children, defaultOpen = false, variant = 'default',
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  if (variant === 'red') {
    return (
      <div className="red-flag-card">
        <div className="red-flag-header" onClick={() => setOpen(o => !o)} role="button" aria-expanded={open}>
          <span className="red-flag-title">
            {icon && <span>{icon}</span>}
            {title}
          </span>
          <ChevronIcon open={open} />
        </div>
        {open && <div className="red-flag-body">{children}</div>}
      </div>
    );
  }

  return (
    <div className="section-card">
      <div className="section-header" onClick={() => setOpen(o => !o)} role="button" aria-expanded={open}>
        <div className="section-header-left">
          {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
          <div>
            <div className="section-header-title">{title}</div>
            {subtitle && <div className="section-header-subtitle">{subtitle}</div>}
          </div>
        </div>
        <ChevronIcon open={open} />
      </div>
      {open && <div className="section-body">{children}</div>}
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`chevron${open ? ' open' : ''}`}
      width="18" height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
