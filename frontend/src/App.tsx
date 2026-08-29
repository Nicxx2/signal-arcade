import {
  Activity,
  AlertTriangle,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  Copy,
  ExternalLink,
  Gauge,
  GraduationCap,
  History,
  HardDrive,
  KeyRound,
  Landmark,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Save,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Trophy,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { copyText } from "./clipboard";
import { latestDecisionsByMint, organizeDecisions } from "./decisionView";
import { buildEquityJourney, unchangedEquitySeconds } from "./equityJourney";
import { StatusPanel } from "./StatusPanel";
import { friendlyError, useSystemStatus } from "./systemStatus";
import type { IssueScope } from "./systemStatus";
import type {
  Decision,
  DecisionAction,
  EquityPoint,
  FeatureSnapshot,
  Fill,
  LearningMode,
  Leaderboard as LeaderboardData,
  MaintenanceOperation,
  PaperSeason,
  Position,
  ProviderConfiguration,
  ProviderPolicy,
  ProviderPreset,
  ProviderSettingsUpdate,
  QuoteCurrency,
  RiskMode,
  SeasonOperation,
  Seasons as SeasonsData,
  Snapshot,
  AiDecisionMode,
} from "./types";

type Tab = "arena" | "decisions" | "leaderboard" | "learning" | "replay" | "settings";
const RISK_MODES: RiskMode[] = ["safe", "balanced", "aggressive"];
const EXPECTED_RESTART_KEY = "signal-arcade-expected-restart-until";

type ExplanationState =
  | { status: "loading"; decision: Decision }
  | { status: "ready"; decision: Decision; text: string; source: string }
  | { status: "error"; decision: Decision; message: string };

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<Tab>("arena");
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expectedRestart, setExpectedRestart] = useState(() => {
    try {
      return Number(window.sessionStorage.getItem(EXPECTED_RESTART_KEY) ?? 0) > Date.now();
    } catch {
      return false;
    }
  });
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const { state: status, activeIssues, reportIssue, resolveIssue, clearHistory } = useSystemStatus();
  const [explanation, setExplanation] = useState<ExplanationState | null>(null);
  const explanationRequest = useRef(0);
  const explanationAbort = useRef<AbortController | null>(null);

  const refresh = useCallback((): Promise<void> => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const request = (async () => {
      try {
        const next = await api.snapshot();
        setSnapshot(next);
        try {
          const maintenance = next.maintenance_operation;
          if (maintenance?.state === "ready") {
            const saved = Number(window.sessionStorage.getItem(EXPECTED_RESTART_KEY) ?? 0);
            const expiresAt = saved > Date.now() ? saved : Date.now() + 30 * 60_000;
            window.sessionStorage.setItem(EXPECTED_RESTART_KEY, String(expiresAt));
            setExpectedRestart(true);
          } else if (maintenance && ["completed", "cancelled", "failed"].includes(maintenance.state)) {
            window.sessionStorage.removeItem(EXPECTED_RESTART_KEY);
            setExpectedRestart(false);
          }
        } catch {
          // Private browsing may deny session storage. Server state remains authoritative.
        }
        resolveIssue("server", true);
        if ((next.snapshot_age_seconds ?? 0) > 15) {
          reportIssue(
            "dashboard",
            "Dashboard view is catching up",
            new Error("The trading engine is still running. This screen is showing the last complete snapshot and will refresh automatically."),
          );
        } else {
          resolveIssue("dashboard");
        }
        if (next.database_ok) {
          resolveIssue("database");
        } else {
          reportIssue(
            "database",
            "Paper ledger unavailable",
            new Error("The database liveness check did not pass. Trading remains safely blocked."),
          );
        }
      } catch (cause) {
        if (expectedRestart) return;
        try {
          const health = await api.health();
          if (health.service_running && health.database_ok) {
            resolveIssue("server", true);
            reportIssue(
              "dashboard",
              "Dashboard refresh delayed",
              new Error("The trading engine and paper ledger are responding. The last complete screen remains visible while the dashboard retries."),
            );
          } else {
            reportIssue("server", "App service needs attention", new Error("The server responded, but one or more core background checks are not healthy."));
          }
        } catch {
          reportIssue("server", "App server unavailable", cause);
        }
      }
    })();
    refreshInFlight.current = request;
    void request.finally(() => {
      if (refreshInFlight.current === request) refreshInFlight.current = null;
    });
    return request;
  }, [expectedRestart, reportIssue, resolveIssue]);

  useEffect(() => {
    if (!expectedRestart) return;
    let expiresAt: number;
    try {
      expiresAt = Number(window.sessionStorage.getItem(EXPECTED_RESTART_KEY) ?? 0);
    } catch {
      expiresAt = Date.now() + 30 * 60_000;
    }
    const timer = window.setTimeout(() => {
      try {
        window.sessionStorage.removeItem(EXPECTED_RESTART_KEY);
      } catch {
        // The timeout still restores normal incident reporting when storage is unavailable.
      }
      setExpectedRestart(false);
    }, Math.max(0, expiresAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [expectedRestart]);

  useEffect(() => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socketUrl = `${protocol}://${location.host}/ws`;
    let socket: WebSocket | null = null;
    let socketOpen = false;
    let stopped = false;
    let pollTimer: number | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    const schedulePoll = () => {
      if (stopped) return;
      if (pollTimer !== null) window.clearTimeout(pollTimer);
      const delay = document.hidden ? 30_000 : socketOpen ? 15_000 : 5_000;
      pollTimer = window.setTimeout(() => {
        pollTimer = null;
        void refresh().finally(schedulePoll);
      }, delay);
    };
    const initial = window.setTimeout(() => void refresh().finally(schedulePoll), 0);
    let websocketRefresh: number | null = null;
    let lastWebsocketRefresh = 0;
    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      const delay = Math.min(30_000, 1_000 * 2 ** Math.min(reconnectAttempt, 5));
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };
    const connect = () => {
      if (stopped) return;
      const next = new WebSocket(socketUrl);
      socket = next;
      next.onopen = () => {
        if (socket !== next || stopped) return;
        if (reconnectTimer !== null) {
          window.clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        socketOpen = true;
        reconnectAttempt = 0;
        setConnected(true);
        schedulePoll();
      };
      next.onclose = () => {
        if (socket !== next || stopped) return;
        socket = null;
        socketOpen = false;
        setConnected(false);
        schedulePoll();
        scheduleReconnect();
      };
      next.onerror = () => {
        if (socket !== next || stopped) return;
        socketOpen = false;
        setConnected(false);
        schedulePoll();
        // Browsers normally follow an error with `close`, but that is not guaranteed to be
        // prompt on every proxy/network failure. Start the bounded recovery path immediately.
        scheduleReconnect();
        next.close();
      };
      next.onmessage = () => {
        if (socket !== next || stopped) return;
        const delay = Math.max(0, 3_000 - (Date.now() - lastWebsocketRefresh));
        if (websocketRefresh !== null) return;
        websocketRefresh = window.setTimeout(() => {
          websocketRefresh = null;
          lastWebsocketRefresh = Date.now();
          void refresh();
        }, delay);
      };
    };
    connect();
    const visibilityChanged = () => {
      if (!document.hidden) void refresh();
      schedulePoll();
    };
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      stopped = true;
      window.clearTimeout(initial);
      if (pollTimer !== null) window.clearTimeout(pollTimer);
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (websocketRefresh !== null) window.clearTimeout(websocketRefresh);
      document.removeEventListener("visibilitychange", visibilityChanged);
      socket?.close();
    };
  }, [refresh]);

  const setRisk = async (mode: RiskMode) => {
    setBusy(true);
    try {
      await api.setRisk(mode);
      resolveIssue("risk");
      await refresh();
    } catch (cause) {
      reportIssue("risk", "Risk mode was not changed", cause);
    } finally {
      setBusy(false);
    }
  };

  const setSeasonAutomation = async (enabled: boolean, graceHours?: number) => {
    setBusy(true);
    try {
      await api.setSeasonAutomation(enabled, graceHours);
      resolveIssue("risk");
      await refresh();
    } catch (cause) {
      reportIssue("risk", "Automatic season policy was not changed", cause);
    } finally {
      setBusy(false);
    }
  };

  const setupPortfolio = async (currency: QuoteCurrency, amount: string): Promise<string | null> => {
    setBusy(true);
    try {
      await api.setupPortfolio(currency, amount);
      resolveIssue("setup");
      await refresh();
      return null;
    } catch (cause) {
      reportIssue("setup", "Paper bankroll was not created", cause);
      return friendlyError(cause);
    } finally {
      setBusy(false);
    }
  };

  const setEngineRunning = async (running: boolean) => {
    setBusy(true);
    try {
      if (running) await api.startEngine();
      else await api.stopEngine();
      resolveIssue("engine");
      await refresh();
    } catch (cause) {
      reportIssue("engine", running ? "Paper engine did not start" : "Paper engine did not stop", cause);
    } finally {
      setBusy(false);
    }
  };

  const setLearningMode = async (mode: LearningMode) => {
    setBusy(true);
    try {
      await api.setLearning(mode);
      resolveIssue("learning");
      await refresh();
    } catch (cause) {
      reportIssue("learning", "Learning mode was not changed", cause);
    } finally {
      setBusy(false);
    }
  };

  const setAiMode = async (mode: AiDecisionMode) => {
    setBusy(true);
    try {
      await api.setAiMode(mode);
      resolveIssue("ai");
      await refresh();
    } catch (cause) {
      reportIssue("ai", "AI Decision Lab mode was not changed", cause);
    } finally {
      setBusy(false);
    }
  };

  const explain = async (decision: Decision) => {
    explanationAbort.current?.abort();
    const controller = new AbortController();
    explanationAbort.current = controller;
    const requestId = ++explanationRequest.current;
    setExplanation({ status: "loading", decision });
    try {
      const result = await api.explain(decision.decision_id, controller.signal);
      if (requestId !== explanationRequest.current) return;
      resolveIssue("explanation");
      setExplanation({
        status: "ready",
        decision: result.decision ?? decision,
        text: result.explanation,
        source: result.source,
      });
    } catch (cause) {
      if (controller.signal.aborted || requestId !== explanationRequest.current) return;
      reportIssue("explanation", "Explanation unavailable", cause);
      setExplanation({ status: "error", decision, message: friendlyError(cause) });
    } finally {
      if (explanationAbort.current === controller) explanationAbort.current = null;
    }
  };

  const closeExplanation = useCallback(() => {
    explanationAbort.current?.abort();
    explanationAbort.current = null;
    explanationRequest.current += 1;
    setExplanation(null);
  }, []);

  useEffect(() => {
    if (!explanation) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeExplanation();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [closeExplanation, explanation]);

  useEffect(() => () => explanationAbort.current?.abort(), []);

  const totalPnl = snapshot
    ? snapshot.portfolio.equity_lamports - snapshot.portfolio.starting_lamports
    : 0;
  const maintenanceLocked = snapshot?.maintenance_operation?.state === "running"
    || snapshot?.maintenance_operation?.state === "ready";
  const controlsBusy = busy || snapshot?.season_operation?.state === "running" || maintenanceLocked;
  const explanationLabel = explanation
    ? tokenDisplayLabel(explanation.decision.symbol, explanation.decision.mint)
    : null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setTab("arena")} aria-label="Open Arena">
          <span className="brand-mark"><BrainCircuit size={20} /></span>
          <span><strong>Signal Arcade</strong><small>Solana paper lab</small></span>
        </button>
        <nav aria-label="Primary navigation">
          <NavButton active={tab === "arena"} onClick={() => setTab("arena")} icon={<Gauge size={17} />} label="Arena" />
          <NavButton active={tab === "decisions"} onClick={() => setTab("decisions")} icon={<BrainCircuit size={17} />} label="Decisions" />
          <NavButton active={tab === "leaderboard"} onClick={() => setTab("leaderboard")} icon={<Trophy size={17} />} label="Results" />
          <NavButton active={tab === "learning"} onClick={() => setTab("learning")} icon={<GraduationCap size={17} />} label="Learning" />
          <NavButton active={tab === "replay"} onClick={() => setTab("replay")} icon={<History size={17} />} label="Replay" />
          <NavButton active={tab === "settings"} onClick={() => setTab("settings")} icon={<Settings size={17} />} label="Settings" />
        </nav>
        <div className="top-status">
          <span
            className="release-badge"
            aria-label={`Signal Arcade version ${snapshot?.version ?? "loading"}`}
            title={snapshot ? `Signal Arcade ${snapshot.version}` : "Loading release version"}
          >
            {snapshot ? `v${snapshot.version}` : "v…"}
          </span>
          <span className="paper-badge"><ShieldCheck size={14} /> Paper only</span>
          {snapshot?.portfolio.risk_halted && (
            <span
              className="risk-pause-badge"
              role="status"
              aria-label="Risk paused"
              title={`New entries are paused at ${(snapshot.portfolio.drawdown_fraction * 100).toFixed(1)}% drawdown. Existing positions still receive exit management.`}
            >
              <AlertTriangle size={14} /> Risk paused
            </span>
          )}
          <span className={`connection ${connected ? "online" : "offline"}`}>
            {connected ? <Wifi size={15} /> : <WifiOff size={15} />}
            {connected ? "Live updates" : expectedRestart ? "Updating" : "Polling"}
          </span>
          <StatusPanel
            activeIssues={activeIssues}
            issues={status.issues}
            lastSuccessAt={status.lastSuccessAt}
            checking={!snapshot && activeIssues.length === 0}
            serviceIncidents={snapshot?.operational_incidents ?? []}
            clearHistory={clearHistory}
          />
        </div>
      </header>

      <SeasonOperationBanner key={snapshot?.season_operation?.operation_id ?? "no-operation"} operation={snapshot?.season_operation ?? null} />
      <MaintenanceOperationBanner key={snapshot?.maintenance_operation?.operation_id ?? "no-maintenance"} operation={snapshot?.maintenance_operation ?? null} />

      <main>
        {!snapshot ? (
          <LoadingState />
        ) : tab === "arena" ? (
          <Arena snapshot={snapshot} totalPnl={totalPnl} setRisk={setRisk} setSeasonAutomation={setSeasonAutomation} setupPortfolio={setupPortfolio} setEngineRunning={setEngineRunning} busy={controlsBusy} explain={explain} explainingId={explanation?.status === "loading" ? explanation.decision.decision_id : null} />
        ) : tab === "decisions" ? (
          <Decisions decisions={snapshot.decisions} explain={explain} explainingId={explanation?.status === "loading" ? explanation.decision.decision_id : null} serverTime={snapshot.server_time} candidateWindowMinutes={snapshot.candidate_window_minutes} staleMarketSeconds={snapshot.stale_market_seconds} engineRunning={snapshot.running} />
        ) : tab === "leaderboard" ? (
          <LeaderboardView explain={explain} reportIssue={reportIssue} resolveIssue={resolveIssue} />
        ) : tab === "learning" ? (
          <LearningLab snapshot={snapshot} setLearningMode={setLearningMode} setAiMode={setAiMode} busy={controlsBusy} />
        ) : tab === "replay" ? (
          <Replay snapshot={snapshot} />
        ) : (
          <SettingsView snapshot={snapshot} refresh={refresh} busy={controlsBusy} setBusy={setBusy} reportIssue={reportIssue} resolveIssue={resolveIssue} />
        )}
      </main>

      {explanation && (
        <div className="drawer-backdrop" role="presentation" onClick={closeExplanation}>
          <aside className="explain-drawer" role="dialog" aria-modal="true" aria-label={`Why ${explanationLabel}`} aria-busy={explanation.status === "loading"} onClick={(event) => event.stopPropagation()}>
            <button className="icon-button drawer-close" onClick={closeExplanation} aria-label="Close explanation"><X size={20} /></button>
            <span className="eyebrow"><Sparkles size={14} /> Decision explanation</span>
            <h2>Why {explanationLabel}?</h2>
            {explanation.status === "loading" ? (
              <div className="explain-state" role="status"><span className="mini-loader" /><div><strong>Preparing the explanation…</strong><p>The deterministic result is ready quickly; a configured local AI may take a little longer.</p></div></div>
            ) : explanation.status === "error" ? (
              <div className="explain-state error" role="status"><AlertTriangle size={21} /><div><strong>Could not load this explanation</strong><p>{explanation.message}</p><button className="button ghost" onClick={() => void explain(explanation.decision)}>Try again</button></div></div>
            ) : (
              <>
                <p>{explanation.text}</p>
                <DecisionEvidence decision={explanation.decision} />
                <div className="explain-source"><Bot size={15} />{explanation.source === "local_ai" ? "Explained by your local AI" : "Deterministic explanation — local AI was not needed"}</div>
                <ResearchHandoff mint={explanation.decision.mint} symbol={explanation.decision.symbol} />
                <p className="fine-print"><em>Paper-trading education only. This saved explanation does not alter the score or constitute financial advice.</em></p>
              </>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function SeasonOperationBanner({ operation }: { operation: SeasonOperation | null }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (operation?.state !== "running") return;
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - Date.parse(operation.started_at)) / 1_000)));
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [operation]);
  if (!operation || (operation.state !== "running" && operation.state !== "failed")) return null;
  const title = operation.kind === "reset" ? "Preparing the new season" : operation.kind === "setup" ? "Creating the paper bankroll" : "Starting the paper engine";
  return <section className={`season-operation-banner ${operation.state}`} role={operation.state === "failed" ? "alert" : "status"} aria-live="polite">
    {operation.state === "running" ? <RotateCcw size={17} /> : <AlertTriangle size={17} />}
    <div><strong>{operation.state === "failed" ? "Season operation needs attention" : title}</strong><span>{operation.detail}</span><small>{humanize(operation.stage)} · {elapsedSeconds < 60 ? `${elapsedSeconds}s` : `${Math.floor(elapsedSeconds / 60)}m ${elapsedSeconds % 60}s`} elapsed</small></div>
    {operation.state === "running" && <span className="season-operation-progress" aria-hidden="true" />}
  </section>;
}

