"use client";

import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

interface DrawerProps {
  open: boolean;
  title: string;
  subtitle?: string;
  icon: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ open, title, subtitle, icon, onClose, children }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className={`drawer-root${open ? " is-open" : ""}`} aria-hidden={!open} inert={!open}>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-head">
          <span className="drawer-icon">{icon}</span>
          <div className="drawer-heading">
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">
            <X size={16} strokeWidth={1.75} />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  text,
}: {
  icon: ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">{icon}</span>
      <p className="empty-title">{title}</p>
      <p className="empty-text">{text}</p>
    </div>
  );
}
