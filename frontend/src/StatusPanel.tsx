import { AlertTriangle, CheckCircle2, Clock3, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import type { SystemIssue } from "./systemStatus";
import type { OperationalIncident } from "./types";

interface StatusPanelProps {
  activeIssues: SystemIssue[];
  issues: SystemIssue[];
  lastSuccessAt: number | null;
  checking: boolean;
  serviceIncidents: OperationalIncident[];
  clearHistory: () => void;
}

export function StatusPanel({
  activeIssues,
  issues,
  lastSuccessAt,
  checking,
  serviceIncidents,
  clearHistory,
}: StatusPanelProps) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"current" | "history">("current");
  const [panelPosition, setPanelPosition] = useState({ left: 12, top: 80 });
  const rootRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const activeServiceIncidents = serviceIncidents.filter((incident) => !incident.resolved_at);
  const latestBrowser = activeIssues[0] ?? null;
  const latestService = activeServiceIncidents[0] ?? null;
  const latest = latestService && (!latestBrowser || Date.parse(latestService.last_seen_at) > latestBrowser.lastSeenAt)
    ? { title: latestService.title, detail: latestService.detail, lastSeenAt: Date.parse(latestService.last_seen_at), occurrences: latestService.occurrences }
    : latestBrowser;
  const activeCount = activeIssues.length + activeServiceIncidents.length;
  const historyCount = issues.length + serviceIncidents.length;
  const state = latest ? "issue" : checking ? "checking" : "healthy";
  const label = state === "issue" ? "Issue" : state === "checking" ? "Checking" : "All good";

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const opener = triggerRef.current;
    const positionPanel = () => {
      const trigger = triggerRef.current?.getBoundingClientRect();
      if (!trigger) return;
      const width = Math.min(380, Math.max(240, window.innerWidth - 24));
      setPanelPosition({
        left: Math.max(12, Math.min(window.innerWidth - width - 12, trigger.right - width)),
        top: trigger.bottom + 12,
      });
    };
    positionPanel();
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => closeRef.current?.focus());
    const dismiss = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popoverRef.current?.contains(target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        popoverRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      if (!focusable.length) return;
      const first = focusable[0]!;
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    window.addEventListener("resize", positionPanel);
    window.addEventListener("scroll", positionPanel, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("resize", positionPanel);
      window.removeEventListener("scroll", positionPanel, true);
      window.requestAnimationFrame(() => {
        if (opener?.isConnected) opener.focus();
        else if (previousFocus?.isConnected) previousFocus.focus();
      });
    };
  }, [open]);

  return (
    <div className="system-status" ref={rootRef}>
      <button
        ref={triggerRef}
        className={`status-trigger ${state}`}
        aria-label={`System status: ${label.toLowerCase()}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="status-dot" />
        {label}
        {activeCount > 1 && <span className="status-count">{activeCount}</span>}
      </button>

      {open && createPortal(
        <section ref={popoverRef} className="status-popover" role="dialog" aria-modal="true" aria-label="System status details" style={{ "--status-left": `${panelPosition.left}px`, "--status-top": `${panelPosition.top}px` } as CSSProperties}>
          <div className="status-popover-head">
            <div><strong>System status</strong><small>Service incidents persist · browser actions stay this session</small></div>
            <button ref={closeRef} className="status-close" aria-label="Close system status" onClick={() => setOpen(false)}><X size={16} /></button>
          </div>
          <div className="status-tabs" role="tablist" aria-label="Status views">
            <button role="tab" aria-selected={view === "current"} className={view === "current" ? "active" : ""} onClick={() => setView("current")}>Current</button>
            <button role="tab" aria-selected={view === "history"} className={view === "history" ? "active" : ""} onClick={() => setView("history")}>History{historyCount ? ` · ${historyCount}` : ""}</button>
          </div>

          {view === "current" ? (
            latest ? (
              <div className="current-status issue" role="status">
                <AlertTriangle size={20} />
                <div>
                  <strong>{latest.title}</strong>
                  <p>{latest.detail}</p>
                  <small>{timeLabel(latest.lastSeenAt)}{latest.occurrences > 1 ? ` · ${latest.occurrences} attempts` : ""}</small>
                  {activeCount > 1 && <small>{activeCount - 1} other current issue{activeCount > 2 ? "s" : ""} recorded</small>}
                </div>
              </div>
            ) : checking ? (
              <div className="current-status checking" role="status">
                <Clock3 size={20} />
                <div><strong>Checking the app</strong><p>Waiting for the first healthy response.</p></div>
              </div>
            ) : (
              <div className="current-status healthy" role="status">
                <CheckCircle2 size={20} />
                <div><strong>Everything looks good</strong><p>The app server and paper ledger are responding normally.</p>{lastSuccessAt && <small>Last checked {timeLabel(lastSuccessAt)}</small>}</div>
              </div>
            )
          ) : (
            <div className="status-history">
              {serviceIncidents.map((incident) => <ServiceIncidentRow incident={incident} key={incident.incident_id} />)}
              {issues.map((issue) => <IssueRow issue={issue} key={issue.id} />)}
              {!historyCount && <div className="status-history-empty"><CheckCircle2 size={19} /><span>No incidents recorded.</span></div>}
              {issues.some((issue) => issue.resolvedAt !== null) && <button className="clear-history" onClick={clearHistory}>Clear resolved history</button>}
            </div>
          )}
        </section>,
        document.body,
      )}
    </div>
  );
}

function ServiceIncidentRow({ incident }: { incident: OperationalIncident }) {
  const active = incident.resolved_at === null;
  return (
    <article className="status-history-row">
      <div><strong>{incident.title}</strong><span className={active ? "active" : "resolved"}>{active ? "Current" : "Resolved"}</span></div>
      <p>{incident.detail}</p>
      <small>{new Date(incident.last_seen_at).toLocaleString()}{incident.occurrences > 1 ? ` · ${incident.occurrences} occurrences` : ""} · saved by app</small>
    </article>
  );
}

function IssueRow({ issue }: { issue: SystemIssue }) {
  const active = issue.resolvedAt === null;
  return (
    <article className="status-history-row">
      <div><strong>{issue.title}</strong><span className={active ? "active" : "resolved"}>{active ? "Current" : "Resolved"}</span></div>
      <p>{issue.detail}</p>
      <small>{timeLabel(issue.lastSeenAt)}{issue.occurrences > 1 ? ` · ${issue.occurrences} attempts` : ""}</small>
    </article>
  );
}

function timeLabel(value: number) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