function MaintenanceOperationBanner({ operation }: { operation: MaintenanceOperation | null }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (operation?.state !== "running") return;
    const update = () => setElapsedSeconds(
      Math.max(0, Math.floor((Date.now() - Date.parse(operation.started_at)) / 1_000)),
    );
    update();
    const timer = window.setInterval(update, 1_000);
    return () => window.clearInterval(timer);
  }, [operation]);
  if (!operation || !["running", "ready", "failed"].includes(operation.state)) return null;
  const failed = operation.state === "failed";
  const ready = operation.state === "ready";
  return <section className={`season-operation-banner maintenance-operation-banner ${operation.state}`} role={failed ? "alert" : "status"} aria-live="polite">
    {ready ? <Check size={17} /> : failed ? <AlertTriangle size={17} /> : <RotateCcw size={17} />}
    <div><strong>{ready ? "Ready for the Docker update" : failed ? "Upgrade preparation needs attention" : "Preparing Signal Arcade for an update"}</strong><span>{operation.detail}</span><small>{humanize(operation.stage)}{operation.state === "running" ? ` · ${elapsedSeconds < 60 ? `${elapsedSeconds}s` : `${Math.floor(elapsedSeconds / 60)}m ${elapsedSeconds % 60}s`} elapsed` : ` · prepared from v${operation.prepared_version}`}</small></div>
    {operation.state === "running" && <span className="season-operation-progress" aria-hidden="true" />}
  </section>;
}

function Arena({ snapshot, totalPnl, setRisk, setSeasonAutomation, setupPortfolio, setEngineRunning, busy, explain, explainingId }: {
  snapshot: Snapshot;
  totalPnl: number;
  setRisk: (mode: RiskMode) => Promise<void>;
  setSeasonAutomation: (enabled: boolean, graceHours?: number) => Promise<void>;
  setupPortfolio: (currency: QuoteCurrency, amount: string) => Promise<string | null>;
  setEngineRunning: (running: boolean) => Promise<void>;
  busy: boolean;
  explain: (decision: Decision) => Promise<void>;
  explainingId: string | null;
}) {
  const portfolio = snapshot.portfolio;
  const [collapsedPositionGroups, setCollapsedPositionGroups] = useState<Set<string>>(
    () => new Set(["dormant"]),
  );
  if (!portfolio.initialized) {
    return <SetupArena snapshot={snapshot} busy={busy} setupPortfolio={setupPortfolio} />;
  }
  const hasHistory = portfolio.positions.length > 0 || snapshot.fills.length > 0 || snapshot.decisions.length > 0;
  const latestDecisionFeed = latestDecisionsByMint(snapshot.decisions).slice(0, 8);
  const capacityPositionCount = portfolio.positions.filter((item) => item.market_status !== "dormant").length;
  const autoSeasonHours = Math.max(1, Math.round(snapshot.season_automation.grace_seconds / 3600));
  const positionGroups = [
    { key: "active", label: "Active", hint: "Fresh, verified sell route", positions: portfolio.positions.filter((item) => item.market_status === "active") },
    { key: "exit_blocked", label: "Exit blocked", hint: "Fresh indication; route not currently executable", positions: portfolio.positions.filter((item) => item.market_status === "exit_blocked") },
    { key: "dormant", label: "Dormant", hint: "Still monitored; does not use an active slot", positions: portfolio.positions.filter((item) => item.market_status === "dormant") },
  ].filter((group) => group.positions.length > 0);
  return (
    <>
      <section className="page-heading">
        <div><span className="eyebrow"><Radio size={14} /> The Arena</span><h1>Your strategy, playing forward.</h1><p>Real market observations. Virtual {portfolio.quote_currency}. Every assumption visible.</p></div>
        <div className={`engine-control ${snapshot.running ? "running" : "stopped"}`}><div><strong><span />Paper engine {snapshot.running ? "running" : "stopped"}</strong><small>{snapshot.running ? "Analyzing and managing the paper portfolio." : portfolio.positions.length ? "Positions are preserved and still marked from fresh data." : "No new paper decisions or fills will occur."}</small></div><button onClick={() => void setEngineRunning(!snapshot.running)} disabled={busy}>{snapshot.running ? <Pause size={15} /> : <Play size={15} />}{snapshot.running ? "Stop" : hasHistory ? "Resume" : "Start"}</button></div>
      </section>

      <div className={`market-state-line ${snapshot.demo_mode ? "demo" : "live"}`}><span />{snapshot.demo_mode ? "Synthetic demo market" : "Solana mainnet paper feed"}{!snapshot.running && <small>Market observations continue while the paper engine is stopped.</small>}</div>

      {portfolio.risk_halted && <div className="risk-halt-note"><AlertTriangle size={17} /><div><strong>New entries are risk-paused</strong><p>The drawdown guardrail is active. Existing positions still receive exit management when fresh executable data is available.</p></div></div>}
      {portfolio.excluded_position_count > 0 && <div className="stale-value-note"><History size={17} /><div><strong>{portfolio.excluded_position_count} position{portfolio.excluded_position_count === 1 ? " is" : "s are"} outside executable equity</strong><p>{portfolio.route_blocked_position_count > 0 ? `${portfolio.route_blocked_position_count} fresh but exit-blocked. ` : ""}{portfolio.stale_position_count > 0 ? `${portfolio.stale_position_count} dormant without a fresh market. ` : ""}Headline equity excludes {money(portfolio.excluded_invested_value_lamports, portfolio.quote_currency, portfolio.quote_decimals)} of indicative or last-known value; last-known equity is {money(portfolio.last_known_equity_lamports, portfolio.quote_currency, portfolio.quote_decimals)}.</p></div></div>}

      <section className="hero-grid">
        <article className="card equity-card">
          <div className="card-label">Paper equity</div>
          <div className="equity-value">{money(portfolio.equity_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</div>
          <div className={`pnl-line ${totalPnl >= 0 ? "positive" : "negative"}`}>{signedMoney(totalPnl, portfolio.quote_currency, portfolio.quote_decimals)} <span>all time</span></div>
          <EquityChart points={snapshot.equity_history} />
          <div className="equity-meta">
            <span>{portfolio.reserved_cash_lamports ? "Available" : "Cash"} <strong>{money(portfolio.available_cash_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>
            {portfolio.reserved_cash_lamports > 0 && <span>Reserved <strong>{money(portfolio.reserved_cash_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>}
            <span>Executable value <strong>{money(portfolio.invested_value_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>
            <span>Drawdown <strong>{percent(portfolio.drawdown_fraction)}</strong></span>
          </div>
        </article>

        <article className="card risk-card">
          <div className="card-label"><ShieldCheck size={16} /> Risk personality</div>
          <h2>{title(snapshot.risk_mode)}</h2>
          <p>{riskCopy(snapshot.risk_mode)}</p>
          <div className={`risk-track mode-${snapshot.risk_mode}`}>
            <input
              aria-label="Risk mode"
              type="range"
              min={0}
              max={2}
              step={1}
              value={RISK_MODES.indexOf(snapshot.risk_mode)}
              disabled={busy}
              onChange={(event) => void setRisk(RISK_MODES[Number(event.target.value)]!)}
            />
          </div>
          <div className="risk-labels"><span>Safer</span><span>Balanced</span><span>Aggressive</span></div>
          <div className="guardrail"><ShieldCheck size={17} /><span>Structural safety and stale-data gates always remain active.</span></div>
          <div className={`auto-season-control ${snapshot.season_automation.enabled ? "enabled" : ""}`}>
            <RotateCcw size={16} />
            <div><strong>Auto new season <em>{snapshot.season_automation.enabled ? "On" : "Off"}</em></strong><small>{snapshot.season_automation.enabled ? snapshot.season_automation.detail : `Wait ${autoSeasonHours}h after a guarded pause with no active holdings; healthy data is always required.`}</small></div>
            {!snapshot.season_automation.enabled ? <label className="auto-season-delay">Wait<select aria-label="Automatic season wait" value={autoSeasonHours} disabled={busy} onChange={(event) => void setSeasonAutomation(false, Number(event.target.value))}>{Array.from({ length: 24 }, (_, index) => index + 1).map((hours) => <option value={hours} key={hours}>{hours}h</option>)}</select></label> : <span className="auto-season-delay-chip">{autoSeasonHours}h</span>}
            <button type="button" role="switch" aria-checked={snapshot.season_automation.enabled} aria-label={`${snapshot.season_automation.enabled ? "Disable" : "Enable"} automatic new seasons`} disabled={busy} onClick={() => void setSeasonAutomation(!snapshot.season_automation.enabled, snapshot.season_automation.enabled ? undefined : autoSeasonHours)}><span /></button>
          </div>
        </article>
      </section>

      <section className="stats-grid">
        <Stat label="Realized P/L" value={signedMoney(portfolio.realized_pnl_lamports, portfolio.quote_currency, portfolio.quote_decimals)} tone={portfolio.realized_pnl_lamports >= 0 ? "good" : "bad"} />
        <Stat label="Open P/L" value={signedMoney(portfolio.unrealized_pnl_lamports, portfolio.quote_currency, portfolio.quote_decimals)} tone={portfolio.unrealized_pnl_lamports >= 0 ? "good" : "bad"} />
        <Stat label="Open positions" value={String(portfolio.positions.length)} hint={`${capacityPositionCount} using active slots · ${portfolio.pending_orders.length} orders waiting`} />
        <Stat label="Observed events" value={compact(Object.values(snapshot.events).reduce((sum, value) => sum + value, 0))} hint={`${snapshot.tokens.length} recent tokens`} />
      </section>

      <section className="content-grid">
        <div>
          <SectionHeader title="Open positions" subtitle="Separated by current market and exit availability" />
          <div className="stack">
            {positionGroups.map((group) => {
              const collapsed = collapsedPositionGroups.has(group.key);
              return <div className="position-group" key={group.key}>
                <button
                  type="button"
                  className="position-group-heading"
                  aria-expanded={!collapsed}
                  aria-label={`${collapsed ? "Show" : "Hide"} ${group.label} positions`}
                  onClick={() => setCollapsedPositionGroups((current) => {
                    const next = new Set(current);
                    if (collapsed) next.delete(group.key);
                    else next.add(group.key);
                    return next;
                  })}
                >
                  <strong>{group.label}</strong><span>{group.hint}</span><b>{group.positions.length}</b><ChevronDown className={collapsed ? "collapsed" : ""} size={13} />
                </button>
                {!collapsed && group.positions.map((position) => <PositionCard key={position.position_id} position={position} currency={portfolio.quote_currency} decimals={portfolio.quote_decimals} />)}
              </div>;
            })}
            {!portfolio.positions.length && <EmptyState icon={<Landmark size={22} />} title="No open positions" copy={snapshot.running ? "Signal Arcade is watching. It will only enter after the data and selected risk limits agree." : "Start the paper engine when you are ready. Nothing can enter while it is stopped."} />}
          </div>
        </div>
        <div>
          <SectionHeader title="Decision feed" subtitle="The latest evidence checkpoints" />
          <div className="stack">
            {latestDecisionFeed.map((decision) => <DecisionRow key={decision.decision_id} decision={decision} explain={explain} loading={explainingId === decision.decision_id} />)}
            {!snapshot.decisions.length && <EmptyState icon={<Activity size={22} />} title="Waiting for evidence" copy="Choose Demo Market in Settings if you want to explore without waiting for a live launch." />}
          </div>
        </div>
      </section>

      <section>
        <SectionHeader title="Market radar" subtitle="Recent tokens with point-in-time market evidence quality" />
        <div className="token-grid">{snapshot.tokens.slice(0, 8).map((token) => <TokenCard key={token.mint} token={token} />)}</div>
      </section>
    </>
  );
}

function SetupArena({ snapshot, busy, setupPortfolio }: {
  snapshot: Snapshot;
  busy: boolean;
  setupPortfolio: (currency: QuoteCurrency, amount: string) => Promise<string | null>;
}) {
  const [currency, setCurrency] = useState<QuoteCurrency>("SOL");
  const [amount, setAmount] = useState("10");
  const [error, setError] = useState<string | null>(null);

  const chooseCurrency = (next: QuoteCurrency) => {
    setCurrency(next);
    setAmount(next === "SOL" ? "10" : "1000");
    setError(null);
  };
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = amount.trim();
    const decimals = currency === "SOL" ? 9 : 6;
    const match = /^(\d+)(?:\.(\d+))?$/.exec(cleaned);
    const numeric = Number(cleaned);
    if (!match || !Number.isFinite(numeric) || numeric <= 0) {
      setError("Enter a positive amount using numbers only.");
      return;
    }
    if ((match[2]?.length ?? 0) > decimals) {
      setError(`${currency} supports at most ${decimals} decimal places.`);
      return;
    }
    if ((currency === "SOL" && numeric > 1_000_000) || numeric > 1_000_000_000) {
      setError("That paper bankroll is unreasonably large.");
      return;
    }
    const setupError = await setupPortfolio(currency, cleaned);
    if (setupError) setError(setupError);
  };

  return <>
    <section className="page-heading setup-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> First paper season</span><h1>Choose the bankroll. Start when ready.</h1><p>Nothing trades on a fresh install until you create the virtual bankroll and press Start.</p></div>
      <div className={`mode-chip ${snapshot.demo_mode ? "demo" : "live"}`}><span />{snapshot.demo_mode ? "Synthetic demo market" : "Solana mainnet paper feed"}</div>
    </section>
    <article className="card setup-card">
      <div className="setup-intro"><strong>Virtual starting balance</strong><p>This is paper money only. No wallet, seed phrase, or real funds are used.</p></div>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <fieldset className="currency-choice"><legend>Account currency</legend><button type="button" className={currency === "SOL" ? "active" : ""} onClick={() => chooseCurrency("SOL")} aria-pressed={currency === "SOL"} aria-label="Use SOL for paper bankroll"><strong>SOL</strong><small>Native Solana accounting</small></button><button type="button" className={currency === "USDC" ? "active" : ""} onClick={() => chooseCurrency("USDC")} aria-pressed={currency === "USDC"} aria-label="Use USDC for paper bankroll"><strong>USDC</strong><small>Dollar-denominated accounting</small></button></fieldset>
        <label className="bankroll-input"><span>Starting amount</span><div><input value={amount} onChange={(event) => { setAmount(event.target.value); setError(null); }} inputMode="decimal" autoComplete="off" aria-label="Starting amount" aria-describedby={error ? "bankroll-help bankroll-error" : "bankroll-help"} /><strong>{currency}</strong></div><small id="bankroll-help">You can reset the paper season later to choose a different amount or currency.</small></label>
        {error && <p className="setup-error" id="bankroll-error" role="alert">{error}</p>}
        <div className="setup-foot"><p>{currency === "USDC" ? "Live USDC accounting converts simulated SOL costs using fresh observed SOL/USD data and abstains if that conversion is unavailable." : "SOL mode accounts directly in lamports, including simulated protocol and network fees."}</p><button className="button setup-submit" disabled={busy}>{busy ? <span className="mini-loader" /> : <CircleDollarSign size={16} />}{busy ? "Creating…" : "Create paper bankroll"}</button></div>
      </form>
    </article>
  </>;
}

export function Decisions({ decisions, explain, explainingId = null, serverTime, candidateWindowMinutes, staleMarketSeconds, engineRunning = true }: {
  decisions: Decision[];
  explain: (decision: Decision) => Promise<void>;
  explainingId?: string | null;
  serverTime: string;
  candidateWindowMinutes: number;
  staleMarketSeconds: number;
  engineRunning?: boolean;
}) {
  const [frozen, setFrozen] = useState<{ decisions: Decision[]; asOfMs: number } | null>(null);
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const paused = frozen !== null;
  const liveAsOfMs = safeDateMs(serverTime);
  const visibleDecisions = frozen?.decisions ?? decisions;
  const viewAsOfMs = frozen?.asOfMs ?? liveAsOfMs;
  const groups = useMemo(
    () => organizeDecisions(visibleDecisions, {
      asOfMs: viewAsOfMs,
      candidateWindowMinutes,
      staleMarketSeconds,
    }),
    [candidateWindowMinutes, staleMarketSeconds, viewAsOfMs, visibleDecisions],
  );
  const frozenIds = useMemo(
    () => new Set((frozen?.decisions ?? []).map((decision) => decision.decision_id)),
    [frozen],
  );
  const unseenCount = paused
    ? decisions.filter((decision) => !frozenIds.has(decision.decision_id)).length
    : 0;

  const togglePause = () => {
    if (paused) {
      setFrozen(null);
      setSelectedDecisionId(null);
    } else {
      setFrozen({ decisions, asOfMs: liveAsOfMs });
    }
  };

  const toggleDetails = (decision: Decision) => {
    if (selectedDecisionId === decision.decision_id) {
      setSelectedDecisionId(null);
      return;
    }
    if (!paused) {
      setFrozen({ decisions, asOfMs: liveAsOfMs });
    }
    setSelectedDecisionId(decision.decision_id);
  };

  return (
    <>
      <section className="page-heading decision-heading">
        <div><span className="eyebrow"><BrainCircuit size={14} /> Decision journal</span><h1>Best signals first. Noise tucked away.</h1><p>{engineRunning ? "The scoring engine keeps working live. Optional local AI explains completed decisions only when asked." : "The paper engine is stopped. Saved decisions remain available while market observations continue refreshing."}</p></div>
        <div className={`decision-view-control ${paused ? "paused" : "live"}`}>
          <button onClick={togglePause} aria-pressed={paused}>
            {paused ? <Play size={15} /> : <Pause size={15} />}
            {paused ? `Resume live${unseenCount ? ` · ${unseenCount} new` : ""}` : "Pause view"}
          </button>
          <small>{paused ? "Your view is frozen; analysis and paper trading continue." : "Following the latest decisions."}</small>
        </div>
      </section>

      <div className="decision-groups">
        <DecisionGroup
          id="best-signals"
          title="Best signals now"
          subtitle="Fresh enter and watch decisions, ranked by composite score"
          decisions={groups.best}
          explain={explain}
          explainingId={explainingId}
          selectedDecisionId={selectedDecisionId}
          toggleDetails={toggleDetails}
          defaultOpen
          ranked
          viewAsOfMs={viewAsOfMs}
          emptyCopy={groups.passed.length
            ? `No fresh enter or watch signal right now. ${groups.passed.length} latest candidate${groups.passed.length === 1 ? " is" : "s are"} safely shown in Passed for now.`
            : "No token currently meets the engine's enter or watch standard."}
        />
        <DecisionGroup
          id="passed-signals"
          title="Passed for now"
          subtitle="Latest checks the engine rejected or abstained from"
          decisions={groups.passed}
          explain={explain}
          explainingId={explainingId}
          selectedDecisionId={selectedDecisionId}
          toggleDetails={toggleDetails}
          emptyCopy="No latest token decisions are currently in the passed group."
          viewAsOfMs={viewAsOfMs}
        />
        <DecisionGroup
          id="earlier-checks"
          title="Expired from current view"
          subtitle="One latest checkpoint per token after its live evidence window closes"
          decisions={groups.earlier}
          explain={explain}
          explainingId={explainingId}
          selectedDecisionId={selectedDecisionId}
          toggleDetails={toggleDetails}
          emptyCopy="No expired checkpoints yet."
          viewAsOfMs={viewAsOfMs}
        />
      </div>
    </>
  );
}

function DecisionGroup({ id, title: heading, subtitle, decisions, explain, explainingId, selectedDecisionId, toggleDetails, defaultOpen = false, ranked = false, emptyCopy, viewAsOfMs }: {
  id: string;
  title: string;
  subtitle: string;
  decisions: Decision[];
  explain: (decision: Decision) => Promise<void>;
  explainingId: string | null;
  selectedDecisionId: string | null;
  toggleDetails: (decision: Decision) => void;
  defaultOpen?: boolean;
  ranked?: boolean;
  emptyCopy: string;
  viewAsOfMs: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`decision-group ${open ? "open" : ""}`}>
      <button className="decision-group-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls={id}>
        <span><strong>{heading}</strong><small>{subtitle}</small></span>
        <span className="decision-group-meta"><b>{decisions.length}</b><ChevronDown size={17} /></span>
      </button>
      {open && (
        <div id={id} className="decision-journal">
          {decisions.map((decision, index) => <DecisionBoardRow key={decision.decision_id} decision={decision} explain={explain} loading={explainingId === decision.decision_id} expanded={selectedDecisionId === decision.decision_id} toggleDetails={toggleDetails} rank={ranked ? index + 1 : undefined} viewAsOfMs={viewAsOfMs} />)}
          {!decisions.length && <EmptyState icon={<BrainCircuit size={22} />} title={`Nothing in ${heading.toLowerCase()}`} copy={emptyCopy} />}
        </div>
      )}
    </section>
  );
}

function LearningDisclosure({ id, title: heading, subtitle, summary, children }: {
  id: string;
  title: string;
  subtitle: string;
  summary: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return <section className={`learning-disclosure ${open ? "open" : ""}`}>
    <button
      className="learning-disclosure-toggle"
      type="button"
      aria-expanded={open}
      aria-controls={id}
      aria-label={`${open ? "Hide" : "Show"} ${heading.toLowerCase()}`}
      onClick={() => setOpen((value) => !value)}
    >
      <span><strong>{heading}</strong><small>{subtitle}</small></span>
      <span className="learning-disclosure-meta"><b>{summary}</b><ChevronDown size={17} /></span>
    </button>
    {open && <div className="learning-disclosure-body" id={id}>{children}</div>}
  </section>;
}

function LearningLab({ snapshot, setLearningMode, setAiMode, busy }: {
  snapshot: Snapshot;
  setLearningMode: (mode: LearningMode) => Promise<void>;
  setAiMode: (mode: AiDecisionMode) => Promise<void>;
  busy: boolean;
}) {
  const learning = snapshot.learning;
  const latest = learning.latest_model;
  const liveHealth = learning.active_model_health;
  const entryAvailability = learning.entry_outcome_availability;
  const challengerInterval = Math.max(1, learning.challenger_interval_outcomes);
  const outcomesUntilChallenger = Math.max(
    0,
    Math.min(challengerInterval, learning.outcomes_until_next_training),
  );
  const challengerProgress = challengerInterval - outcomesUntilChallenger;
  const progress = latest
    ? challengerProgress / challengerInterval
    : Math.min(1, learning.usable_outcome_count / learning.minimum_training_samples);
  const progressNow = latest ? challengerProgress : learning.usable_outcome_count;
  const progressMax = latest ? challengerInterval : learning.minimum_training_samples;
  const progressLabel = latest
    ? "Progress toward next challenger"
    : "Progress toward first learning challenger";
  const nextChallengerCopy = outcomesUntilChallenger === 0
    ? "Next challenger is ready to fit"
    : `${outcomesUntilChallenger} more usable outcome${outcomesUntilChallenger === 1 ? "" : "s"} until the next challenger`;
  const normalStateCopy = {
    paused: "Learning is paused. Existing lessons stay safely stored.",
    collecting: "Collecting independent forward outcomes before fitting anything.",
    challenger_testing: "A challenger exists, but it has not beaten the baseline safely yet.",
    ready: "A challenger passed forward checks and can be enabled when you choose.",
    active: "Qualified entry and hold challengers may act only inside their separate safety gates.",
  }[learning.state];
  const stateCopy = liveHealth.state === "suspended"
    ? "A previously active learner showed confident harm on later unseen outcomes, so the baseline automatically took control."
    : !learning.collecting_from_current_source && learning.mode !== "off"
      ? "Demo stays separate. Switch to Solana mainnet when you want to collect live-paper lessons."
      : normalStateCopy;
  const canActivate = learning.activation_available && learning.collecting_from_current_source;
  const holdReview = learning.recommended_hold_seconds[snapshot.risk_mode];
  const timing = learning.hold_timing_validation[snapshot.risk_mode];

  return <>
    <section className="page-heading learning-heading">
      <div><span className="eyebrow"><GraduationCap size={14} /> Learning Lab</span><h1>Experience earns influence—slowly.</h1><p>{stateCopy}</p></div>
      <div className="learning-controls">
        {learning.mode === "off"
          ? <button className="button learning-primary" onClick={() => void setLearningMode("shadow")} disabled={busy}><Play size={15} /> Start shadow learning</button>
          : <button className="button ghost" onClick={() => void setLearningMode("off")} disabled={busy}><Pause size={15} /> Pause learning</button>}
        {learning.mode === "active"
          ? <button className="button learning-primary" onClick={() => void setLearningMode("shadow")} disabled={busy}><ShieldCheck size={15} /> Return to shadow</button>
          : <button className="button learning-primary" onClick={() => void setLearningMode("active")} disabled={busy || !canActivate} title={!learning.collecting_from_current_source ? "Switch to Solana mainnet before activation" : learning.activation_available ? "Use the newest qualified challenger" : "Forward validation has not qualified a challenger yet"}><TrendingUp size={15} /> Use qualified learner</button>}
      </div>
    </section>

    {learning.demo_excluded && <div className="learning-demo-note"><ShieldCheck size={17} /><div><strong>Demo experience stays separate</strong><p>Synthetic tokens remain fun to explore, but they can never train or activate the live learner.</p></div></div>}

    <section className="card learning-progress-card">
      <div><span className={`learning-state state-${learning.state}`} /> <strong>{title(learning.state)}</strong><small>{learning.mode === "active" ? `Active model · ${learning.active_model?.version ?? "none"} · ${duration(holdReview)} hold review` : `Baseline remains in control · ${duration(holdReview)} hold review`}</small></div>
      <div className="learning-progress-copy"><strong>{latest ? `${learning.usable_outcome_count} usable` : `${learning.usable_outcome_count} / ${learning.minimum_training_samples}`}</strong><small>{latest ? `Minimum ${learning.minimum_training_samples} met · ${nextChallengerCopy}` : "usable five-minute outcomes before first training"}</small></div>
      <div className="learning-progress" role="progressbar" aria-label={progressLabel} aria-valuemin={0} aria-valuemax={progressMax} aria-valuenow={progressNow}><span style={{ width: `${progress * 100}%` }} /></div>
    </section>

    <section className="stats-grid learning-stats">
      <Stat label="Tokens remembered" value={compact(learning.observation_count)} hint={`Newest ${compact(learning.model_window_observations)} train · ${compact(learning.retained_observation_limit)} retained`} />
      <Stat label="Usable outcomes" value={compact(learning.usable_outcome_count)} hint="After entry, exit and fees" />
      <Stat label="Still unfolding" value={compact(learning.pending_count)} hint="Measured at 1, 5, 10, 15 and 20 minutes" />
      <Stat label="Unknown outcomes" value={compact(learning.unavailable_outcome_count)} hint="No fake P/L; unavailable exits still reduce horizon utility" />
    </section>

    <CoachRoom snapshot={snapshot} />

    <AiDecisionLabCard snapshot={snapshot} setAiMode={setAiMode} busy={busy} />

    <LearningDisclosure
      id="learning-evidence-details"
      title="Learning evidence"
      subtitle="Forward validation and the associations currently being tested"
      summary={latest ? latest.qualified ? "Qualified challenger" : "Challenger testing" : "Collecting"}
    >
      <div className="learning-grid">
        <article className="card learning-card">
          <SectionHeader title="Forward test" subtitle="Newest observations are never used to fit the challenger being judged" />
          {latest ? <div className="learning-metrics">
            <div><span>Qualified</span><strong className={latest.qualified ? "positive" : "negative"}>{latest.qualified ? "Yes" : "Not yet"}</strong></div>
            <div><span>Risk cohort</span><strong>{latest.risk_mode ? title(latest.risk_mode) : "Legacy"}</strong></div>
            <div><span>Validation outcomes</span><strong>{latest.validation_count}</strong></div>
            <div><span>Outcome availability</span><strong className={entryAvailability.qualified ? "positive" : ""}>{percent(entryAvailability.availability_fraction)}</strong></div>
            <div><span>Overlap embargo</span><strong>{latest.embargoed_count} excluded</strong></div>
            <div><span>Learner top group</span><strong className={latest.learner_top_mean_return >= 0 ? "positive" : "negative"}>{percentSigned(latest.learner_top_mean_return)}</strong></div>
            <div><span>Baseline top group</span><strong className={latest.baseline_top_mean_return >= 0 ? "positive" : "negative"}>{percentSigned(latest.baseline_top_mean_return)}</strong></div>
            <div><span>Learner rank fit</span><strong>{latest.learner_correlation.toFixed(2)}</strong></div>
            <div><span>Validation error</span><strong>{percent(latest.validation_rmse)}</strong></div>
            <div><span>Veto-policy proof</span><strong>{latest.policy_validation_count} actionable · {latest.policy_uplift_lower_bound === null ? "collecting" : `${percentSigned(latest.policy_uplift_lower_bound)} floor`}</strong></div>
            <div><span>Hold timing</span><strong className={timing.qualified ? "positive" : ""}>{timing.qualified ? `${duration(timing.selected_horizon_seconds)} qualified` : "Baseline"}</strong></div>
            <div><span>Timing validation</span><strong>{timing.validation_count} outcomes</strong></div>
            <div><span>Live health guard</span><strong className={liveHealth.state === "healthy" ? "positive" : liveHealth.state === "suspended" || liveHealth.state === "degraded" ? "negative" : ""}>{liveHealth.state === "healthy" && liveHealth.estimated_uplift !== null ? `${percentSigned(liveHealth.estimated_uplift)} estimated` : liveHealth.state === "collecting" ? `${liveHealth.usable_count} / ${liveHealth.minimum_samples}` : liveHealth.state === "suspended" ? "Returned to shadow" : title(liveHealth.state)}</strong></div>
          </div> : <EmptyState icon={<GraduationCap size={22} />} title="No model fitted yet" copy="Signal Arcade is recording outcomes, but it refuses to fit a learner from a tiny sample." />}
        </article>

        <article className="card learning-card">
          <SectionHeader title="What it is noticing" subtitle="Associations, not universal claims about every token" />
          {learning.lessons.length ? <div className="lesson-list">{learning.lessons.map((lesson) => <div key={lesson.feature}><span className={lesson.effect === "helped" ? "lesson-up" : "lesson-down"}>{lesson.effect === "helped" ? "↑" : "↓"}</span><div><strong>{title(lesson.label)}</strong><small>Associated with {lesson.effect === "helped" ? "better" : "worse"} fee-inclusive outcomes · strength {Math.abs(lesson.coefficient).toFixed(3)}</small></div></div>)}</div> : <EmptyState icon={<TrendingUp size={22} />} title="Lessons need time" copy="The first challenger appears only after enough live, forward five-minute outcomes exist." />}
        </article>
      </div>
    </LearningDisclosure>

    <LearningDisclosure
      id="learning-permanent-boundaries"
      title="Permanent boundaries"
      subtitle="Learning can become selective; it cannot become reckless"
      summary={`${learning.guardrails.length} always active`}
    >
      <article className="card learning-guardrails">
        <div>{learning.guardrails.map((guardrail) => <span key={guardrail}><ShieldCheck size={15} />{guardrail}</span>)}</div>
      </article>
    </LearningDisclosure>
  </>;
}

function CoachRoom({ snapshot }: { snapshot: Snapshot }) {
  const coach = snapshot.coach;
  const current = coach.recent_hypotheses.find((item) => item.context_active);
  const active = coach.mode === "shadow" && (current?.state === "testing" || current?.state === "promising");
  const progress = current
    ? Math.min(1, current.forward_usable_count / current.minimum_forward_samples)
    : 0;
  const stateCopy: Record<typeof coach.state, string> = {
    off: "Enable AI Shadow when you want the local coach to review completed evidence.",
    waiting: coach.paused_reason === "protecting_open_positions"
      ? "The coach is waiting while the engine manages open positions."
      : coach.paused_reason === "protecting_market_throughput"
        ? "Market work has priority. Coaching will resume after the event queue settles."
        : coach.paused_reason === "ollama_busy"
          ? "Ollama is busy with another optional task; coaching will retry automatically."
          : "Waiting for enough new measured outcomes to review another idea.",
    reviewing: "The local model is comparing bounded experiments in the background.",
    testing: "A coaching idea is collecting only outcomes created after it was proposed.",
    promising: "This idea has survived its forward Shadow test across multiple seasons.",
    inconclusive: "Too many forward exits were unavailable to trust this experiment yet.",
    not_supported: "New forward evidence did not support this coaching idea.",
  };
  const latestReview = coach.recent_reviews[0];
  return <article className="card coach-card">
    <div className="coach-heading">
      <SectionHeader title="AI Coach Room" subtitle="Slow reflection for the fast engine · every experiment remains Shadow-only" />
      <span className={`coach-state state-${coach.state}`}>{title(coach.state)}</span>
    </div>
    <div className="coach-summary">
      <div><span>Coach mode</span><strong>{coach.mode === "shadow" ? "Watching" : "Off"}</strong><small>{coach.mode === "off" ? "No local model work" : coach.worker_running ? "Background worker healthy" : "No AI coach calls"}</small></div>
      <div><span>Influence</span><strong>None</strong><small>Cannot change entries, exits, sizing or safety</small></div>
      <div><span>Next review</span><strong>{active ? "Forward test active" : coach.outcomes_until_review === 0 ? "When the engine is quiet" : `${coach.outcomes_until_review} outcomes`}</strong><small>{coach.outcomes_seen.toLocaleString()} fee-inclusive outcomes seen</small></div>
    </div>
    <p className="coach-state-copy"><Bot size={15} />{stateCopy[coach.state]}</p>
    {current ? <div className="coach-experiment">
      <div className="coach-experiment-head">
        <div><span>{current.kind === "entry_veto" ? "Entry protection experiment" : "Exit timing experiment"}</span><strong>{current.title}</strong><small>{current.rationale}</small></div>
        <span className={`coach-experiment-state state-${current.state}`}>{title(current.state)}</span>
      </div>
      <div className="coach-proof-grid">
        <div><span>Historical screen</span><strong>{current.discovery_uplift_lower_bound === null ? "Unknown" : `${percentSigned(current.discovery_uplift_lower_bound)} floor`}</strong><small>{current.discovery_usable_count} usable · could only propose</small></div>
        <div><span>New forward evidence</span><strong>{current.forward_mean_uplift === null ? "Collecting" : percentSigned(current.forward_mean_uplift)}</strong><small>{current.forward_usable_count} / {current.minimum_forward_samples} usable</small></div>
        <div><span>Outcome coverage</span><strong>{percent(current.forward_availability_fraction)}</strong><small>Needs {percent(current.minimum_availability_fraction)}</small></div>
        <div><span>Independent seasons</span><strong>{current.forward_season_count} / {coach.minimum_forward_seasons}</strong><small>No historical double counting</small></div>
      </div>
      <div className="coach-progress" role="progressbar" aria-label="Coach forward-test progress" aria-valuemin={0} aria-valuemax={current.minimum_forward_samples} aria-valuenow={current.forward_usable_count}><span style={{ width: `${progress * 100}%` }} /></div>
    </div> : <div className="coach-empty">
      <BrainCircuit size={21} />
      <div><strong>{latestReview?.selected_candidate_id === "none" ? "No experiment cleared screening yet" : "The coach is observing"}</strong><small>{latestReview?.summary || "It will review compact, normalized outcomes without placing work on the live decision path."}</small></div>
    </div>}
    {coach.last_error && <p className="coach-safe-error"><ShieldCheck size={14} />Optional coaching is waiting after a local-model issue; the engine was unaffected.</p>}
    <div className="coach-guardrails">{coach.guardrails.slice(0, 4).map((item) => <span key={item}><ShieldCheck size={13} />{item}</span>)}</div>
  </article>;
}

function AiDecisionLabCard({ snapshot, setAiMode, busy }: {
  snapshot: Snapshot;
  setAiMode: (mode: AiDecisionMode) => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const lab = snapshot.ai_lab;
  const qualification = lab.qualification;
  const selectedCatalog = lab.catalog.find((model) => model.name === lab.selected_model);
  const effectiveCompute = lab.runtime_compute === "idle" && lab.inference_busy
    ? lab.configured_accelerator
    : lab.runtime_compute;
  const computeLabel = effectiveCompute === "cpu" ? "CPU" : effectiveCompute === "gpu" ? "GPU" : effectiveCompute === "hybrid" ? "Hybrid" : title(effectiveCompute);
  const runtimeLabel = !lab.ollama_reachable
    ? "Runtime unavailable"
    : `${computeLabel} · ${lab.inference_busy ? "working" : "ready"}`;
  const modes: Array<{
    key: string;
    mode?: AiDecisionMode;
    label: string;
    copy: string;
    futureHint?: string;
  }> = [
    { key: "off", mode: "off", label: "Off", copy: "No AI calls" },
    { key: "shadow", mode: "shadow", label: "Shadow", copy: "Observes and tests without influence" },
    {
      key: "qualified-coach",
      label: "Qualified Coach",
      copy: "Bounded suggestions after proof",
      futureHint: "Future update — available only after Shadow earns enough forward, fee-inclusive evidence across multiple seasons.",
    },
    {
      key: "live-critic",
      label: "Live Critic",
      copy: "Real-time guidance after validation",
      futureHint: "Future update — considered only after Qualified Coach proves useful, safe, bounded, and reversible.",
    },
  ];
  const recent = lab.recent_assessments.slice(0, 5);
  const displayedMode = lab.mode === "guarded" ? "Qualified Coach (legacy)" : title(lab.mode);
  return <article className="card ai-lab-card">
    <div className="ai-lab-heading">
      <SectionHeader title="AI Decision Lab" subtitle="An optional local critic that must prove itself on saved, fee-inclusive outcomes" />
      <div className="learning-card-actions">
        <span className={`ai-mode-badge ${lab.mode}`}>{displayedMode}</span>
        <button
          className="button ghost learning-section-toggle"
          type="button"
          aria-expanded={open}
          aria-controls="ai-decision-lab-details"
          aria-label={`${open ? "Hide" : "Show"} AI Decision Lab details`}
          onClick={() => setOpen((value) => !value)}
        >{open ? "Hide" : "Show"}<ChevronDown size={15} /></button>
      </div>
    </div>
    {open && <div className="learning-collapse-body" id="ai-decision-lab-details">
    <div className="ai-mode-grid">
      {modes.map((option) => {
        const future = option.mode === undefined;
        const active = option.mode !== undefined && lab.mode === option.mode;
        const hintId = `ai-mode-${option.key}-hint`;
        return <div
          key={option.key}
          className={`ai-mode-option${future ? " future" : ""}`}
          tabIndex={future ? 0 : undefined}
          aria-describedby={future ? hintId : undefined}
        >
          <button
            className={active ? "active" : ""}
            aria-pressed={active}
            disabled={busy || future}
            onClick={option.mode ? () => void setAiMode(option.mode!) : undefined}
          >
            <span className="ai-mode-title"><strong>{option.label}</strong>{future && <em>Future</em>}</span>
            <small>{option.copy}</small>
          </button>
          {future && <span className="ai-mode-tooltip" id={hintId} role="tooltip">{option.futureHint}</span>}
        </div>;
      })}
    </div>
    <div className="ai-lab-summary">
      <div><span>Selected model</span><strong>{lab.selected_model}</strong><small>{selectedCatalog?.installed ? `Installed reviewed model · ${runtimeLabel}` : selectedCatalog ? "Install it in Settings before Shadow can run" : "Legacy/custom explanation model · choose a reviewed model in Settings"}</small></div>
      <div><span>Shadow evidence</span><strong>{qualification.resolved} resolved</strong><small>{percent(qualification.valid_fraction)} valid · evidence alone never enables a future stage</small></div>
      <div><span>Influence</span><strong>{lab.mode === "guarded" ? "Veto only" : "None"}</strong><small>AI can never create or resize an entry</small></div>
    </div>
    <p className="ai-lab-note"><ShieldCheck size={14} />Shadow is the only AI analysis stage available now. It observes normalized saved evidence without influencing trades; later stages stay locked until separately implemented and validated.</p>
    {recent.length > 0 && <div className="ai-assessment-list">
      {recent.map((assessment) => <div key={assessment.assessment_id}><span className={`ai-verdict ${assessment.valid ? assessment.verdict ?? "unknown" : "invalid"}`}>{assessment.valid ? title(assessment.verdict ?? "unknown") : aiFailureLabel(assessment.invalid_reason)}</span><div><strong title={tokenSymbolKnown(assessment.symbol) ? undefined : assessment.mint}>{tokenDisplayLabel(assessment.symbol, assessment.mint)}</strong><small>{assessment.valid ? assessment.summary || "Bounded assessment completed" : aiFailureDetail(assessment.invalid_reason)}</small></div><div><strong>{!assessment.valid ? "Ignored safely" : assessment.resolved_at ? assessment.counterfactual_uplift === null ? "No outcome" : `${percentSigned(assessment.counterfactual_uplift)} veto value` : "Measuring…"}</strong><small>{assessment.latency_ms.toLocaleString()} ms</small></div></div>)}
    </div>}
    </div>}
  </article>;
}

function LeaderboardView({ explain, reportIssue, resolveIssue }: {
  explain: (decision: Decision) => Promise<void>;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const [view, setView] = useState<"trades" | "seasons">("trades");
  const [sort, setSort] = useState<"profit" | "loss" | "recent">("profit");
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [explainingId, setExplainingId] = useState<string | null>(null);
  const [reviewingMint, setReviewingMint] = useState<string | null>(null);
  const dataRef = useRef<LeaderboardData | null>(null);
  const consecutiveLoadFailures = useRef(0);

  useEffect(() => {
    if (view !== "trades") return;
    let active = true;
    let refreshTimer: number | null = null;
    let controller: AbortController | null = null;
    const load = async (showLoading: boolean) => {
      if (!active) return;
      if (showLoading) {
        setLoading(true);
        setRetrying(false);
      }
      controller = new AbortController();
      let succeeded = false;
      try {
        const result = await api.leaderboard(sort, controller.signal);
        if (!active) return;
        dataRef.current = result;
        setData(result);
        setLoading(false);
        setRetrying(false);
        consecutiveLoadFailures.current = 0;
        succeeded = true;
        resolveIssue("leaderboard");
      } catch (cause) {
        if (!active || controller.signal.aborted) return;
        setRetrying(true);
        setLoading(dataRef.current === null);
        consecutiveLoadFailures.current += 1;
        if (consecutiveLoadFailures.current >= 2) {
          reportIssue("leaderboard", "Results could not be loaded", cause);
        }
      } finally {
        if (active) {
          refreshTimer = window.setTimeout(
            () => void load(false),
            succeeded ? 15_000 : 2_000,
          );
        }
      }
    };
    void load(true);
    return () => {
      active = false;
      controller?.abort();
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    };
  }, [reportIssue, resolveIssue, sort, view]);

  const explainEntry = async (decisionId: string) => {
    setExplainingId(decisionId);
    try {
      const decision = await api.decision(decisionId);
      await explain(decision);
      resolveIssue("leaderboard");
    } catch (cause) {
      reportIssue("leaderboard", "The entry decision could not be opened", cause);
    } finally {
      setExplainingId(null);
    }
  };

  const changingSort = data !== null && data.sort !== sort;

  return <>
    <section className="page-heading leaderboard-heading">
      <div><span className="eyebrow"><Trophy size={14} /> Results board</span><h1>{view === "trades" ? "Wins, losses, and the evidence behind them." : "Is the strategy improving each season?"}</h1><p>{view === "trades" ? "Rank complete paper trades, spot patterns, then open the exact saved entry checkpoint." : "Compare each paper bankroll using percentages that stay meaningful across SOL and USDC seasons."}</p></div>
      <div className="results-controls">
        <div className="results-view-tabs" aria-label="Results view">
          <button className={view === "trades" ? "active" : ""} aria-pressed={view === "trades"} onClick={() => setView("trades")}>Trades</button>
          <button className={view === "seasons" ? "active" : ""} aria-pressed={view === "seasons"} onClick={() => setView("seasons")}>Seasons</button>
        </div>
        {view === "trades" && <div className="leaderboard-sort" aria-label="Sort results">
          {(["profit", "loss", "recent"] as const).map((value) => <button key={value} className={sort === value ? "active" : ""} aria-pressed={sort === value} onClick={() => { if (value !== sort) { setLoading(true); setSort(value); } }}>{value === "profit" ? "Most profit" : value === "loss" ? "Most loss" : "Latest"}</button>)}
        </div>}
      </div>
    </section>
    {view === "seasons" ? <SeasonsView reportIssue={reportIssue} resolveIssue={resolveIssue} /> : <>
    {data && <section className="stats-grid leaderboard-stats">
      <Stat label="Closed trades" value={String(data.summary.closed_trades)} />
      <Stat label="Wins" value={String(data.summary.wins)} tone="good" />
      <Stat label="Losses" value={String(data.summary.losses)} tone="bad" />
      <Stat label="Win rate" value={data.summary.closed_trades ? percent(data.summary.wins / data.summary.closed_trades) : "—"} />
    </section>}
    <div className="leaderboard-table" role="table" aria-busy={loading || changingSort}>
      <div className="leaderboard-row leaderboard-head" role="row"><span>Rank</span><span>Token</span><span>Paper P/L</span><span>Fees</span><span>Held</span><span>Outcome</span><span /></div>
      {data?.rows.map((row, index) => {
        const tokenLabel = tokenDisplayLabel(row.symbol, row.mint);
        return <div className="leaderboard-row" role="row" key={`${row.mint}-${row.status}`}>
        <span className="leader-rank">#{index + 1}</span>
        <span className="leaderboard-token"><strong title={tokenSymbolKnown(row.symbol) ? undefined : row.mint}>{tokenLabel}</strong><small>{shortMint(row.mint)} · {row.status}{row.status === "open" && row.market_status !== "active" ? ` · ${humanize(row.market_status)}` : ""}</small><MintActions mint={row.mint} symbol={row.symbol} compact /></span>
        <span className={row.pnl_minor >= 0 ? "positive" : "negative"}><strong>{signedMoney(row.pnl_minor, row.quote_currency, row.quote_decimals)}</strong><small>{row.status === "open" && !row.mark_is_executable ? `conservative · ${signedMoney(row.last_known_pnl_minor, row.quote_currency, row.quote_decimals)} last known` : percentSigned(row.return_fraction)}</small></span>
        <span>{money(row.fees_minor, row.quote_currency, row.quote_decimals)}</span>
        <span>{duration(row.hold_seconds)}</span>
        <span>{row.exit_assessment ? <button className="exit-review-toggle" aria-expanded={reviewingMint === row.mint} onClick={() => setReviewingMint((current) => current === row.mint ? null : row.mint)}>{humanize(row.exit_assessment.reason)}</button> : row.exit_reason ? humanize(row.exit_reason) : row.status === "open" ? "Still open" : "Closed"}</span>
        <span>{row.entry_decision_id && <button className="quick-explain" onClick={() => void explainEntry(row.entry_decision_id!)} disabled={explainingId === row.entry_decision_id}>{explainingId === row.entry_decision_id ? <span className="mini-loader" /> : <Sparkles size={14} />}Why it bought</button>}</span>
        {reviewingMint === row.mint && row.exit_assessment && <div className="leaderboard-exit-review"><div><strong>Why it sold</strong><small>{humanize(row.exit_assessment.reason)} · policy {row.exit_assessment.policy_version}</small></div><div><span>Hold support<strong>{percent(row.exit_assessment.support_score)}</strong></span><span>Best marked return<strong>{row.peak_return_fraction === null ? "—" : percentSigned(row.peak_return_fraction)}</strong></span><span>Peak profit captured<strong>{row.peak_capture_fraction === null ? "—" : percentSigned(row.peak_capture_fraction)}</strong></span><span>Entry mode<strong>{row.entry_risk_mode ? title(row.entry_risk_mode) : "Legacy"}</strong></span></div>{row.exit_assessment.evidence.length > 0 && <p>{row.exit_assessment.evidence.join(" · ")}</p>}</div>}
      </div>})}
      {data !== null && data.sort === sort && !loading && !data.rows.length && <EmptyState icon={<Trophy size={22} />} title="No paper results yet" copy="Completed and open paper trades will appear here with their real simulated fees and saved entry evidence." />}
      {data === null && <div className="leaderboard-loading"><span className="mini-loader" /> {retrying ? "Saved results are taking longer. Retrying…" : "Loading saved results…"}</div>}
      {data !== null && (loading || changingSort || retrying) && <div className="leaderboard-refresh-note"><span className="mini-loader" /> {retrying ? "Showing the last saved order while Results retries…" : "Updating result order…"}</div>}
    </div>
    </>}
  </>;
}

function SeasonsView({ reportIssue, resolveIssue }: {
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const [data, setData] = useState<SeasonsData | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [chartRange, setChartRange] = useState<10 | 25 | "all">(10);
  const [historyLimit, setHistoryLimit] = useState<number | "all">(20);
  const consecutiveFailures = useRef(0);

  useEffect(() => {
    let active = true;
    let refreshTimer: number | null = null;
    let controller: AbortController | null = null;
    const load = async () => {
      controller = new AbortController();
      let succeeded = false;
      try {
        const result = await api.seasons(controller.signal);
        if (!active) return;
        setData(result);
        setRetrying(false);
        consecutiveFailures.current = 0;
        succeeded = true;
        resolveIssue("leaderboard");
      } catch (cause) {
        if (!active || controller.signal.aborted) return;
        setRetrying(true);
        consecutiveFailures.current += 1;
        if (consecutiveFailures.current >= 2) {
          reportIssue("leaderboard", "Season results could not be loaded", cause);
        }
      } finally {
        if (active) {
          refreshTimer = window.setTimeout(() => void load(), succeeded ? 15_000 : 2_000);
        }
      }
    };
    void load();
    return () => {
      active = false;
      controller?.abort();
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    };
  }, [reportIssue, resolveIssue]);

  if (data === null) {
    return <div className="leaderboard-table" aria-busy="true"><div className="leaderboard-loading"><span className="mini-loader" /> {retrying ? "Season history is taking longer. Retrying…" : "Loading season history…"}</div></div>;
  }
  if (!data.seasons.length) {
    return <div className="leaderboard-table"><EmptyState icon={<History size={22} />} title="No seasons yet" copy="Create a paper bankroll to begin Season 1. Its scorecard will be preserved when you start the next season." /></div>;
  }

  const orderedSeasons = [...data.seasons].sort((left, right) => left.season_number - right.season_number);
  const completed = orderedSeasons.filter((season) => season.status === "completed");
  const trend = seasonTrend(completed);
  const chartSeasons = chartRange === "all" ? orderedSeasons : orderedSeasons.slice(-chartRange);
  const newestSeasons = [...orderedSeasons].reverse();
  const visibleHistory = historyLimit === "all" ? newestSeasons : newestSeasons.slice(0, historyLimit);
  const hiddenHistoryCount = newestSeasons.length - visibleHistory.length;
  return <>
    <section className="stats-grid leaderboard-stats season-stats">
      <Stat label="Seasons" value={String(data.summary.season_count)} hint="Current included" />
      <Stat label="Completed" value={String(data.summary.completed_seasons)} />
      <Stat label="Profitable" value={String(data.summary.profitable_seasons)} tone={data.summary.profitable_seasons ? "good" : undefined} />
      <Stat label="Average win rate" value={data.summary.average_win_rate === null ? "—" : percent(data.summary.average_win_rate)} hint="Completed seasons" />
    </section>
    <section className="season-overview-grid">
      <article className="card season-chart-card">
        <div className="season-card-heading">
          <div><span>Win rate by season</span><strong>Performance progression</strong></div>
          <div className="season-chart-actions">
            <small>{chartRange === "all" ? `All ${orderedSeasons.length} seasons` : `Latest ${Math.min(chartRange, orderedSeasons.length)} of ${orderedSeasons.length}`}</small>
            {orderedSeasons.length > 10 && <div className="season-range-tabs" role="group" aria-label="Season chart range">
              <button type="button" className={chartRange === 10 ? "active" : ""} aria-pressed={chartRange === 10} onClick={() => setChartRange(10)}>Latest 10</button>
              <button type="button" className={chartRange === 25 ? "active" : ""} aria-pressed={chartRange === 25} onClick={() => setChartRange(25)}>Latest 25</button>
              <button type="button" className={chartRange === "all" ? "active" : ""} aria-pressed={chartRange === "all"} onClick={() => setChartRange("all")}>All</button>
            </div>}
          </div>
        </div>
        <SeasonWinChart seasons={chartSeasons} all={chartRange === "all"} total={orderedSeasons.length} />
        <p><BrainCircuit size={14} /> Starting a new season resets its bankroll, while retained learning continues across seasons.</p>
      </article>
      <article className={`card season-trend-card ${trend.tone}`}>
        <TrendingUp size={20} />
        <span>Season read</span>
        <strong>{trend.title}</strong>
        <p>{trend.copy}</p>
      </article>
    </section>
    {newestSeasons.length > 20 && <div className="season-history-heading">
      <div><strong>Complete season history</strong><small>Every scorecard is retained</small></div>
      <span>Showing {visibleHistory.length} of {newestSeasons.length}</span>
    </div>}
    <div className="season-table" role="table" aria-label="Paper season scorecards" aria-busy={retrying}>
      <div className="season-row season-head" role="row"><span>Season</span><span>Bankroll</span><span>Net result</span><span>Win rate</span><span>Trades</span><span>Drawdown</span><span>Duration</span></div>
      {visibleHistory.map((season) => <SeasonRow season={season} key={season.season_id} />)}
      {hiddenHistoryCount > 0 && <div className="season-history-more">
        <span>{hiddenHistoryCount} older scorecard{hiddenHistoryCount === 1 ? "" : "s"} safely retained</span>
        <div>
          <button type="button" className="button subtle" onClick={() => setHistoryLimit((current) => current === "all" ? current : current + 20)}>Show {Math.min(20, hiddenHistoryCount)} older</button>
          <button type="button" className="button subtle" aria-label={`Show all ${newestSeasons.length} seasons`} onClick={() => setHistoryLimit("all")}>Show all</button>
        </div>
      </div>}
      {retrying && <div className="leaderboard-refresh-note"><span className="mini-loader" /> Showing saved season scorecards while this view retries…</div>}
    </div>
  </>;
}

function SeasonWinChart({ seasons, all, total }: { seasons: PaperSeason[]; all: boolean; total: number }) {
  const barsRef = useRef<HTMLDivElement>(null);
  const latestSeasonId = seasons.at(-1)?.season_id;
  useEffect(() => {
    if (all) return;
    const bars = barsRef.current;
    if (!bars) return;
    let pinnedToLatest = true;
    const pinLatest = () => { bars.scrollLeft = bars.scrollWidth; };
    const frame = window.requestAnimationFrame(pinLatest);
    const trackPosition = () => {
      pinnedToLatest = Math.abs(bars.scrollWidth - bars.clientWidth - bars.scrollLeft) < 2;
    };
    bars.addEventListener("scroll", trackPosition, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      if (pinnedToLatest) pinLatest();
    });
    observer?.observe(bars);
    return () => {
      window.cancelAnimationFrame(frame);
      bars.removeEventListener("scroll", trackPosition);
      observer?.disconnect();
    };
  }, [all, latestSeasonId, seasons.length]);
  if (all) return <SeasonHistoryChart seasons={seasons} />;
  const first = seasons[0];
  const last = seasons.at(-1);
  const details = seasons.map((season) => `Season ${season.season_number}: ${season.win_rate === null ? "no closed trades" : `${Math.round(season.win_rate * 100)}% win rate`}`).join("; ");
  const label = total > seasons.length && first && last ? `Latest ${seasons.length} of ${total} seasons, Seasons ${first.season_number} through ${last.season_number}. ${details}` : details;
  return <div className="season-win-chart" role="img" aria-label={label}>
    <div className="season-chart-axis"><span>100%</span><span>50%</span><span>0%</span></div>
    <div className={`season-chart-bars ${seasons.length > 12 ? "compact" : ""}`} ref={barsRef}>
      {seasons.map((season) => {
        const rate = season.win_rate;
        return <div className={`season-chart-column ${season.status}`} key={season.season_id}>
          <div className="season-chart-value">{rate === null ? "—" : percent(rate)}</div>
          <div className="season-chart-track"><span style={{ height: rate === null ? "0" : `${Math.max(0, Math.min(100, rate * 100))}%` }} /></div>
          <strong>S{season.season_number}</strong>
          <small className={(season.net_return_fraction ?? 0) >= 0 ? "positive" : "negative"}>{season.net_return_fraction === null ? "—" : percentSigned(season.net_return_fraction)}</small>
        </div>;
      })}
    </div>
  </div>;
}

function SeasonHistoryChart({ seasons }: { seasons: PaperSeason[] }) {
  const width = 1000;
  const height = 192;
  const left = 42;
  const right = 14;
  const top = 18;
  const bottom = 31;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const points = seasons.map((season, index) => {
    const x = left + (seasons.length <= 1 ? plotWidth / 2 : (index / (seasons.length - 1)) * plotWidth);
    const rate = season.win_rate;
    return { season, x, y: rate === null ? null : top + (1 - Math.max(0, Math.min(1, rate))) * plotHeight };
  });
  let path = "";
  let drawing = false;
  for (const point of points) {
    if (point.y === null) {
      drawing = false;
      continue;
    }
    path += `${drawing ? " L" : " M"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    drawing = true;
  }
  const measured = seasons.filter((season) => season.win_rate !== null);
  const labelStep = Math.max(1, Math.ceil(Math.max(1, seasons.length - 1) / 8));
  const labelIndexes = new Set(points.map((_, index) => index).filter((index) => index === 0 || index === points.length - 1 || index % labelStep === 0));
  const rates = measured.map((season) => season.win_rate!);
  const latest = seasons.at(-1);
  const accessibleLabel = measured.length
    ? `All ${seasons.length} seasons. Measured win rates range from ${percent(Math.min(...rates))} to ${percent(Math.max(...rates))}. Latest is Season ${latest?.season_number}, ${latest?.win_rate === null ? "with no closed trades" : `${percent(latest?.win_rate ?? 0)} win rate`}.`
    : `All ${seasons.length} seasons. No season has a measured win rate yet.`;

  return <div className="season-history-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={accessibleLabel}>
      {[1, 0.5, 0].map((rate) => {
        const y = top + (1 - rate) * plotHeight;
        return <g key={rate}><line className="season-line-grid" x1={left} x2={width - right} y1={y} y2={y} /><text className="season-line-y-label" x={left - 8} y={y + 3}>{Math.round(rate * 100)}%</text></g>;
      })}
      {path && <path className="season-line-path" d={path.trim()} />}
      {points.map((point) => point.y === null ? null : <circle
        className={`season-line-point ${point.season.status} ${(point.season.net_return_fraction ?? 0) >= 0 ? "positive" : "negative"}`}
        cx={point.x}
        cy={point.y}
        r={point.season.status === "current" ? 4.5 : 3}
        key={point.season.season_id}
      ><title>{`Season ${point.season.season_number}: ${percent(point.season.win_rate!)} win rate, ${point.season.net_return_fraction === null ? "net return unavailable" : `${percentSigned(point.season.net_return_fraction)} net return`}${point.season.status === "current" ? ", current" : ""}`}</title></circle>)}
      {points.map((point, index) => labelIndexes.has(index) ? <text className="season-line-x-label" textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"} x={point.x} y={height - 8} key={`label-${point.season.season_id}`}>S{point.season.season_number}</text> : null)}
    </svg>
    {!measured.length && <span className="season-line-empty">Waiting for closed paper trades</span>}
    <div className="season-line-legend"><span><i /> Win rate across every season</span><small>Exact values remain in the scorecards below</small></div>
  </div>;
}

function SeasonRow({ season }: { season: PaperSeason }) {
  const ending = season.ending_equity_minor;
  const winRate = season.win_rate;
  return <div className={`season-row ${season.status}`} role="row">
    <span className="season-identity" data-label="Season"><strong>Season {season.season_number}</strong><small>{season.status === "current" ? "Live scorecard" : `Finished ${shortDate(season.ended_at!)}`}</small><em>{season.status}</em></span>
    <span data-label="Bankroll"><strong>{money(season.starting_minor, season.quote_currency, season.quote_decimals)}</strong><small>{ending === null ? "No equity mark" : `${season.status === "current" ? "Now" : "Ended"} ${money(ending, season.quote_currency, season.quote_decimals)}`}</small></span>
    <span data-label="Net result" className={season.net_pnl_minor >= 0 ? "positive" : "negative"}><strong>{signedMoney(season.net_pnl_minor, season.quote_currency, season.quote_decimals)}</strong><small>{season.net_return_fraction === null ? "—" : percentSigned(season.net_return_fraction)}</small></span>
    <span data-label="Win rate"><strong>{winRate === null ? "—" : percent(winRate)}</strong><small>{season.wins}W · {season.losses}L{season.break_even ? ` · ${season.break_even} even` : ""}</small></span>
    <span data-label="Trades"><strong>{season.closed_trades.toLocaleString()}</strong><small>{money(season.total_fees_minor, season.quote_currency, season.quote_decimals)} fees</small></span>
    <span data-label="Drawdown"><strong>{percent(season.ending_drawdown_fraction)}</strong><small>{season.open_positions ? `${season.open_positions} open at ${season.status === "current" ? "present" : "finish"}` : "No open positions"}</small></span>
    <span data-label="Duration"><strong>{longDuration(season.duration_seconds)}</strong><small>Started {shortDate(season.started_at)}</small></span>
  </div>;
}

function seasonTrend(completed: PaperSeason[]): { title: string; copy: string; tone: "neutral" | "good" | "bad" } {
  if (completed.length < 2) {
    return { title: "Building the baseline", copy: completed.length ? "Complete one more season to compare net return and win rate without guessing from a single run." : "The current season is establishing the first honest baseline.", tone: "neutral" };
  }
  const previous = completed.at(-2)!;
  const latest = completed.at(-1)!;
  const returnDelta = (latest.net_return_fraction ?? 0) - (previous.net_return_fraction ?? 0);
  const winDelta = latest.win_rate !== null && previous.win_rate !== null ? latest.win_rate - previous.win_rate : null;
  const direction = returnDelta > 0.001 ? "improved" : returnDelta < -0.001 ? "declined" : "held steady";
  const tone = returnDelta > 0.001 ? "good" : returnDelta < -0.001 ? "bad" : "neutral";
  return {
    title: `Latest net return ${direction}`,
    copy: `Season ${latest.season_number} finished at ${percentSigned(latest.net_return_fraction ?? 0)} versus ${percentSigned(previous.net_return_fraction ?? 0)} in Season ${previous.season_number}.${winDelta === null ? "" : ` Win rate moved ${percentSigned(winDelta)}.`}`,
    tone,
  };
}

function DecisionEvidence({ decision }: { decision: Decision }) {
  const values = decision.feature_snapshot.values;
  const reserve = values.virtual_quote_reserve_sol?.value;
  const estimatedImpact = typeof reserve === "number" && reserve > 0 && decision.planned_order_size_sol
    ? Math.min(1, decision.planned_order_size_sol / reserve)
    : null;
  const evidence = [
    ["Token age", values.age_seconds, "duration"],
    ["Trades in 1 minute", values.trade_count_1m, "number"],
    ["Trades in 5 minutes", values.trade_count_5m, "number"],
    ["Unique wallets (5m)", values.unique_wallets_5m, "number"],
    ["Buy ratio (5m)", values.buy_ratio_5m, "percent"],
    ["Curve progress", values.curve_progress, "percent"],
    ["Momentum (1m)", values.momentum_1m, "signedPercent"],
    ["Wallet volume concentration", values.wallet_volume_hhi, "percent"],
    ["Reserve depth", values.virtual_quote_reserve_sol, "sol"],
    ["Observed fee (basis points)", values.observed_fee_bps, "number"],
    ["Creator sells (5m)", values.creator_sells_5m, "number"],
    ["Mint safety", values.mint_safety_verified, "boolean"],
  ] as const;
  return <section className="explain-evidence">
    <div className="explain-score-grid"><ScoreBar label="Opportunity" value={decision.score.opportunity} tone="good" /><ScoreBar label="Danger" value={decision.score.danger} tone="bad" /><ScoreBar label="Execution" value={decision.score.execution} tone="blue" /><ScoreBar label="Evidence confidence" value={decision.score.confidence} tone="purple" /></div>
    <h3>What the engine actually saw</h3>
    <div className="evidence-grid">{evidence.map(([label, item, format]) => <div key={label}><span>{label}</span><strong>{formatEvidence(item?.value, format)}</strong><small>{item ? `${Math.round(item.quality * 100)}% source quality · ${duration(item.freshness_seconds)} old` : "Not recorded"}</small></div>)}<div><span>Estimated entry impact</span><strong>{estimatedImpact === null ? "Unknown" : percent(estimatedImpact)}</strong><small>Planned paper size ÷ observed reserve depth</small></div></div>
    <div className="explain-gates"><div><strong>Positive evidence</strong>{decision.reasons.map((reason) => <span key={reason}><Check size={13} />{reason}</span>)}</div><div><strong>{decision.blockers.length ? "Gates that stopped entry" : "Safety gates"}</strong>{decision.blockers.length ? decision.blockers.map((blocker) => <span key={blocker}><AlertTriangle size={13} />{humanize(blocker)}</span>) : <span><ShieldCheck size={13} />All configured entry gates passed at this checkpoint.</span>}</div></div>
  </section>;
}

function Replay({ snapshot }: { snapshot: Snapshot }) {
  const currency = snapshot.portfolio.quote_currency;
  return <><section className="page-heading"><div><span className="eyebrow"><History size={14} /> Replay</span><h1>The score is net of the friction.</h1><p>Review fills, latency, price impact, protocol charges and simulated network fees.</p></div></section><article className="card replay-chart"><SectionHeader title="Equity history" subtitle={`${snapshot.equity_history.length} recorded market checkpoints · ${currency} account`} /><EquityChart points={snapshot.equity_history} tall /></article><SectionHeader title="Fill receipts" subtitle="Immutable paper execution evidence" /><div className="fills-table" role="table"><div className="fill-row fill-head" role="row"><span>Time</span><span>Token</span><span>Side</span><span>Net {currency}</span><span>Fees</span><span>Impact</span><span>Latency</span></div>{snapshot.fills.map((fill) => <FillRow fill={fill} key={fill.fill_id} />)}{!snapshot.fills.length && <EmptyState icon={<CircleDollarSign size={22} />} title="No fills yet" copy="A receipt appears after order latency when the latest observed reserve state is still executable." />}</div></>;
}

function StorageManager({ snapshot, refresh, setBusy, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const storage = snapshot.storage;
  const [maxGb, setMaxGb] = useState(() => (storage.max_database_bytes / 1024**3).toFixed(1));
  const [retention, setRetention] = useState(() => String(storage.raw_trade_retention_hours));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const usedFraction = Math.min(1, storage.live_bytes / Math.max(1, storage.max_database_bytes));
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const limit = Number(maxGb);
    const hours = Number(retention);
    if (!Number.isFinite(limit) || limit < 0.5 || limit > 100 || !Number.isInteger(hours) || hours < 1 || hours > 720) {
      reportIssue("storage", "Storage settings are invalid", new Error("Use 0.5–100 GB and 1–720 retention hours."));
      return;
    }
    setSaved(false);
    setSaving(true);
    setBusy(true);
    try {
      await api.updateStorageSettings(limit, hours);
      resolveIssue("storage");
      setSaved(true);
      void refresh();
    } catch (cause) {
      reportIssue("storage", "Storage settings were not saved", cause);
    } finally {
      setSaving(false);
      setBusy(false);
    }
  };
  return <article className="card settings-card storage-card">
    <SectionHeader title="Storage budget" subtitle="Bound high-volume evidence without deleting trades, P/L, ledger entries, or learned models" />
    <div className="storage-meter"><span style={{ width: `${usedFraction * 100}%` }} /></div>
    <div className="storage-summary"><strong>{formatBytes(storage.live_bytes)} live data</strong><span>{formatBytes(storage.database_bytes)} allocated · {formatBytes(storage.reclaimable_bytes)} reusable</span></div>
    <form className="storage-form" onSubmit={save}><label>Maximum database<input type="number" min="0.5" max="100" step="0.5" value={maxGb} onChange={(event) => { setMaxGb(event.target.value); setSaved(false); }} disabled={saving} /><span>GB</span></label><label>Raw event history<input type="number" min="1" max="720" step="1" value={retention} onChange={(event) => { setRetention(event.target.value); setSaved(false); }} disabled={saving} /><span>hours</span></label><button className={`button${saved ? " saved" : ""}`} type="submit" disabled={saving} aria-live="polite">{saving ? <span className="mini-loader" /> : saved ? <Check size={15} /> : <Save size={15} />}{saving ? "Saving…" : saved ? "Saved" : "Save"}</button></form>
    {saved && <p className="storage-saved" role="status"><Check size={13} />Policy saved. Cleanup continues safely in the background.</p>}
    <p className="storage-note"><HardDrive size={14} />SQLite reuses freed pages, so an older file may stay physically large without continuing to grow. Docker text logs are separately rotated and capped at about 30 MB by the included Compose files.</p>
  </article>;
}

const DOCKER_UPDATE_COMMANDS = "docker compose pull\ndocker compose up -d";

function MaintenanceManager({ snapshot, refresh, busy, setBusy, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const operation = snapshot.maintenance_operation;
  const active = operation?.state === "running" || operation?.state === "ready";
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState(false);
  const [copied, setCopied] = useState(false);
  const activeDownload = snapshot.ai_lab.downloads.some(
    (download) => download.status === "queued" || download.status === "downloading",
  );

  const prepare = async () => {
    setWorking(true);
    setBusy(true);
    try {
      await api.prepareForUpgrade();
      resolveIssue("maintenance");
      setConfirming(false);
      await refresh();
    } catch (cause) {
      reportIssue("maintenance", "Upgrade preparation did not start", cause);
    } finally {
      setWorking(false);
      setBusy(false);
    }
  };

  const cancel = async () => {
    setWorking(true);
    try {
      await api.cancelUpgradePreparation();
      resolveIssue("maintenance");
      await refresh();
    } catch (cause) {
      reportIssue("maintenance", "Upgrade preparation was not cancelled", cause);
    } finally {
      setWorking(false);
    }
  };

  const copyCommands = async () => {
    const successful = await copyText(DOCKER_UPDATE_COMMANDS);
    setCopied(successful);
    if (!successful) {
      reportIssue("maintenance", "Docker commands were not copied", new Error("Copy the two displayed commands manually."));
      return;
    }
    resolveIssue("maintenance");
    window.setTimeout(() => setCopied(false), 2_000);
  };

  return <article className={`card settings-card maintenance-manager ${operation?.state ?? "idle"}`}>
    <SectionHeader title="Maintenance & updates" subtitle="Quiesce paper activity before replacing containers, without giving the app control of Docker" />
    {operation?.state === "running" ? (
      <div className="maintenance-state" role="status" aria-live="polite">
        <span className="mini-loader" />
        <div><strong>Preparing safely…</strong><p>{operation.detail}</p><small>{humanize(operation.stage)} · keep this page open or return later</small></div>
      </div>
    ) : operation?.state === "ready" ? (
      <div className="maintenance-ready" role="status">
        <div className="maintenance-ready-copy"><Check size={18} /><div><strong>Ready for the Docker update</strong><p>{operation.detail}</p></div></div>
        <div className="maintenance-preserved"><span><ShieldCheck size={13} />{snapshot.portfolio.positions.length} open position{snapshot.portfolio.positions.length === 1 ? "" : "s"} preserved</span><span><ShieldCheck size={13} />Learning, seasons and settings preserved</span>{operation.cancelled_pending_orders > 0 && <span><Check size={13} />{operation.cancelled_pending_orders} unfilled order{operation.cancelled_pending_orders === 1 ? "" : "s"} cancelled</span>}{operation.interrupted_ai_downloads > 0 && <span><AlertTriangle size={13} />Restart {operation.interrupted_ai_downloads} model download after updating</span>}</div>
        <div className="maintenance-commands"><div><code>docker compose pull</code><code>docker compose up -d</code></div><button className="button ghost" type="button" onClick={() => void copyCommands()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copied" : "Copy commands"}</button></div>
        <p className="maintenance-note">Run these in the folder containing a Docker Hub Compose file. For a local source checkout, run <code>docker compose up -d --build</code> instead. Portainer and similar hosts can use their pull-and-redeploy action. Signal Arcade resumes the previous engine state after health checks pass.</p>
        <button className="button ghost maintenance-cancel" type="button" disabled={working} onClick={() => void cancel()}>{working ? <span className="mini-loader" /> : <RotateCcw size={15} />}Cancel and resume without updating</button>
      </div>
    ) : confirming ? (
      <div className="maintenance-confirm">
        <p><strong>Prepare Signal Arcade for an update?</strong>The paper engine will pause at an atomic boundary, unfilled orders will be cancelled, and optional AI work will settle. Open positions, history, learning, provider settings, seasons, bankroll configuration and downloaded models stay intact.</p>
        {activeDownload && <p className="maintenance-warning"><AlertTriangle size={14} />The current local-model download will stop safely and can be restarted after the update.</p>}
        <p className="maintenance-note">This does not expose the Docker socket or stop Docker by itself. When preparation is complete, this screen shows the two host commands to run.</p>
        <div className="maintenance-actions"><button className="button ghost" type="button" disabled={working} onClick={() => setConfirming(false)}>Not now</button><button className="button" type="button" disabled={working} onClick={() => void prepare()}>{working ? <span className="mini-loader" /> : <ShieldCheck size={15} />}{working ? "Starting…" : "Prepare safely"}</button></div>
      </div>
    ) : (
      <div className="maintenance-idle">
        <div><ShieldCheck size={18} /><p><strong>Upgrade without guessing when it is safe</strong><span>Prepare first, wait for Ready, then run the normal Docker Compose update. No paper history or learning is reset.</span></p></div>
        {operation?.state === "failed" && <p className="maintenance-warning"><AlertTriangle size={14} />{operation.detail}</p>}
        {operation?.state === "completed" && <p className="maintenance-success"><Check size={14} />Updated safely from v{operation.prepared_version} to v{operation.restarted_version ?? snapshot.version}.</p>}
        <button className="button ghost" type="button" disabled={working || (busy && !active)} onClick={() => setConfirming(true)}><ShieldCheck size={15} />Prepare for upgrade</button>
      </div>
    )}
  </article>;
}

function SettingsView({ snapshot, refresh, busy, setBusy, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const [confirmReset, setConfirmReset] = useState(false);
  const changeMode = async (demo: boolean) => {
    setBusy(true);
    try {
      await api.setDemo(demo);
      resolveIssue("mode");
      await refresh();
    } catch (cause) {
      reportIssue("mode", "Market source was not changed", cause);
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    setBusy(true);
    try {
      await api.reset();
      resolveIssue("reset");
      setConfirmReset(false);
      await refresh();
    } catch (cause) {
      reportIssue("reset", "Paper season was not reset", cause);
    } finally {
      setBusy(false);
    }
  };
  return <>
    <section className="page-heading"><div><span className="eyebrow"><Settings size={14} /> Settings</span><h1>Advanced controls, kept out of play.</h1><p>The free keyless path is ready by default. Provider upgrades stay local, capped and visible.</p></div></section>
    <div className="settings-grid">
      <article className="card settings-card">
        <SectionHeader title="Market source" subtitle="Switching stops the engine and returns to bankroll setup so data modes never mix" />
        <label className="mode-option"><span><Radio size={18} /><strong>Solana mainnet</strong><small>Official program logs through the configured public or private RPC.</small></span><input type="radio" name="market-source" checked={!snapshot.demo_mode} disabled={busy} onChange={() => void changeMode(false)} /></label>
        <label className="mode-option"><span><Sparkles size={18} /><strong>Synthetic demo</strong><small>Fully offline market activity. External enrichment is paused in this mode.</small></span><input type="radio" name="market-source" checked={snapshot.demo_mode} disabled={busy} onChange={() => void changeMode(true)} /></label>
      </article>
      <article className="card settings-card">
        <SectionHeader title="Data health" subtitle="The engine abstains when required evidence is stale" />
        <HealthRows health={snapshot.provider_health} />
        <div className={`health-summary ${snapshot.database_ok ? "healthy" : "unhealthy"}`}><span />SQLite connection {snapshot.database_ok ? "healthy" : "failed"}</div>
        <div className={`health-summary ${snapshot.event_pipeline.degraded ? "unhealthy" : "healthy"}`}><span />Market processing {snapshot.event_pipeline.degraded ? snapshot.event_pipeline.degraded_reasons.map(humanize).join(", ") : "current"} · {compact(snapshot.event_pipeline.processed)} handled ({compact(snapshot.event_pipeline.persisted)} retained)</div>
      </article>
      <StorageManager snapshot={snapshot} refresh={refresh} setBusy={setBusy} reportIssue={reportIssue} resolveIssue={resolveIssue} />
      <AiModelManager snapshot={snapshot} refresh={refresh} reportIssue={reportIssue} resolveIssue={resolveIssue} />
      <ProviderManager snapshot={snapshot} refresh={refresh} busy={busy} setBusy={setBusy} reportIssue={reportIssue} resolveIssue={resolveIssue} />
      <MaintenanceManager snapshot={snapshot} refresh={refresh} busy={busy} setBusy={setBusy} reportIssue={reportIssue} resolveIssue={resolveIssue} />
      <article className="card settings-card danger-zone">
        <SectionHeader title="New paper season" subtitle="On-chain evidence and learned experience remain; this season's money and P/L reset" />
        {confirmReset ? <div className="reset-confirm"><p>This stops the paper engine and returns to setup for a fresh bankroll. Learning Lab observations and model versions are preserved.</p><div><button className="button ghost" disabled={busy} onClick={() => setConfirmReset(false)}>Cancel</button><button className="button danger" disabled={busy} onClick={() => void reset()}>{busy ? "Resetting safely…" : "Reset paper portfolio"}</button></div></div> : <button className="button ghost" disabled={busy} onClick={() => setConfirmReset(true)}><RotateCcw size={16} /> Start a new season</button>}
      </article>
    </div>
  </>;
}

function AiModelManager({ snapshot, refresh, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const lab = snapshot.ai_lab;
  const selectedIsCurated = lab.catalog.some((model) => model.name === lab.selected_model);
  const downloadActive = lab.downloads.some((item) => item.status === "queued" || item.status === "downloading");
  const hasInstalledModel = lab.catalog.some((model) => model.installed);
  const selectedModel = lab.catalog.find((model) => model.name === lab.selected_model);
  const [workingModel, setWorkingModel] = useState<string | null>(null);
  const [confirmRemoval, setConfirmRemoval] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(
    () => !lab.ollama_reachable || !hasInstalledModel || downloadActive,
  );
  const attentionRequiresExpanded = downloadActive || !lab.ollama_reachable;
  const sectionExpanded = expanded || attentionRequiresExpanded;
  const act = async (model: string, action: "download" | "select" | "remove") => {
    setWorkingModel(model);
    try {
      if (action === "download") await api.pullAiModel(model);
      else if (action === "select") await api.selectAiModel(model);
      else await api.removeAiModel(model);
      resolveIssue("ai");
      await refresh();
    } catch (cause) {
      const title = action === "download"
        ? "Local model download did not start"
        : action === "select"
          ? "Local model was not selected"
          : "Local model was not removed";
      reportIssue("ai", title, cause);
    } finally {
      setWorkingModel(null);
      if (action === "remove") setConfirmRemoval(null);
    }
  };
  return <article className="card settings-card ai-model-manager">
    <div className="ai-lab-heading settings-disclosure-head">
      <SectionHeader title="Local AI models" subtitle="Choose by available RAM; downloads continue while you use the paper lab" />
      <div className="settings-disclosure-actions">
        <span className="settings-section-summary"><Bot size={14} /><span><strong>{selectedModel?.label ?? lab.selected_model}</strong><small>{lab.selected_model_installed ? "Selected model" : "Needs download"}</small></span></span>
        <span className="model-memory">{lab.system_memory_bytes ? `${(lab.system_memory_bytes / 1024 ** 3).toFixed(1)} GB RAM` : "RAM unavailable"}</span>
        {attentionRequiresExpanded
          ? <span className="settings-auto-open">{downloadActive ? "Download active" : "Needs attention"}</span>
          : <button className="button ghost settings-section-toggle" type="button" aria-expanded={sectionExpanded} aria-controls="local-ai-model-settings" aria-label={`${sectionExpanded ? "Hide" : "Show"} local AI models`} onClick={() => setExpanded((value) => !value)}>{sectionExpanded ? "Hide" : "Show"}<ChevronDown size={15} /></button>}
      </div>
    </div>
    {sectionExpanded && <div className="settings-disclosure-body" id="local-ai-model-settings">
      <div className="ai-runtime-strip" aria-label="Local AI runtime status">
        <span className={lab.ollama_reachable ? "positive" : "negative"}>{lab.ollama_reachable ? "Runtime ready" : "Runtime unavailable"}</span>
        <span>{lab.deployment === "bundled" ? "Bundled Docker service" : "External service"}</span>
        <span>{lab.configured_accelerator === "external" ? "External compute" : `${lab.configured_accelerator.toUpperCase()} configured`}</span>
        <span>{lab.runtime_compute === "idle" ? "Idle until needed" : lab.runtime_compute === "unavailable" ? "Not connected" : `${title(lab.runtime_compute)} inference`}</span>
        {lab.ollama_version && <span>Ollama {lab.ollama_version}</span>}
      </div>
      {!lab.ollama_reachable && <p className="provider-warning"><AlertTriangle size={14} />{lab.deployment === "bundled" ? "The bundled AI service is still starting or unavailable. Paper trading continues normally; check the Ollama container if this remains after a minute." : "The configured external Ollama service is unavailable. Paper trading continues normally; restore the bundled connection below or check that server."}</p>}
      {lab.ollama_reachable && !hasInstalledModel && <p className="provider-note"><ShieldCheck size={14} />The private local runtime is ready. Choose a model below; the download continues in the background and is stored separately from trading data.</p>}
      {!selectedIsCurated && <p className="provider-note"><ShieldCheck size={14} />Your existing <strong>{lab.selected_model}</strong> selection remains available for explanations. Choose one of the reviewed models below before using the AI Decision Lab.</p>}
      <div className="ai-model-list">
        {lab.catalog.map((model) => {
          const download = lab.downloads.find((item) => item.model === model.name);
          const downloading = download?.status === "queued" || download?.status === "downloading";
          const selected = lab.selected_model === model.name;
          const busy = workingModel === model.name;
          return <div className={`ai-model-row ${selected ? "selected" : ""}`} key={model.name}>
            <div className="ai-model-copy"><div><strong>{model.label}</strong>{model.role.includes("Recommended") && <span>Recommended</span>}</div><small>{model.role}</small><small>{formatBytes(model.download_bytes)} download · {model.recommended_ram_gb} GB RAM recommended{!model.fits_recommended_ram ? " · above detected RAM" : ""}</small></div>
            {downloading && download && <div className="model-download" role="status"><div><span style={{ width: `${download.progress_fraction * 100}%` }} /></div><small>{download.message} · {percent(download.progress_fraction)}</small></div>}
            {download?.status === "error" && <small className="model-error">{download.error ?? "Download failed"}</small>}
            <div className="ai-model-actions">
              {model.installed ? <>
                {selected ? <span className="model-selected"><Check size={14} />Selected</span> : <button className="button ghost" disabled={busy || downloadActive} onClick={() => void act(model.name, "select")}>Select</button>}
                {confirmRemoval === model.name ? <>
                  <button className="button ghost" disabled={busy} onClick={() => setConfirmRemoval(null)}>Cancel</button>
                  <button className="button danger" disabled={busy || downloadActive} onClick={() => void act(model.name, "remove")}>Remove model</button>
                </> : <button className="button ghost" disabled={busy || downloadActive} onClick={() => setConfirmRemoval(model.name)}>Remove</button>}
              </> : <button className="button ghost" disabled={busy || downloadActive || !lab.ollama_reachable} onClick={() => void act(model.name, "download")}>{downloading ? "Downloading…" : download?.status === "error" ? "Retry" : "Download"}</button>}
            </div>
          </div>;
        })}
      </div>
      <p className="storage-note"><HardDrive size={14} />Model sizes are shown before download. They survive app updates in a separate Docker volume, do not count toward the database limit, and can be removed here when no longer needed.</p>
    </div>}
  </article>;
}

function ProviderManager({ snapshot, refresh, busy, setBusy, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
}) {
  const settings = snapshot.provider_settings;
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [configuration, setConfiguration] = useState<ProviderConfiguration>(() => providerConfiguration(settings));
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [clearSecrets, setClearSecrets] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const solanaPresetId = matchingPreset(configuration.solana, settings.presets.solana);
  const guidedSolana = guidedSolanaProvider(solanaPresetId);
  const guidedSolanaConfigured = guidedSolana
    ? solanaProviderMatches(settings.providers.solana, guidedSolana)
    : false;
  const attentionRequiresExpanded = Boolean(settings.secret_store_error);
  const sectionExpanded = expanded || attentionRequiresExpanded;

  const setPolicy = (provider: keyof ProviderConfiguration, policy: ProviderPolicy) => {
    setSavedMessage(null);
    setConfiguration((current) => ({ ...current, [provider]: policy }));
  };
  const applyPreset = (provider: "solana" | "jupiter", presetId: string) => {
    if (presetId === "custom") {
      setSavedMessage(null);
      setConfiguration((current) => ({
        ...current,
        [provider]: {
          ...current[provider],
          label: provider === "solana" ? "Custom RPC" : "Custom plan",
        },
      }));
      return;
    }
    const preset = settings.presets[provider]?.find((item) => item.id === presetId);
    if (!preset) return;
    setPolicy(provider, policyFromPreset(preset));
  };
  const toggleClear = (keys: string[], checked: boolean) => {
    setSavedMessage(null);
    setClearSecrets((current) => checked
      ? [...new Set([...current, ...keys])]
      : current.filter((key) => !keys.includes(key)));
  };
  const toggleEditor = () => {
    setSavedMessage(null);
    if (!editing) {
      setConfiguration(providerConfiguration(settings));
      setSecretValues({});
      setClearSecrets([]);
    }
    setEditing((value) => !value);
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setSavedMessage(null);
    setBusy(true);
    const solanaApiKey = secretValues.solana_api_key;
    const secrets: ProviderSettingsUpdate["secrets"] = { clear: [] };
    const storedSecretKeys = [
      "solana_http",
      "solana_ws",
      "jupiter_base",
      "jupiter_api_key",
      "ollama_url",
      "ollama_model",
    ] as const;
    for (const key of storedSecretKeys) {
      const value = secretValues[key]?.trim();
      if (value) secrets[key] = value;
    }
    const effectiveClear = new Set(clearSecrets);
    if (solanaPresetId === "public") {
      effectiveClear.add("solana_http");
      effectiveClear.add("solana_ws");
    }
    if (guidedSolana && solanaApiKey?.trim()) {
      const endpoints = guidedSolanaEndpoints(guidedSolana, solanaApiKey);
      secrets.solana_http = endpoints.http;
      secrets.solana_ws = endpoints.ws;
      effectiveClear.delete("solana_http");
      effectiveClear.delete("solana_ws");
    }
    secrets.clear = [...effectiveClear] as ProviderSettingsUpdate["secrets"]["clear"];
    const body: ProviderSettingsUpdate = { configuration, secrets };
    try {
      const result = await api.updateProviderSettings(body);
      resolveIssue("providers");
      setSecretValues({});
      setClearSecrets([]);
      setEditing(false);
      setSavedMessage(result.paper_engine_stopped
        ? "Providers saved. The paper engine stopped safely for the source change."
        : "Provider settings saved.");
      void refresh();
    } catch (cause) {
      reportIssue("providers", "Provider settings were not saved", cause);
    } finally {
      setSaving(false);
      setBusy(false);
    }
  };

  return <article className="card settings-card provider-manager">
    <div className="provider-heading settings-disclosure-head">
      <SectionHeader title="Data providers" subtitle="Each adapter's exact role, activity and call budget" />
      <div className="settings-disclosure-actions">
        <span className="settings-section-summary"><Radio size={14} /><span><strong>Solana {settings.providers.solana.active ? "live" : "idle"}</strong><small>{Object.keys(settings.providers).length} adapters configured</small></span></span>
        {sectionExpanded && <button className="button ghost" type="button" disabled={saving} aria-expanded={editing} onClick={toggleEditor}><KeyRound size={15} />{editing ? "Close" : "Manage"}</button>}
        {attentionRequiresExpanded
          ? <span className="settings-auto-open">Needs attention</span>
          : <button className="button ghost settings-section-toggle" type="button" aria-expanded={sectionExpanded} aria-controls="data-provider-settings" aria-label={`${sectionExpanded ? "Hide" : "Show"} data providers`} onClick={() => setExpanded((value) => !value)}>{sectionExpanded ? "Hide" : "Show"}<ChevronDown size={15} /></button>}
      </div>
    </div>
    {sectionExpanded && <div className="settings-disclosure-body" id="data-provider-settings">
      {settings.secret_store_error && <p className="provider-warning"><AlertTriangle size={14} />{settings.secret_store_error}</p>}
      {savedMessage && <p className="provider-saved" role="status"><Check size={14} />{savedMessage}</p>}
      <div className="provider-list">
        {Object.entries(settings.providers).map(([name, provider]) => {
          const quota = snapshot.quotas[name];
          return <div className="provider-row" key={name}>
            <div><strong>{title(name)}</strong><small>{providerRole(name)} · {provider.policy.label} · {provider.endpoint}</small></div>
            <div><span className={provider.active ? "provider-active" : "provider-idle"}>{providerActivity(name, provider.active)}</span><small>{quota ? providerQuotaCopy(quota) : "No external calls"}</small></div>
          </div>;
        })}
      </div>
      <p className="provider-note"><ShieldCheck size={14} />{settings.notes.pump} Monthly plans are paced so routine HTTP calls cannot burn the allowance early. {settings.notes.streaming}</p>
      {editing && <form className="provider-form" onSubmit={save}>
      <ProviderEditor title="Solana RPC" copy="The live program stream plus one mint-safety lookup per newly observed candidate.">
        <label>RPC service<select value={solanaPresetId} onChange={(event) => applyPreset("solana", event.target.value)}>{settings.presets.solana?.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}<option value="custom">Custom RPC or limits</option></select></label>
        {guidedSolana && <SecretInput
          label={`${guidedSolana.name} API key`}
          value={secretValues.solana_api_key ?? ""}
          placeholder={guidedSolanaConfigured ? "Saved securely · blank keeps it" : `Paste your ${guidedSolana.name} key`}
          required={!guidedSolanaConfigured}
          onChange={(value) => { setSavedMessage(null); setSecretValues((current) => ({ ...current, solana_api_key: value })); }}
        />}
        {solanaPresetId === "public" && <p className="provider-connection-guide">No key required. Saving restores the configured environment endpoint or the bundled public Solana endpoint.</p>}
        {guidedSolana && <p className="provider-connection-guide">Signal Arcade creates the secure HTTP and WebSocket URLs automatically. The key remains write-only.</p>}
        {solanaPresetId === "custom" && <>
          <SecretInput label="HTTP RPC URL" value={secretValues.solana_http ?? ""} placeholder={`${settings.providers.solana.endpoint} · blank keeps saved value`} onChange={(value) => { setSavedMessage(null); setSecretValues((current) => ({ ...current, solana_http: value })); }} />
          <SecretInput label="WebSocket URL" value={secretValues.solana_ws ?? ""} placeholder={`${settings.providers.solana.stream_endpoint ?? "Saved stream"} · blank keeps saved value`} onChange={(value) => { setSavedMessage(null); setSecretValues((current) => ({ ...current, solana_ws: value })); }} />
          <PolicyInputs policy={configuration.solana} onChange={(policy) => setPolicy("solana", policy)} />
          <label className="provider-check"><input type="checkbox" checked={clearSecrets.includes("solana_http") && clearSecrets.includes("solana_ws")} onChange={(event) => toggleClear(["solana_http", "solana_ws"], event.target.checked)} />Restore environment/default RPC endpoints</label>
        </>}
        {solanaPresetId !== "custom" && <p className="provider-preset-summary">Automatic limits: {configuration.solana.requests_per_minute.toLocaleString()}/min{configuration.solana.monthly_limit ? ` · ${configuration.solana.monthly_limit.toLocaleString()} monthly HTTP cap` : " · no app-level monthly cap"}</p>}
      </ProviderEditor>
      <ProviderEditor title="DEX Screener" copy="Keyless secondary USD and liquidity context. It never replaces the core on-chain feed.">
        <PolicyInputs policy={configuration.dexscreener} onChange={(policy) => setPolicy("dexscreener", policy)} />
      </ProviderEditor>
      <ProviderEditor title="Jupiter" copy="Optional validation adapter. V1 paper fills do not call Jupiter automatically.">
        <label>Plan<select value={matchingPreset(configuration.jupiter, settings.presets.jupiter)} onChange={(event) => applyPreset("jupiter", event.target.value)}>{settings.presets.jupiter?.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}<option value="custom">Custom limits</option></select></label>
        <SecretInput label="API key" value={secretValues.jupiter_api_key ?? ""} placeholder={settings.providers.jupiter.api_key_configured ? "Saved on the local server · blank keeps it" : "Optional"} onChange={(value) => { setSavedMessage(null); setSecretValues((current) => ({ ...current, jupiter_api_key: value })); }} />
        <PolicyInputs policy={configuration.jupiter} onChange={(policy) => setPolicy("jupiter", policy)} />
        <label className="provider-check"><input type="checkbox" checked={clearSecrets.includes("jupiter_api_key")} onChange={(event) => toggleClear(["jupiter_api_key"], event.target.checked)} />Remove saved Jupiter key</label>
      </ProviderEditor>
      <ProviderEditor title="Local AI connection" copy="Docker uses the private bundled Ollama service automatically. Only set an override when you deliberately want another local Ollama server.">
        <SecretInput label="External Ollama URL override" value={secretValues.ollama_url ?? ""} placeholder={`${settings.providers.ollama.endpoint} · blank keeps the current connection`} onChange={(value) => { setSavedMessage(null); setSecretValues((current) => ({ ...current, ollama_url: value })); }} />
        <PolicyInputs policy={configuration.ollama} onChange={(policy) => setPolicy("ollama", policy)} />
        <label className="provider-check"><input type="checkbox" checked={clearSecrets.includes("ollama_url")} onChange={(event) => toggleClear(["ollama_url"], event.target.checked)} />Restore bundled/environment Ollama connection</label>
      </ProviderEditor>
      <div className="provider-save"><p>Keys are write-only and never returned to the browser. New secret values require HTTPS or opening this page on localhost. Saving a new Solana stream stops the paper engine and cancels pending orders safely.</p><button className="button" type="submit" disabled={saving || busy} aria-live="polite">{saving ? <span className="mini-loader" /> : <Save size={15} />}{saving ? "Saving…" : "Save providers"}</button></div>
      </form>}
    </div>}
  </article>;
}

function ProviderEditor({ title: heading, copy, children }: { title: string; copy: string; children: React.ReactNode }) {
  return <fieldset className="provider-editor"><legend>{heading}</legend><p>{copy}</p><div className="provider-fields">{children}</div></fieldset>;
}

function SecretInput({ label, value, placeholder, required = false, onChange }: { label: string; value: string; placeholder: string; required?: boolean; onChange: (value: string) => void }) {
  return <label>{label}<input type="password" autoComplete="off" value={value} placeholder={placeholder} required={required} onChange={(event) => onChange(event.target.value)} /></label>;
}

function PolicyInputs({ policy, onChange }: { policy: ProviderPolicy; onChange: (policy: ProviderPolicy) => void }) {
  return <>
    <label>Requests per minute<input type="number" min="1" max="60000" value={policy.requests_per_minute} onChange={(event) => onChange({ ...policy, requests_per_minute: Number(event.target.value) })} /></label>
    <label>Monthly hard cap<input type="number" min="1" max="2000000000" value={policy.monthly_limit ?? ""} placeholder="No monthly cap" onChange={(event) => onChange({ ...policy, monthly_limit: event.target.value ? Number(event.target.value) : null })} /></label>
    <label className="provider-check"><input type="checkbox" checked={policy.paid_mode} onChange={(event) => onChange({ ...policy, paid_mode: event.target.checked })} />Paid plan enabled</label>
  </>;
}

function providerConfiguration(settings: Snapshot["provider_settings"]): ProviderConfiguration {
  return {
    solana: { ...settings.providers.solana.policy },
    dexscreener: { ...settings.providers.dexscreener.policy },
    jupiter: { ...settings.providers.jupiter.policy },
    ollama: { ...settings.providers.ollama.policy },
  };
}

function policyFromPreset(preset: ProviderPreset): ProviderPolicy {
  return { label: preset.label, requests_per_minute: preset.requests_per_minute, monthly_limit: preset.monthly_limit, reserve_fraction: 0.1, paid_mode: preset.paid_mode };
}

function matchingPreset(policy: ProviderPolicy, presets: ProviderPreset[] | undefined): string {
  return presets?.find((preset) => preset.label === policy.label && preset.requests_per_minute === policy.requests_per_minute && preset.monthly_limit === policy.monthly_limit && preset.paid_mode === policy.paid_mode)?.id ?? "custom";
}

interface GuidedSolanaProvider {
  name: string;
  httpHost: string;
  wsHost: string;
  httpTemplate: (encodedKey: string) => string;
  wsTemplate: (encodedKey: string) => string;
}

const GUIDED_SOLANA_PROVIDERS: Record<string, GuidedSolanaProvider> = {
  helius_free: {
    name: "Helius",
    httpHost: "https://mainnet.helius-rpc.com",
    wsHost: "wss://mainnet.helius-rpc.com",
    httpTemplate: (key) => `https://mainnet.helius-rpc.com/?api-key=${key}`,
    wsTemplate: (key) => `wss://mainnet.helius-rpc.com/?api-key=${key}`,
  },
  alchemy_free: {
    name: "Alchemy",
    httpHost: "https://solana-mainnet.g.alchemy.com",
    wsHost: "wss://solana-mainnet.g.alchemy.com",
    httpTemplate: (key) => `https://solana-mainnet.g.alchemy.com/v2/${key}`,
    wsTemplate: (key) => `wss://solana-mainnet.g.alchemy.com/v2/${key}`,
  },
  solanatracker_rpc_free: {
    name: "SolanaTracker RPC",
    httpHost: "https://rpc-mainnet.solanatracker.io",
    wsHost: "wss://rpc-mainnet.solanatracker.io",
    httpTemplate: (key) => `https://rpc-mainnet.solanatracker.io?api_key=${key}`,
    wsTemplate: (key) => `wss://rpc-mainnet.solanatracker.io?api_key=${key}`,
  },
};

function guidedSolanaProvider(presetId: string): GuidedSolanaProvider | null {
  return GUIDED_SOLANA_PROVIDERS[presetId] ?? null;
}

function solanaProviderMatches(provider: Snapshot["provider_settings"]["providers"]["solana"], guided: GuidedSolanaProvider): boolean {
  return provider.endpoint === guided.httpHost && provider.stream_endpoint === guided.wsHost;
}

function guidedSolanaEndpoints(guided: GuidedSolanaProvider, apiKey: string): { http: string; ws: string } {
  const encodedKey = encodeURIComponent(apiKey.trim());
  return { http: guided.httpTemplate(encodedKey), ws: guided.wsTemplate(encodedKey) };
}

function providerRole(name: string): string {
  if (name === "solana") return "Core on-chain stream + mint safety";
  if (name === "dexscreener") return "Secondary USD + liquidity context";
  if (name === "jupiter") return "Validation adapter; idle in V1";
  if (name === "ollama") return "On-demand explanations only";
  return "Optional adapter";
}

function providerActivity(name: string, active: boolean): string {
  if (name === "jupiter") return "Idle in V1";
  if (name === "ollama") return active ? "On demand" : "Optional";
  return active ? "In use" : "Optional";
}

function providerQuotaCopy(quota: Snapshot["quotas"][string]): string {
  const projection = quota.monthly_limit ? `${compact(quota.projected_monthly_calls)} / ${compact(quota.monthly_limit)} projected` : `${compact(quota.projected_monthly_calls)} projected`;
  const rate = quota.monthly_pacing && quota.effective_requests_per_minute < quota.requests_per_minute ? `${quota.effective_requests_per_minute.toFixed(1)}/min paced` : `${quota.requests_per_minute}/min`;
  return `${projection} · ${rate}`;
}

function DecisionRow({ decision, explain, loading }: { decision: Decision; explain: (decision: Decision) => Promise<void>; loading: boolean }) {
  const tokenLabel = tokenDisplayLabel(decision.symbol, decision.mint);
  return <article className="decision-row"><button className="decision-row-explain" onClick={() => void explain(decision)} disabled={loading} aria-busy={loading} aria-label={`Explain ${tokenLabel} decision`}><ActionBadge action={decision.action} label={decisionActionLabel(decision.action)} /><span className="decision-token"><strong title={tokenSymbolKnown(decision.symbol) ? undefined : decision.mint}>{tokenLabel}</strong><small>{decision.reasons[0] ?? "Evidence checkpoint"}</small></span><ScoreRing score={decision.score.composite} />{loading ? <span className="mini-loader" /> : <ChevronRight size={17} />}</button><MintActions mint={decision.mint} symbol={decision.symbol} compact /></article>;
}

function DecisionBoardRow({ decision, explain, loading, expanded, toggleDetails, rank, viewAsOfMs }: {
  decision: Decision;
  explain: (decision: Decision) => Promise<void>;
  loading: boolean;
  expanded: boolean;
  toggleDetails: (decision: Decision) => void;
  rank?: number;
  viewAsOfMs: number;
}) {
  const noBlockerCopy = decision.action === "enter"
    ? "All configured safety gates passed for this paper signal."
    : decision.action === "watch"
      ? "Waiting for the paper-entry threshold."
      : "No additional blocker was recorded.";
  const detailsId = `decision-details-${decision.decision_id}`;
  const tokenLabel = tokenDisplayLabel(decision.symbol, decision.mint);

  return <article className={`decision-board-row ${expanded ? "expanded" : ""}`}>
    <div className="decision-board-main">
      <div className="decision-board-token">
        <div><ActionBadge action={decision.action} label={decisionActionLabel(decision.action)} />{rank && <span className="decision-rank">#{rank} now</span>}</div>
        <strong title={tokenSymbolKnown(decision.symbol) ? undefined : decision.mint}>{tokenLabel}</strong>
        <small>{ago(decision.created_at)} · {decision.model_version}</small>
      </div>
      <p className="decision-board-reason">{decision.reasons[0] ?? "No positive evidence recorded."}</p>
      <div className="decision-board-metrics" aria-label={`${tokenLabel} decision summary`}>
        <span><strong>{decision.score.composite}</strong><small>Score</small></span>
        <span><strong>{percent(decision.score.confidence)}</strong><small>Data confidence</small></span>
        <span className={decision.score.net_edge_index >= 0 ? "positive" : "negative"}><strong>{percentSigned(decision.score.net_edge_index)}</strong><small>Edge index</small></span>
      </div>
      <div className="decision-board-actions">
        <MintActions mint={decision.mint} symbol={decision.symbol} compact />
        <button className="quick-explain" onClick={() => void explain(decision)} disabled={loading} aria-busy={loading} aria-label={`Explain ${tokenLabel} decision`}>
          {loading ? <span className="mini-loader" /> : <Sparkles size={15} />}<span>{loading ? "Explaining…" : "Explain"}</span>
        </button>
        <button className="details-toggle" onClick={() => toggleDetails(decision)} aria-expanded={expanded} aria-controls={detailsId} aria-label={`Review ${tokenLabel} decision details`}>
          <span>Details</span><ChevronDown size={15} />
        </button>
      </div>
    </div>
    {expanded && <div id={detailsId} className="decision-board-details">
      <div className="score-bars"><ScoreBar label="Opportunity" value={decision.score.opportunity} tone="good" /><ScoreBar label="Danger" value={decision.score.danger} tone="bad" /><ScoreBar label="Execution" value={decision.score.execution} tone="blue" /><ScoreBar label="Data confidence" value={decision.score.confidence} tone="purple" /></div>
      <p className="model-note">Experimental transparent heuristic · the edge index ranks evidence after estimated friction; it is not a profit forecast.</p>
      {decision.learning_assessment && <p className={`learning-decision-note ${decision.learning_assessment.applied ? "applied" : "shadow"}`}><GraduationCap size={14} /><span><strong>{decision.learning_assessment.applied ? "Proven learner applied" : "Shadow learner"}</strong> · predicted {percentSigned(decision.learning_assessment.predicted_net_return)}, conservative {percentSigned(decision.learning_assessment.conservative_net_return)} after validation uncertainty.</span></p>}
      <div className="decision-copy">
        <div><strong>Evidence</strong>{decision.reasons.length ? decision.reasons.map((reason, index) => <p key={`${index}-${reason}`}>• {reason}</p>) : <p>• No positive evidence recorded.</p>}</div>
        <div><strong>{decision.blockers.length ? "Why it did not enter" : "Risk result"}</strong>{decision.blockers.length ? decision.blockers.map((blocker, index) => <p key={`${index}-${blocker}`}>• {decisionBlockerCopy(blocker, decision, viewAsOfMs)}</p>) : <p>• {noBlockerCopy}</p>}</div>
      </div>
      <ResearchHandoff mint={decision.mint} symbol={decision.symbol} />
    </div>}
  </article>;
}

function MintActions({ mint, symbol, compact = false }: { mint: string; symbol: string; compact?: boolean }) {
  const [copyStatus, setCopyStatus] = useState<"copied" | "failed" | null>(null);
  const tokenLabel = tokenDisplayLabel(symbol, mint);
  const copyMint = async () => {
    setCopyStatus(await copyText(mint) ? "copied" : "failed");
  };
  return <span className={`mint-actions ${compact ? "compact" : ""}`} aria-label={`${tokenLabel} token research actions`}>
    <button type="button" onClick={() => void copyMint()} title={mint} aria-label={`Copy ${tokenLabel} mint address`}>{copyStatus === "copied" ? <Check size={13} /> : <Copy size={13} />}<span>{copyStatus === "copied" ? "Copied" : copyStatus === "failed" ? "Blocked" : "Mint"}</span></button>
    <a href={gmgnTokenUrl(mint)} target="_blank" rel="noopener noreferrer" aria-label={`Open ${tokenLabel} on GMGN`} title={`Research ${mint} on GMGN`}><ExternalLink size={13} /><span>GMGN</span></a>
  </span>;
}

function ResearchHandoff({ mint, symbol }: { mint: string; symbol: string }) {
  const [copyStatus, setCopyStatus] = useState<"copied" | "failed" | null>(null);
  const tokenLabel = tokenDisplayLabel(symbol, mint);
  const copyMint = async () => {
    setCopyStatus(await copyText(mint) ? "copied" : "failed");
  };
  return <section className="research-handoff" aria-label={`${tokenLabel} research handoff`}>
    <div><strong>Research handoff</strong><small>Copy the exact mint or inspect the same token independently on GMGN.</small></div>
    <div className="mint-copy"><input readOnly value={mint} aria-label={`${tokenLabel} mint address`} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copyMint()}>{copyStatus === "copied" ? <Check size={15} /> : <Copy size={15} />}{copyStatus === "copied" ? "Copied" : "Copy mint"}</button><a href={gmgnTokenUrl(mint)} target="_blank" rel="noopener noreferrer" aria-label={`Open ${tokenLabel} on GMGN`}><ExternalLink size={15} />Open GMGN</a></div>
    {copyStatus === "failed" && <small className="copy-failed" role="status">Clipboard access is blocked here—select the address above.</small>}
    <p>Signal ≠ fill. GMGN is an external research/trading site; opening it never places a trade from Signal Arcade.</p>
  </section>;
}

function TokenCard({ token }: { token: FeatureSnapshot }) {
  const values = token.values;
  const [copyStatus, setCopyStatus] = useState<"copied" | "failed" | null>(null);
  const symbolKnown = Boolean(token.symbol.trim() && token.symbol !== "?");
  const nameKnown = Boolean(token.name.trim() && token.name !== "Unknown token");
  const identityIncomplete = !symbolKnown || !nameKnown;
  const identitySource = values.identity_source?.value;
  const secondaryIdentity = typeof identitySource === "string" && identitySource.includes("dexscreener");
  const copyMint = async () => {
    setCopyStatus(await copyText(token.mint) ? "copied" : "failed");
  };
  return <article className="card token-card">
    <div className="token-identity">
      <span className="token-dot" />
      <strong>{symbolKnown ? token.symbol : shortMint(token.mint)}</strong>
      <small>{nameKnown ? token.name : "Name unavailable"}{secondaryIdentity && <em>DEX display label</em>}</small>
      {identityIncomplete && <button className="token-mint-copy" type="button" title={token.mint} aria-label={`Copy ${token.mint} mint address`} onClick={() => void copyMint()}>{copyStatus === "copied" ? <Check size={13} /> : <Copy size={13} />}<span>{copyStatus === "copied" ? "Copied" : copyStatus === "failed" ? "Copy blocked" : "Mint"}</span></button>}
    </div>
    <div className="token-score"><strong>{Math.round(token.data_confidence * 100)}%</strong><span>Market data confidence</span></div>
    <dl><div><dt>Trades 1m</dt><dd>{String(values.trade_count_1m?.value ?? "—")}</dd></div><div><dt>Buy ratio</dt><dd>{typeof values.buy_ratio_5m?.value === "number" ? percent(values.buy_ratio_5m.value) : "—"}</dd></div><div><dt>Curve</dt><dd>{typeof values.curve_progress?.value === "number" ? percent(values.curve_progress.value) : "—"}</dd></div></dl>
    {token.hard_flags.length > 0 && <span className="flag-line">{humanize(token.hard_flags[0]!)}</span>}
  </article>;
}

function PositionCard({ position, currency, decimals }: { position: Position; currency: QuoteCurrency; decimals: number }) {
  const fraction = position.entry_cost_lamports ? position.unrealized_pnl_lamports / position.entry_cost_lamports : 0;
  const assessment = position.exit_assessment;
  const policy = assessment
    ? `${humanize(assessment.reason)}${assessment.action === "hold" ? ` · ${Math.round(assessment.support_score * 100)}% support` : ""}`
    : null;
  const statusCopy = position.market_status === "active"
    ? position.mark_age_seconds !== null ? `marked ${duration(position.mark_age_seconds)} ago` : "verified route"
    : position.market_status === "exit_blocked"
      ? `indicative only · ${humanize(position.mark_blockers[0] ?? "exit route unavailable")}`
      : "last known · waiting for a fresh market";
  const valueKind = position.market_status === "active" ? "" : position.market_status === "exit_blocked" ? " indicative" : " last known";
  const tokenLabel = tokenDisplayLabel(position.symbol, position.mint);
  return <article className={`card position-card ${position.market_status}`}><div className="position-identity"><span className="token-dot" /><strong title={tokenSymbolKnown(position.symbol) ? undefined : position.mint}>{tokenLabel}</strong><small>Opened {ago(position.opened_at)} · {statusCopy}{policy ? ` · ${policy}` : ""}</small><MintActions mint={position.mint} symbol={position.symbol} compact /></div><div className="position-value"><strong>{money(position.last_mark_lamports, currency, decimals)}</strong><span className={fraction >= 0 ? "positive" : "negative"}>{percentSigned(fraction)}{valueKind}</span></div></article>;
}

function FillRow({ fill }: { fill: Fill }) {
  const fees = fill.account_protocol_fee_minor + fill.account_network_fee_minor;
  const exitReason = fill.assumptions.find((item) => item.startsWith("scheduled_reason:"))?.slice(17);
  const tokenLabel = tokenDisplayLabel(fill.symbol, fill.mint);
  return <div className="fill-row" role="row"><span>{new Date(fill.filled_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span><span><strong title={tokenSymbolKnown(fill.symbol) ? undefined : fill.mint}>{tokenLabel}</strong><small>{fill.venue}{exitReason ? ` · ${humanize(exitReason)}` : fill.sol_usd_price ? ` · SOL $${fill.sol_usd_price.toFixed(2)}` : ""}</small></span><span><ActionBadge action={fill.side === "buy" ? "enter" : "pass"} label={fill.side} /></span><span>{money(fill.account_net_minor, fill.account_currency, fill.account_decimals)}</span><span>{money(fees, fill.account_currency, fill.account_decimals)}</span><span>{percent(fill.price_impact_fraction)}</span><span>{fill.latency_ms.toLocaleString()}ms</span></div>;
}

function EquityChart({ points, tall = false }: { points: EquityPoint[]; tall?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [view, setView] = useState<"journey" | "time">("journey");
  const journey = useMemo(() => buildEquityJourney(points), [points]);
  const displayPoints = view === "journey" ? journey : points;
  const unchangedSeconds = unchangedEquitySeconds(points);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(devicePixelRatio, 2);
      canvas.width = Math.max(1, rect.width * ratio);
      canvas.height = Math.max(1, rect.height * ratio);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, rect.width, rect.height);
      const data = displayPoints.length ? displayPoints : [{ recorded_at: "", equity_lamports: 0, cash_lamports: 0 }];
      const values = data.map((point) => point.equity_lamports);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const flat = max === min;
      const range = Math.max(1, max - min);
      const pad = 8;
      const timestamps = data.map((point) => Date.parse(point.recorded_at));
      const firstTime = Math.min(...timestamps);
      const lastTime = Math.max(...timestamps);
      const useTime = view === "time" && timestamps.every(Number.isFinite) && lastTime > firstTime;
      let coords = data.map((point, index) => ({
        x: pad + (useTime ? (timestamps[index]! - firstTime) / (lastTime - firstTime) : index / Math.max(1, data.length - 1)) * (rect.width - pad * 2),
        y: flat ? rect.height / 2 : pad + (1 - (point.equity_lamports - min) / range) * (rect.height - pad * 2),
      }));
      if (coords.length === 1) coords = [{ x: pad, y: coords[0]!.y }, { x: rect.width - pad, y: coords[0]!.y }];
      const gradient = ctx.createLinearGradient(0, 0, 0, rect.height);
      gradient.addColorStop(0, "rgba(98, 91, 255, .28)");
      gradient.addColorStop(1, "rgba(98, 91, 255, 0)");
      ctx.beginPath();
      ctx.moveTo(coords[0]!.x, rect.height);
      coords.forEach((point) => ctx.lineTo(point.x, point.y));
      ctx.lineTo(coords.at(-1)!.x, rect.height);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.beginPath();
      coords.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
      ctx.strokeStyle = "#7b74ff";
      ctx.lineWidth = 2;
      ctx.stroke();
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [displayPoints, view]);
  const plateau = unchangedSeconds >= 60 ? ` · unchanged for ${duration(unchangedSeconds)}` : "";
  return <div className="equity-chart-shell">
    <div className="equity-chart-toolbar"><small>{view === "journey" ? `${journey.length} meaningful equity moves${plateau}` : "True elapsed-time spacing"}</small><div role="group" aria-label="Equity chart spacing"><button className={view === "journey" ? "active" : ""} aria-pressed={view === "journey"} onClick={() => setView("journey")}>Journey</button><button className={view === "time" ? "active" : ""} aria-pressed={view === "time"} onClick={() => setView("time")}>Real time</button></div></div>
    <canvas ref={ref} className={`equity-chart ${tall ? "tall" : ""}`} role="img" aria-label={`Paper equity ${view === "journey" ? "season journey with unchanged checkpoints collapsed" : "history spaced by elapsed time"}. ${points.length} recorded checkpoints.`}>Paper equity history</canvas>
  </div>;
}

function HealthRows({ health }: { health: Record<string, unknown> }) { return <div className="health-rows">{Object.entries(health).filter(([, value]) => typeof value !== "object").map(([key, value]) => <div key={key}><span>{humanize(key)}</span><strong>{formatHealthValue(key, value)}</strong></div>)}</div>; }
function ScoreBar({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className="score-bar"><div><span>{label}</span><strong>{percent(value)}</strong></div><div className={`bar ${tone}`}><span style={{ width: `${Math.max(2, value * 100)}%` }} /></div></div>; }
function ScoreRing({ score }: { score: number }) { return <span className="score-ring" style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}><strong>{score}</strong><small>/100</small></span>; }
function ActionBadge({ action, label }: { action: DecisionAction; label?: string }) { return <span className={`action-badge ${action}`}>{label ?? action}</span>; }
function SectionHeader({ title: heading, subtitle }: { title: string; subtitle: string }) { return <div className="section-header"><div><h2>{heading}</h2><p>{subtitle}</p></div></div>; }
function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) { return <article className="card stat-card"><span>{label}</span><strong className={tone}>{value}</strong>{hint && <small>{hint}</small>}</article>; }
function EmptyState({ icon, title: heading, copy }: { icon: React.ReactNode; title: string; copy: string }) { return <div className="empty-state">{icon}<div><strong>{heading}</strong><p>{copy}</p></div></div>; }
function NavButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) { return <button className={active ? "active" : ""} aria-label={label} aria-current={active ? "page" : undefined} onClick={onClick}>{icon}<span>{label}</span></button>; }
function LoadingState() { return <div className="loading-state"><span className="loader" /><strong>Starting the arcade…</strong><p>Checking the ledger and connecting to the selected market source.</p></div>; }

function money(value: number, currency: QuoteCurrency, decimals: number) { const scale = 10 ** decimals; const amount = value / scale; return currency === "USDC" ? `${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC` : `${amount.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 5 })} SOL`; }
function signedMoney(value: number, currency: QuoteCurrency, decimals: number) { return `${value >= 0 ? "+" : "−"}${money(Math.abs(value), currency, decimals)}`; }
function percent(value: number) { return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`; }
function percentSigned(value: number) { return `${value >= 0 ? "+" : "−"}${percent(Math.abs(value))}`; }
function compact(value: number) { return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value); }
function formatHealthValue(key: string, value: unknown) {
  if (value === null) return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && key.endsWith("_at")) {
    const timestamp = Date.parse(value);
    if (Number.isFinite(timestamp)) return new Date(timestamp).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
  }
  if (typeof value === "number" && key.endsWith("_seconds")) return duration(value);
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (typeof value === "string" && key.includes("reason")) return humanize(value);
  return String(value);
}
function duration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3_600)}h ${Math.floor((seconds % 3_600) / 60)}m`;
}
function longDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 86_400) return duration(seconds);
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  return `${days}d ${hours}h`;
}
function shortDate(value: string) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : "Unknown date";
}
function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toFixed(unit >= 3 ? 2 : unit === 0 ? 0 : 1)} ${units[unit]}`;
}
function formatEvidence(value: unknown, format: "duration" | "number" | "percent" | "signedPercent" | "sol" | "boolean") {
  if (value === null || value === undefined) return "Unknown";
  if (format === "boolean") return value === true ? "Verified" : value === false ? "Failed" : "Unknown";
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unknown";
  if (format === "duration") return duration(value);
  if (format === "percent") return percent(value);
  if (format === "signedPercent") return percentSigned(value);
  if (format === "sol") return `${value.toLocaleString(undefined, { maximumFractionDigits: 3 })} SOL`;
  return value.toLocaleString();
}
function decisionBlockerCopy(blocker: string, decision: Decision, viewAsOfMs: number) {
  if (blocker !== "needs_at_least_15_seconds_of_history") return humanize(blocker);
  const recordedAge = decision.feature_snapshot.values.age_seconds?.value;
  const elapsed = Math.max(0, (viewAsOfMs - safeDateMs(decision.created_at)) / 1_000);
  const currentAge = (typeof recordedAge === "number" ? recordedAge : 0) + elapsed;
  return currentAge >= 15
    ? "At this checkpoint, the token needed 15 seconds of history. That time gate has since matured; a fresh event will re-evaluate it."
    : `At this checkpoint, the token still needed about ${Math.max(1, Math.ceil(15 - currentAge))} seconds of history.`;
}
function shortMint(value: string) { return value.length <= 12 ? value : `${value.slice(0, 6)}…${value.slice(-4)}`; }
function tokenSymbolKnown(symbol: string) { const value = symbol.trim(); return Boolean(value && value !== "?" && value.toLowerCase() !== "unknown token"); }
function tokenDisplayLabel(symbol: string, mint: string) { return tokenSymbolKnown(symbol) ? symbol.trim() : shortMint(mint); }
function gmgnTokenUrl(mint: string) { return `https://gmgn.ai/sol/token/${encodeURIComponent(mint)}`; }
function safeDateMs(value: string) { const timestamp = Date.parse(value); return Number.isFinite(timestamp) ? timestamp : Date.now(); }
function aiFailureLabel(reason: string | null) {
  const normalized = (reason ?? "").toLowerCase();
  if (normalized.includes("timed_out") || normalized.includes("timeout")) return "Timed out";
  if (normalized.includes("rate") || normalized.includes("busy")) return "Deferred";
  return "Unavailable";
}
function aiFailureDetail(reason: string | null) {
  const label = aiFailureLabel(reason);
  if (label === "Timed out") return "The local model missed its bounded time budget; this assessment was ignored.";
  if (label === "Deferred") return "The local model was busy; the deterministic engine continued without this assessment.";
  return "The optional local model was unavailable; the deterministic engine continued unchanged.";
}
function title(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function humanize(value: string) { return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()); }
function decisionActionLabel(action: DecisionAction) { return action === "enter" ? "Paper enter" : action === "watch" ? "Watching" : action === "pass" ? "Passed" : "Abstained"; }
function ago(value: string) { const timestamp = Date.parse(value); if (!Number.isFinite(timestamp)) return "time unknown"; const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000)); if (seconds < 60) return `${seconds}s ago`; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; return `${Math.floor(seconds / 3600)}h ago`; }
function riskCopy(mode: RiskMode) { return mode === "safe" ? "Waits for stronger evidence and keeps virtual positions small." : mode === "balanced" ? "Balances opportunity, confidence, execution cost and danger." : "Explores more uncertain opportunities inside permanent hard limits."; }
