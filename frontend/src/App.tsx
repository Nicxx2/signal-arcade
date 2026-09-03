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
  DrawdownPolicy,
  ChallengerChampionEvent,
  EquityPoint,
  FeatureSnapshot,
  Fill,
  LearningMode,
  Leaderboard as LeaderboardData,
  MaintenanceOperation,
  PaperSeason,
  Position,
  ProfileTransitionStrategy,
  ProviderConfiguration,
  ProviderPolicy,
  ProviderPreset,
  ProviderSettingsUpdate,
  ProviderView,
  QuoteCurrency,
  ReadinessGate,
  RiskMode,
  SeasonAutomation,
  SeasonProfile,
  SeasonOperation,
  Seasons as SeasonsData,
  Snapshot,
  AiDecisionMode,
} from "./types";

type Tab = "arena" | "decisions" | "leaderboard" | "learning" | "replay" | "settings";
const RISK_MODES: RiskMode[] = ["safe", "balanced", "aggressive"];
const EXPECTED_RESTART_KEY = "signal-arcade-expected-restart-until";
const DISMISSED_MAINTENANCE_NOTICE_KEY = "signal-arcade-dismissed-maintenance-notice-v1";
const MAINTENANCE_NOTICE_MAX_AGE_MS = 24 * 60 * 60 * 1_000;
const MAINTENANCE_NOTICE_FUTURE_TOLERANCE_MS = 5 * 60 * 1_000;
const ARENA_LAYOUT_KEY = "signal-arcade-arena-layout-v1";
const ARENA_POSITION_GROUP_KEYS = ["active", "exit_blocked", "dormant"] as const;
const DECISIONS_LAYOUT_KEY = "signal-arcade-decisions-layout-v1";
const DECISION_GROUP_KEYS = ["best", "passed", "earlier"] as const;
const LEARNING_UI_KEY = "signal-arcade-learning-ui-v1";
const LEARNING_SECTION_KEYS = ["champion_journey", "challenger_proof", "learning_evidence", "coach_notebook", "coach_contribution", "coach_safety"] as const;
const LEARNING_VIEW_KEYS = ["overview", "baseline", "challenger", "coach", "reviews", "safety"] as const;
const MAX_SEASON_HISTORY_POINTS = 240;

type LearningSectionKey = typeof LEARNING_SECTION_KEYS[number];
type LearningViewKey = typeof LEARNING_VIEW_KEYS[number];
type SeasonComparisonGroup = NonNullable<SeasonsData["comparison_groups"]>[number];
type SeasonComparisonPickerOption = {
  value: string;
  label: string;
  detail: string;
};
type SeasonComparisonPickerSection = {
  label: string;
  options: SeasonComparisonPickerOption[];
};

function finiteNonNegativeSeconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : null;
}

function compactAutoSeasonTime(seconds: number): string {
  const roundedMinutes = Math.max(1, Math.ceil(seconds / 60));
  if (roundedMinutes < 60) return `${roundedMinutes}m`;
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function autoSeasonStatusChip(
  automation: SeasonAutomation,
  configuredHours: number,
): { label: string; ariaLabel: string } {
  const remaining = finiteNonNegativeSeconds(automation.remaining_seconds);
  const verified = finiteNonNegativeSeconds(automation.verified_seconds);
  const grace = finiteNonNegativeSeconds(automation.grace_seconds) ?? configuredHours * 3_600;
  if (automation.state === "countdown") {
    const label = remaining === null ? "Counting" : `${compactAutoSeasonTime(remaining)} left`;
    return { label, ariaLabel: `Automatic season status: ${label}` };
  }
  if (automation.state === "paused") {
    const progress = verified === null
      ? "Paused"
      : `${compactAutoSeasonTime(verified)} / ${compactAutoSeasonTime(grace)} saved`;
    return { label: progress, ariaLabel: `Automatic season status: ${progress}` };
  }
  const label = automation.state === "due"
    ? "Due now"
    : automation.state === "confirming"
      ? "Checking"
      : automation.state === "managing_positions"
        ? "Managing"
        : automation.state === "pending_orders"
          ? "Settling"
          : automation.state === "engine_stopped"
            ? "Engine off"
            : automation.state === "maintenance"
              ? "Paused"
              : automation.state === "waiting_for_data"
                ? "Waiting"
                : `${configuredHours}h rule`;
  return { label, ariaLabel: `Automatic season status: ${label}` };
}

function loadDismissedMaintenanceNotice(): string | null {
  try {
    const operationId = window.localStorage.getItem(DISMISSED_MAINTENANCE_NOTICE_KEY);
    return operationId && operationId.length <= 180 ? operationId : null;
  } catch {
    return null;
  }
}

function saveDismissedMaintenanceNotice(operationId: string): void {
  try {
    window.localStorage.setItem(DISMISSED_MAINTENANCE_NOTICE_KEY, operationId);
  } catch {
    // Storage can be unavailable. Dismissal still applies until this page is reloaded.
  }
}

function maintenanceCompletionCopy(
  operation: MaintenanceOperation | null,
  currentVersion: string,
  serverTime: string,
): string | null {
  if (operation?.state !== "completed") return null;
  const restartedVersion = typeof operation.restarted_version === "string"
    ? operation.restarted_version.trim()
    : "";
  const runningVersion = typeof currentVersion === "string" ? currentVersion.trim() : "";
  const completedAtValue = typeof operation.completed_at === "string" ? operation.completed_at : "";
  const serverTimeValue = typeof serverTime === "string" ? serverTime : "";
  if (!restartedVersion || restartedVersion !== runningVersion || !completedAtValue) return null;
  const completedAt = Date.parse(completedAtValue);
  const serverNow = Date.parse(serverTimeValue);
  if (!Number.isFinite(completedAt) || !Number.isFinite(serverNow)) return null;
  const ageMs = serverNow - completedAt;
  if (ageMs < -MAINTENANCE_NOTICE_FUTURE_TOLERANCE_MS || ageMs > MAINTENANCE_NOTICE_MAX_AGE_MS) return null;
  const preparedVersion = typeof operation.prepared_version === "string"
    ? operation.prepared_version.trim()
    : "";
  return preparedVersion && preparedVersion !== restartedVersion
    ? `Updated safely from v${preparedVersion} to v${restartedVersion}.`
    : `Restarted safely on v${restartedVersion}.`;
}

type LearningUiPreferences = {
  activeView: LearningViewKey;
  expandedSections: Set<LearningSectionKey>;
  seenMilestoneIds: Set<string>;
  initialized: boolean;
};

type LearningMilestone = {
  id: string;
  title: string;
  detail: string;
  tone: "info" | "good" | "warning";
};

function defaultLearningUi(): LearningUiPreferences {
  return {
    activeView: "overview",
    expandedSections: new Set(),
    seenMilestoneIds: new Set(),
    initialized: false,
  };
}

function loadLearningUi(): LearningUiPreferences {
  const defaults = defaultLearningUi();
  try {
    const raw = window.localStorage.getItem(LEARNING_UI_KEY);
    if (!raw) return defaults;
    const stored: unknown = JSON.parse(raw);
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return defaults;
    const record = stored as Record<string, unknown>;
    if (record.version !== 1 && record.version !== 2) return defaults;
    const activeView = record.version === 2
      && typeof record.activeView === "string"
      && LEARNING_VIEW_KEYS.includes(record.activeView as LearningViewKey)
      ? record.activeView as LearningViewKey
      : defaults.activeView;
    const expandedSections = record.version === 2 && Array.isArray(record.expandedSections)
      ? new Set(record.expandedSections.filter(
        (key): key is LearningSectionKey => typeof key === "string"
          && LEARNING_SECTION_KEYS.includes(key as LearningSectionKey),
      ))
      : defaults.expandedSections;
    const seenMilestoneIds = Array.isArray(record.seenMilestoneIds)
      ? new Set(record.seenMilestoneIds.filter(
        (id): id is string => typeof id === "string" && id.length > 0 && id.length <= 180,
      ).slice(-100))
      : new Set<string>();
    return { activeView, expandedSections, seenMilestoneIds, initialized: record.initialized === true };
  } catch {
    return defaults;
  }
}

function saveLearningUi(preferences: LearningUiPreferences): void {
  try {
    window.localStorage.setItem(LEARNING_UI_KEY, JSON.stringify({
      version: 2,
      initialized: preferences.initialized,
      activeView: preferences.activeView,
      expandedSections: LEARNING_SECTION_KEYS.filter((key) => preferences.expandedSections.has(key)),
      seenMilestoneIds: Array.from(preferences.seenMilestoneIds).slice(-100),
    }));
  } catch {
    // Storage can be unavailable. Sections and milestones still work for this page load.
  }
}

function learningMilestones(snapshot: Snapshot): LearningMilestone[] {
  const milestones: LearningMilestone[] = [];
  const learning = snapshot.learning;
  const latestVersion = learning.latest_model?.version;
  if (latestVersion && learning.latest_model?.qualified && !learning.activation_available && learning.active_model_health.state !== "suspended") {
    milestones.push({
      id: `challenger-proof-${latestVersion}`,
      title: "Challenger proof advanced",
      detail: "The fitted model passed its historical proof; current activation safety is still collecting.",
      tone: "info",
    });
  }
  if (latestVersion && learning.activation_available && learning.mode !== "active") {
    milestones.push({
      id: `challenger-ready-${latestVersion}`,
      title: "Qualified Challenger ready",
      detail: "Every server-side proof and current coverage gate passed. It is waiting for your choice.",
      tone: "good",
    });
  }
  if (learning.mode === "active" && learning.active_model?.version) {
    milestones.push({
      id: `challenger-active-${learning.active_model.version}`,
      title: "Qualified Challenger active",
      detail: "Bounded learned protection is active while the Baseline remains the safe core and fallback.",
      tone: "good",
    });
  }
  if (learning.active_model_health.state === "suspended") {
    milestones.push({
      id: `challenger-suspended-${learning.active_model_health.model_version ?? "unknown"}-${learning.active_model_health.suspended_at ?? "current"}`,
      title: "Baseline safely regained control",
      detail: "Later unseen evidence suspended the learner and returned it to Shadow.",
      tone: "warning",
    });
  }
  (learning.skills ?? []).forEach((skill) => {
    const championVersion = skill.champion?.version;
    if (championVersion && !skill.active_version && skill.state !== "suspended") {
      const championEvent = (learning.champion_journey ?? []).find((event) => (
        event.skill === skill.skill && event.champion_version === championVersion
      ));
      milestones.push({
        id: `challenger-skill-qualified-${skill.skill}-${championVersion}`,
        title: championEvent?.kind === "promoted"
          ? `${skill.label} crowned a new Champion`
          : `${skill.label} skill qualified`,
        detail: championEvent?.kind === "promoted"
          ? "A contender beat the saved Champion on shared forward outcomes. Influence remains separately gated."
          : learning.consent_granted
            ? "Its independent proof passed. Fresh combined evidence decides when it may join."
            : "Its independent proof passed. It remains Shadow until you enable the Challenger once.",
        tone: "good",
      });
    }
    if (skill.active_version) {
      milestones.push({
        id: `challenger-skill-active-${skill.skill}-${skill.active_version}`,
        title: `${skill.label} joined the team`,
        detail: "Fresh combined proof passed; this bounded skill is now active with the Baseline fallback.",
        tone: "good",
      });
    }
    if (skill.state === "suspended" && championVersion) {
      milestones.push({
        id: `challenger-skill-suspended-${skill.skill}-${championVersion}`,
        title: `${skill.label} returned to Shadow`,
        detail: "Later unseen evidence failed its health guard. Other safe components remain isolated.",
        tone: "warning",
      });
    }
  });
  snapshot.coach.recent_hypotheses
    .filter((hypothesis) => hypothesis.context_active)
    .slice(0, 3)
    .forEach((hypothesis) => {
      if (hypothesis.contribution_state === "handed_off") {
        milestones.push({
          id: `coach-contribution-handed-off-${hypothesis.hypothesis_id}`,
          title: "Coach idea entered a Challenger battle",
          detail: "The proved idea is now a contender only. The saved Champion stays in control until fresh common outcomes prove an advantage.",
          tone: "good",
        });
        return;
      }
      if (hypothesis.state === "promising" && hypothesis.contribution_state === "ready") {
        milestones.push({
          id: `coach-contribution-ready-${hypothesis.hypothesis_id}`,
          title: "Coach idea is ready to challenge",
          detail: "Independent Coach proof passed. You may allow this idea into a normal Challenger tournament; it still cannot trade directly.",
          tone: "good",
        });
        return;
      }
      const copy = hypothesis.state === "testing"
        ? "A new allowlisted coaching idea has begun collecting independent forward evidence."
        : hypothesis.state === "promising"
          ? "A coaching idea passed its current Shadow proof across independent seasons. Influence remains zero."
          : hypothesis.state === "inconclusive"
            ? "A coaching test lacked enough executable outcome coverage to be trusted."
            : "Forward evidence did not support this coaching idea.";
      milestones.push({
        id: `coach-${hypothesis.hypothesis_id}-${hypothesis.state}`,
        title: hypothesis.state === "testing" ? "AI Coach started an experiment" : `Coach experiment ${title(hypothesis.state)}`,
        detail: copy,
        tone: hypothesis.state === "promising" ? "good" : hypothesis.state === "testing" ? "info" : "warning",
      });
    });
  if (snapshot.ai_lab.qualification.qualified) {
    milestones.push({
      id: `ai-shadow-proof-${snapshot.ai_lab.qualification.configuration_fingerprint}`,
      title: "Local AI Shadow proof target reached",
      detail: "This is an evidence milestone only. Qualified Coach remains a future, unavailable stage.",
      tone: "good",
    });
  }
  return milestones.slice(0, 8);
}

type DecisionGroupKey = typeof DECISION_GROUP_KEYS[number];

type DecisionsLayoutPreferences = {
  expandedGroups: Set<DecisionGroupKey>;
};

function defaultDecisionsLayout(): DecisionsLayoutPreferences {
  return { expandedGroups: new Set(["best"]) };
}

function loadDecisionsLayout(): DecisionsLayoutPreferences {
  const defaults = defaultDecisionsLayout();
  try {
    const raw = window.localStorage.getItem(DECISIONS_LAYOUT_KEY);
    if (!raw) return defaults;
    const stored: unknown = JSON.parse(raw);
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return defaults;
    const record = stored as Record<string, unknown>;
    if (record.version !== 1 || !Array.isArray(record.expandedGroups)) return defaults;
    return {
      expandedGroups: new Set(record.expandedGroups.filter(
        (key): key is DecisionGroupKey => typeof key === "string"
          && DECISION_GROUP_KEYS.includes(key as DecisionGroupKey),
      )),
    };
  } catch {
    return defaults;
  }
}

function saveDecisionsLayout(preferences: DecisionsLayoutPreferences): void {
  try {
    window.localStorage.setItem(DECISIONS_LAYOUT_KEY, JSON.stringify({
      version: 1,
      expandedGroups: DECISION_GROUP_KEYS.filter((key) => preferences.expandedGroups.has(key)),
    }));
  } catch {
    // Storage can be unavailable in private or locked-down browsers. Layout still works for this page load.
  }
}

type ArenaLayoutPreferences = {
  marketRadarCollapsed: boolean;
  collapsedPositionGroups: Set<string>;
};

function defaultArenaLayout(): ArenaLayoutPreferences {
  const compactViewport = typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(max-width: 650px)").matches;
  return { marketRadarCollapsed: compactViewport, collapsedPositionGroups: new Set(["dormant"]) };
}

function loadArenaLayout(): ArenaLayoutPreferences {
  const defaults = defaultArenaLayout();
  try {
    const raw = window.localStorage.getItem(ARENA_LAYOUT_KEY);
    if (!raw) return defaults;
    const stored: unknown = JSON.parse(raw);
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return defaults;
    const record = stored as Record<string, unknown>;
    if (record.version !== 1) return defaults;
    const collapsed = Array.isArray(record.collapsedPositionGroups)
      ? new Set(record.collapsedPositionGroups.filter(
        (key): key is string => typeof key === "string" && ARENA_POSITION_GROUP_KEYS.includes(key as typeof ARENA_POSITION_GROUP_KEYS[number]),
      ))
      : defaults.collapsedPositionGroups;
    return {
      marketRadarCollapsed: typeof record.marketRadarCollapsed === "boolean"
        ? record.marketRadarCollapsed
        : defaults.marketRadarCollapsed,
      collapsedPositionGroups: collapsed,
    };
  } catch {
    return defaults;
  }
}

function saveArenaLayout(preferences: ArenaLayoutPreferences): void {
  try {
    window.localStorage.setItem(ARENA_LAYOUT_KEY, JSON.stringify({
      version: 1,
      marketRadarCollapsed: preferences.marketRadarCollapsed,
      collapsedPositionGroups: ARENA_POSITION_GROUP_KEYS.filter((key) => preferences.collapsedPositionGroups.has(key)),
    }));
  } catch {
    // Storage can be unavailable in private or locked-down browsers. Layout still works for this page load.
  }
}

type ExplanationState =
  | { status: "loading"; decision: Decision }
  | { status: "ready"; decision: Decision; text: string; source: string }
  | { status: "error"; decision: Decision; message: string };

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<Tab>("arena");
  const [learningUi, setLearningUi] = useState(loadLearningUi);
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
  const milestones = useMemo(() => snapshot ? learningMilestones(snapshot) : [], [snapshot]);
  const visibleMilestones = useMemo(() => milestones.slice(0, 3), [milestones]);
  const unseenMilestones = learningUi.initialized
    ? visibleMilestones.filter((milestone) => !learningUi.seenMilestoneIds.has(milestone.id))
    : [];

  useEffect(() => {
    if (!learningUi.initialized) return;
    saveLearningUi(learningUi);
  }, [learningUi]);

  useEffect(() => {
    const storageChanged = (event: StorageEvent) => {
      if (event.key === LEARNING_UI_KEY || event.key === null) setLearningUi(loadLearningUi());
    };
    window.addEventListener("storage", storageChanged);
    return () => window.removeEventListener("storage", storageChanged);
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    const timer = window.setTimeout(() => {
      setLearningUi((current) => {
        if (current.initialized && (tab !== "learning" || current.activeView !== "overview")) return current;
        const seen = new Set(current.seenMilestoneIds);
        visibleMilestones.forEach((milestone) => seen.add(milestone.id));
        return { ...current, initialized: true, seenMilestoneIds: new Set(Array.from(seen).slice(-100)) };
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [learningUi.activeView, visibleMilestones, snapshot, tab]);

  const setLearningView = useCallback((activeView: LearningViewKey) => {
    setLearningUi((current) => ({ ...current, activeView }));
  }, []);

  const toggleLearningSection = useCallback((key: LearningSectionKey) => {
    setLearningUi((current) => {
      const expanded = new Set(current.expandedSections);
      if (expanded.has(key)) expanded.delete(key);
      else expanded.add(key);
      return { ...current, expandedSections: expanded };
    });
  }, []);

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

  const setRisk = async (
    mode: RiskMode,
    drawdownPolicy: DrawdownPolicy = { kind: "default", custom_threshold_bps: null },
    transitionStrategy: ProfileTransitionStrategy = "finish_safely",
    quoteCurrency?: QuoteCurrency,
    startingAmount?: string,
  ) => {
    setBusy(true);
    try {
      await api.setRisk(mode, drawdownPolicy, transitionStrategy, quoteCurrency, startingAmount);
      resolveIssue("risk");
      await refresh();
    } catch (cause) {
      reportIssue("risk", "Next-season settings were not changed", cause);
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

  const setupPortfolio = async (currency: QuoteCurrency, amount: string, riskMode: RiskMode, drawdownPolicy: DrawdownPolicy): Promise<string | null> => {
    setBusy(true);
    try {
      await api.setupPortfolio(currency, amount, riskMode, drawdownPolicy);
      resolveIssue("setup");
      await refresh();
      return null;
    } catch (cause) {
      // The setup transaction can safely outlive a disconnected/aborted HTTP response while it
      // waits for the event boundary. Reconcile once against authoritative server state before
      // inviting a retry that could only produce a confusing duplicate-initialization response.
      try {
        const confirmed = await api.snapshot();
        setSnapshot(confirmed);
        if (
          confirmed.portfolio.initialized
          || (
            confirmed.season_operation?.kind === "setup"
            && confirmed.season_operation.state === "running"
          )
        ) {
          resolveIssue("setup");
          return null;
        }
      } catch {
        // Preserve the original setup error; normal polling continues independently.
      }
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

  const setCoachContribution = async (enabled: boolean) => {
    setBusy(true);
    try {
      await api.setCoachContribution(enabled);
      resolveIssue("ai");
      await refresh();
    } catch (cause) {
      reportIssue("ai", "AI Coach contribution permission was not changed", cause);
    } finally {
      setBusy(false);
    }
  };

  const setCoachResearch = async (enabled: boolean) => {
    setBusy(true);
    try {
      await api.setCoachResearch(enabled);
      resolveIssue("ai");
      await refresh();
    } catch (cause) {
      reportIssue("ai", "AI Coach research mode was not changed", cause);
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
          <NavButton active={tab === "learning"} attention={unseenMilestones.length > 0} onClick={() => setTab("learning")} icon={<GraduationCap size={17} />} label="Learning" />
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
          <Arena snapshot={snapshot} totalPnl={totalPnl} setRisk={setRisk} setSeasonAutomation={setSeasonAutomation} setupPortfolio={setupPortfolio} setEngineRunning={setEngineRunning} busy={controlsBusy} explain={explain} explainingId={explanation?.status === "loading" ? explanation.decision.decision_id : null} onViewAllDecisions={() => setTab("decisions")} />
        ) : tab === "decisions" ? (
          <Decisions decisions={snapshot.decisions} explain={explain} explainingId={explanation?.status === "loading" ? explanation.decision.decision_id : null} serverTime={snapshot.server_time} candidateWindowMinutes={snapshot.candidate_window_minutes} staleMarketSeconds={snapshot.stale_market_seconds} engineRunning={snapshot.running} />
        ) : tab === "leaderboard" ? (
          <LeaderboardView explain={explain} reportIssue={reportIssue} resolveIssue={resolveIssue} />
        ) : tab === "learning" ? (
          <LearningLab snapshot={snapshot} setLearningMode={setLearningMode} setAiMode={setAiMode} setCoachResearch={setCoachResearch} setCoachContribution={setCoachContribution} busy={controlsBusy} activeView={learningUi.activeView} setActiveView={setLearningView} expandedSections={learningUi.expandedSections} toggleSection={toggleLearningSection} milestones={milestones} hasUnseenMilestones={unseenMilestones.length > 0} />
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
  const title = operation.kind === "reset"
    ? "Preparing the new season"
    : operation.kind === "setup"
      ? "Creating the paper bankroll"
      : operation.kind === "profile_transition"
        ? `Changing to ${riskModeLabel(operation.target_risk_mode ?? "balanced")}`
        : "Starting the paper engine";
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

function Arena({ snapshot, totalPnl, setRisk, setSeasonAutomation, setupPortfolio, setEngineRunning, busy, explain, explainingId, onViewAllDecisions }: {
  snapshot: Snapshot;
  totalPnl: number;
  setRisk: (mode: RiskMode, drawdownPolicy?: DrawdownPolicy, transitionStrategy?: ProfileTransitionStrategy, quoteCurrency?: QuoteCurrency, startingAmount?: string) => Promise<void>;
  setSeasonAutomation: (enabled: boolean, graceHours?: number) => Promise<void>;
  setupPortfolio: (currency: QuoteCurrency, amount: string, riskMode: RiskMode, drawdownPolicy: DrawdownPolicy) => Promise<string | null>;
  setEngineRunning: (running: boolean) => Promise<void>;
  busy: boolean;
  explain: (decision: Decision) => Promise<void>;
  explainingId: string | null;
  onViewAllDecisions: () => void;
}) {
  const portfolio = snapshot.portfolio;
  const [arenaLayout, setArenaLayout] = useState(loadArenaLayout);
  const collapsedPositionGroups = arenaLayout.collapsedPositionGroups;
  const marketRadarCollapsed = arenaLayout.marketRadarCollapsed;
  const [pendingProfile, setPendingProfile] = useState<{
    mode: RiskMode;
    drawdownPolicy: DrawdownPolicy;
    transitionStrategy: ProfileTransitionStrategy;
    quoteCurrency: QuoteCurrency;
    startingAmount: string;
    customDrawdown: string;
  } | null>(null);
  const profileDialogOpen = pendingProfile !== null;
  const profileDialogRef = useRef<HTMLElement>(null);
  const profileReturnFocusRef = useRef<HTMLElement | null>(null);
  const updateArenaLayout = useCallback((update: (current: ArenaLayoutPreferences) => ArenaLayoutPreferences) => {
    setArenaLayout((current) => {
      const next = update(current);
      saveArenaLayout(next);
      return next;
    });
  }, []);
  useEffect(() => {
    const syncArenaLayout = (event: StorageEvent) => {
      if (event.key === ARENA_LAYOUT_KEY || event.key === null) {
        setArenaLayout(loadArenaLayout());
      }
    };
    window.addEventListener("storage", syncArenaLayout);
    return () => window.removeEventListener("storage", syncArenaLayout);
  }, []);
  const closeProfileDialog = useCallback(() => setPendingProfile(null), []);
  useEffect(() => {
    if (!profileDialogOpen) return;
    const dialog = profileDialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeProfileDialog();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = [...dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
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
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
      profileReturnFocusRef.current?.focus();
      profileReturnFocusRef.current = null;
    };
  }, [closeProfileDialog, profileDialogOpen]);
  if (!portfolio.initialized) {
    return <SetupArena snapshot={snapshot} busy={busy} setupPortfolio={setupPortfolio} />;
  }
  const hasHistory = portfolio.positions.length > 0 || snapshot.fills.length > 0 || snapshot.decisions.length > 0;
  const latestDecisionFeed = latestDecisionsByMint(snapshot.decisions).slice(0, 8);
  const capacityPositionCount = portfolio.positions.filter((item) => item.market_status !== "dormant").length;
  const autoSeasonHours = Math.max(1, Math.round(snapshot.season_automation.grace_seconds / 3600));
  const autoSeasonChip = autoSeasonStatusChip(snapshot.season_automation, autoSeasonHours);
  const profileTransition = snapshot.season_operation?.kind === "profile_transition"
    && snapshot.season_operation.state === "running";
  const profileLocked = snapshot.season_profile === null || snapshot.season_profile.locked_at !== null;
  const positionCapacity = snapshot.season_profile?.risk_limits.max_open_positions ?? null;
  const exposureCap = typeof snapshot.season_profile?.risk_limits.max_exposure_fraction === "number"
    ? snapshot.season_profile.risk_limits.max_exposure_fraction
    : null;
  const openSeasonEditor = (
    mode: RiskMode = snapshot.risk_mode,
    drawdownPolicy: DrawdownPolicy = snapshot.season_profile?.drawdown_policy
      ?? { kind: "default", custom_threshold_bps: null },
  ) => {
    if (busy || profileTransition) return;
    profileReturnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setPendingProfile({
      mode,
      drawdownPolicy,
      transitionStrategy: "finish_safely",
      quoteCurrency: portfolio.quote_currency,
      startingAmount: minorAmountInput(portfolio.starting_lamports, portfolio.quote_decimals),
      customDrawdown: drawdownPolicy.custom_threshold_bps
        ? String(drawdownPolicy.custom_threshold_bps / 100)
        : "",
    });
  };
  const positionGroups = [
    { key: "active", label: "Active", hint: "Fresh, verified sell route", positions: portfolio.positions.filter((item) => item.market_status === "active") },
    { key: "exit_blocked", label: "Exit blocked", hint: "Fresh indication; route not currently executable", positions: portfolio.positions.filter((item) => item.market_status === "exit_blocked") },
    { key: "dormant", label: "Dormant", hint: "Still monitored; does not use an active slot", positions: portfolio.positions.filter((item) => item.market_status === "dormant") },
  ].filter((group) => group.positions.length > 0);
  const pendingAmount = pendingProfile
    ? parseStartingAmount(pendingProfile.startingAmount, pendingProfile.quoteCurrency)
    : null;
  const pendingCustomMatch = pendingProfile?.drawdownPolicy.kind === "custom"
    ? /^(\d+)(?:\.(\d{1,2}))?$/.exec(pendingProfile.customDrawdown.trim())
    : null;
  const pendingCustomValue = pendingProfile?.drawdownPolicy.kind === "custom"
    ? Number(pendingProfile.customDrawdown)
    : null;
  const pendingDrawdownError = pendingProfile?.drawdownPolicy.kind === "custom"
    && (!pendingCustomMatch || !Number.isFinite(pendingCustomValue) || pendingCustomValue! < 1 || pendingCustomValue! > 99)
    ? "Enter a drawdown from 1% to 99%, using at most two decimals."
    : null;
  const pendingResolvedPolicy = pendingProfile
    ? canonicalDrawdownPolicy(
      pendingProfile.mode,
      pendingProfile.drawdownPolicy.kind === "custom" && pendingDrawdownError === null
        ? { kind: "custom", custom_threshold_bps: Math.round(pendingCustomValue! * 100) }
        : pendingProfile.drawdownPolicy,
      snapshot.season_profile_catalog,
    )
    : null;
  const pendingPlanChanged = Boolean(
    pendingProfile
    && pendingAmount !== null
    && pendingAmount.minor !== null
    && (
      pendingProfile.quoteCurrency !== portfolio.quote_currency
      || pendingAmount.minor !== portfolio.starting_lamports
      || pendingProfile.mode !== snapshot.risk_mode
      || pendingResolvedPolicy?.kind !== snapshot.season_profile?.drawdown_policy.kind
      || pendingResolvedPolicy?.custom_threshold_bps !== snapshot.season_profile?.drawdown_policy.custom_threshold_bps
    )
  );
  return (
    <>
      <section className="page-heading">
        <div><span className="eyebrow"><Radio size={14} /> The Arena</span><h1>Your strategy, playing forward.</h1><p>Real market observations. Virtual {portfolio.quote_currency}. Every assumption visible.</p></div>
        <div className={`engine-control ${snapshot.running ? "running" : "stopped"}`}><div><strong><span />{profileTransition ? "Changing season profile" : `Paper engine ${snapshot.running ? "running" : "stopped"}`}</strong><small>{profileTransition ? "New entries are paused while the old season safely settles." : snapshot.running ? "Analyzing and managing the paper portfolio." : portfolio.positions.length ? "Positions are preserved and still marked from fresh data." : "No new paper decisions or fills will occur."}</small></div><button onClick={() => void setEngineRunning(!snapshot.running)} disabled={busy || profileTransition}>{profileTransition ? <RotateCcw size={15} /> : snapshot.running ? <Pause size={15} /> : <Play size={15} />}{profileTransition ? "Settling" : snapshot.running ? "Stop" : hasHistory ? "Resume" : "Start"}</button></div>
      </section>

      <div className={`market-state-line ${snapshot.demo_mode ? "demo" : "live"}`}><span />{snapshot.demo_mode ? "Synthetic demo market" : "Solana mainnet paper feed"}{!snapshot.running && <small>Market observations continue while the paper engine is stopped.</small>}</div>

      {portfolio.risk_halted && <div className="risk-halt-note"><AlertTriangle size={17} /><div><strong>New entries are risk-paused</strong><p>The drawdown guardrail is active. Existing positions still receive exit management when fresh executable data is available.</p></div></div>}
      {portfolio.excluded_position_count > 0 && <div className="stale-value-note"><History size={17} /><div><strong>{portfolio.excluded_position_count} position{portfolio.excluded_position_count === 1 ? " is" : "s are"} outside executable equity</strong><p>{portfolio.route_blocked_position_count > 0 ? `${portfolio.route_blocked_position_count} fresh but exit-blocked. ` : ""}{portfolio.stale_position_count > 0 ? `${portfolio.stale_position_count} dormant without a fresh market. ` : ""}Headline equity excludes {money(portfolio.excluded_invested_value_lamports, portfolio.quote_currency, portfolio.quote_decimals)} of indicative or last-known value; last-known equity is {money(portfolio.last_known_equity_lamports, portfolio.quote_currency, portfolio.quote_decimals)}.</p></div></div>}

      <section className="hero-grid">
        <article className="card equity-card">
          <div className="card-label">Paper equity</div>
          <div className="equity-value">{money(portfolio.equity_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</div>
          <div className={`pnl-line ${totalPnl >= 0 ? "positive" : "negative"}`}>{signedMoney(totalPnl, portfolio.quote_currency, portfolio.quote_decimals)} <span>this season</span></div>
          <EquityChart points={snapshot.equity_history} />
          <div className="equity-meta">
            <span>{portfolio.reserved_cash_lamports ? "Available" : "Cash"} <strong>{money(portfolio.available_cash_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>
            {portfolio.reserved_cash_lamports > 0 && <span>Reserved <strong>{money(portfolio.reserved_cash_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>}
            <span>Executable value <strong>{money(portfolio.invested_value_lamports, portfolio.quote_currency, portfolio.quote_decimals)}</strong></span>
            <span>Drawdown <strong>{percent(portfolio.drawdown_fraction)}</strong></span>
          </div>
        </article>

        <article className="card risk-card">
          <div className="risk-profile-heading">
            <div>
              <div className="card-label"><ShieldCheck size={16} /> Current season profile</div>
              <h2>{riskModeLabel(snapshot.risk_mode)}</h2>
              <p>{riskCopy(snapshot.risk_mode)}</p>
            </div>
            <button type="button" className="button subtle" disabled={busy || profileTransition} onClick={() => openSeasonEditor()}><Settings size={14} />Edit next season</button>
          </div>
          <div className="active-profile-summary" aria-label="Current season settings">
            <div><span>Paper bankroll</span><strong>{minorAmountInput(portfolio.starting_lamports, portfolio.quote_decimals)} {portfolio.quote_currency}</strong></div>
            <div><span>Position capacity</span><strong>{positionCapacity === null ? "Unavailable" : `${positionCapacity} position${positionCapacity === 1 ? "" : "s"}`}</strong></div>
            <div><span>Total exposure cap</span><strong>{exposureCap === null ? "Unavailable" : percent(exposureCap)}</strong></div>
            <div><span>Drawdown halt</span><strong>{drawdownProfileLabel(snapshot.season_profile)}</strong></div>
          </div>
          <p className="active-profile-lock">{profileLocked ? "Locked for this season. Changes begin at a clean season boundary." : "Editable until the first decision locks this season."}</p>
          <div className="guardrail"><ShieldCheck size={17} /><span>Structural safety and stale-data gates always remain active.</span></div>
          <div className={`auto-season-control ${snapshot.season_automation.enabled ? "enabled" : ""}`}>
            <RotateCcw size={16} />
            <div><strong>Auto new season <em>{snapshot.season_automation.enabled ? "On" : "Off"}</em></strong><small>{snapshot.season_automation.enabled ? snapshot.season_automation.detail : snapshot.season_profile?.drawdown_policy.kind === "disabled" ? `Wait ${autoSeasonHours}h after genuine bankroll exhaustion; recoverable holdings and unknown data always defer rollover.` : `Wait ${autoSeasonHours}h after a guarded pause with no active holdings; healthy data is always required.`}</small></div>
            {!snapshot.season_automation.enabled ? <label className="auto-season-delay">Wait<select aria-label="Automatic season wait" value={autoSeasonHours} disabled={busy} onChange={(event) => void setSeasonAutomation(false, Number(event.target.value))}>{Array.from({ length: 24 }, (_, index) => index + 1).map((hours) => <option value={hours} key={hours}>{hours}h</option>)}</select></label> : <span className={`auto-season-delay-chip state-${snapshot.season_automation.state}`} aria-label={autoSeasonChip.ariaLabel} title={snapshot.season_automation.detail}>{autoSeasonChip.label}</span>}
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
                  onClick={() => updateArenaLayout((current) => {
                    const next = new Set(current.collapsedPositionGroups);
                    if (collapsed) next.delete(group.key);
                    else next.add(group.key);
                    return { ...current, collapsedPositionGroups: next };
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
          <SectionHeader
            title="Decision feed"
            subtitle="The latest evidence checkpoints"
            action={<button type="button" className="section-action" onClick={onViewAllDecisions} aria-label="View all decisions">View all <ChevronRight size={13} /></button>}
          />
          <div className="stack">
            {latestDecisionFeed.map((decision) => <DecisionRow key={decision.decision_id} decision={decision} explain={explain} loading={explainingId === decision.decision_id} />)}
            {!snapshot.decisions.length && <EmptyState icon={<Activity size={22} />} title="Waiting for evidence" copy="Choose Demo Market in Settings if you want to explore without waiting for a live launch." />}
          </div>
        </div>
      </section>

      <section className="market-radar-section">
        <SectionHeader
          title="Market radar"
          subtitle="Recent tokens with point-in-time market evidence quality"
          action={<button type="button" className="section-action" aria-expanded={!marketRadarCollapsed} aria-controls="market-radar-grid" aria-label={`${marketRadarCollapsed ? "Show" : "Hide"} Market radar`} onClick={() => updateArenaLayout((current) => ({ ...current, marketRadarCollapsed: !current.marketRadarCollapsed }))}>{marketRadarCollapsed ? "Show" : "Hide"} <ChevronDown className={marketRadarCollapsed ? "collapsed" : ""} size={13} /></button>}
        />
        <div className={`token-grid ${marketRadarCollapsed ? "is-collapsed" : ""}`} id="market-radar-grid" hidden={marketRadarCollapsed} aria-hidden={marketRadarCollapsed}>
          {snapshot.tokens.slice(0, 8).map((token) => <TokenCard key={token.mint} token={token} />)}
          {!snapshot.tokens.length && <div className="market-radar-empty"><EmptyState icon={<Activity size={22} />} title="Radar is warming up" copy={snapshot.running ? "Recent tokens will appear after the selected market source produces enough point-in-time evidence." : "Market observations continue while the paper engine is stopped; recent tokens will appear when enough evidence arrives."} /></div>}
        </div>
      </section>
      {pendingProfile && <div className="profile-confirm-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeProfileDialog(); }}>
        <section
          className="card profile-confirm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="profile-confirm-title"
          aria-describedby="profile-confirm-copy"
          tabIndex={-1}
          ref={profileDialogRef}
        >
          <Settings size={23} />
          <h2 id="profile-confirm-title">Edit the next paper season</h2>
          <p id="profile-confirm-copy">Choose the complete target once. Currency, virtual bankroll and risk policy change together at one clean boundary; current inventory never crosses into the new profile.</p>
          <div className="season-plan-current"><span>Current</span><strong>{portfolio.quote_currency} {minorAmountInput(portfolio.starting_lamports, portfolio.quote_decimals)} · {riskModeLabel(snapshot.risk_mode)} · {shortDrawdownLabel(snapshot.season_profile)}</strong></div>
          <div className="season-plan-editor">
            <fieldset className="season-plan-currency"><legend>Account currency</legend>{(["SOL", "USDC"] as QuoteCurrency[]).map((currency) => <label className={pendingProfile.quoteCurrency === currency ? "selected" : ""} key={currency}><input type="radio" name="next-season-currency" checked={pendingProfile.quoteCurrency === currency} onChange={() => setPendingProfile((current) => current ? { ...current, quoteCurrency: currency } : current)} /><span><strong>{currency}</strong><small>{currency === "SOL" ? "Native Solana accounting" : "Dollar-denominated accounting"}</small></span></label>)}</fieldset>
            <label className="season-plan-amount"><span>Virtual starting bankroll</span><div><input aria-label="Next season starting amount" inputMode="decimal" value={pendingProfile.startingAmount} onChange={(event) => setPendingProfile((current) => current ? { ...current, startingAmount: event.target.value } : current)} /><b>{pendingProfile.quoteCurrency}</b></div>{pendingAmount?.error && <small role="alert">{pendingAmount.error}</small>}</label>
            <fieldset className="season-plan-risk"><legend>Risk personality</legend>{RISK_MODES.map((mode) => <label className={pendingProfile.mode === mode ? "selected" : ""} key={mode}><input type="radio" name="next-season-risk" checked={pendingProfile.mode === mode} onChange={() => setPendingProfile((current) => current ? { ...current, mode } : current)} /><span><strong>{riskModeLabel(mode)}</strong><small>{profileLimitSummary(snapshot.season_profile_catalog.find((profile) => profile.risk_mode === mode) ?? null)}</small></span></label>)}</fieldset>
            <fieldset className="season-plan-drawdown"><legend>Portfolio drawdown halt</legend>
              <label className={pendingProfile.drawdownPolicy.kind === "default" ? "selected" : ""}><input type="radio" name="next-season-drawdown" checked={pendingProfile.drawdownPolicy.kind === "default"} onChange={() => setPendingProfile((current) => current ? { ...current, drawdownPolicy: { kind: "default", custom_threshold_bps: null } } : current)} /><span><strong>Personality default</strong><small>{drawdownPolicyTargetLabel(pendingProfile.mode, { kind: "default", custom_threshold_bps: null }, snapshot.season_profile_catalog)}</small></span></label>
              <label className={pendingProfile.drawdownPolicy.kind === "custom" ? "selected" : ""}><input type="radio" name="next-season-drawdown" checked={pendingProfile.drawdownPolicy.kind === "custom"} onChange={() => setPendingProfile((current) => current ? { ...current, drawdownPolicy: { kind: "custom", custom_threshold_bps: null } } : current)} /><span><strong>Custom</strong><small>A separate season experiment</small></span></label>
              {pendingProfile.drawdownPolicy.kind === "custom" && <label className="season-plan-custom"><input aria-label="Next season custom drawdown percentage" inputMode="decimal" value={pendingProfile.customDrawdown} onChange={(event) => setPendingProfile((current) => current ? { ...current, customDrawdown: event.target.value } : current)} /><b>%</b></label>}
              <label className={pendingProfile.drawdownPolicy.kind === "disabled" ? "selected" : ""}><input type="radio" name="next-season-drawdown" checked={pendingProfile.drawdownPolicy.kind === "disabled"} onChange={() => setPendingProfile((current) => current ? { ...current, drawdownPolicy: { kind: "disabled", custom_threshold_bps: null } } : current)} /><span><strong>Off</strong><small>Structural safety still stays active</small></span></label>
              {pendingDrawdownError && <small className="season-plan-error" role="alert">{pendingDrawdownError}</small>}
            </fieldset>
          </div>
          {profileLocked && <fieldset className="profile-transition-options">
            <legend>How should this season finish?</legend>
            <label className={pendingProfile.transitionStrategy === "finish_safely" ? "selected" : ""}>
              <input type="radio" name="profile-transition-strategy" value="finish_safely" checked={pendingProfile.transitionStrategy === "finish_safely"} onChange={() => setPendingProfile((current) => current ? { ...current, transitionStrategy: "finish_safely" } : current)} />
              <span><strong>Finish safely <em>Recommended</em></strong><small>Freeze entries and manage positions under their original policy. Confirmed terminal inventory becomes an honest write-off after its recovery window.</small></span>
            </label>
            <label className={`manual ${pendingProfile.transitionStrategy === "end_now" ? "selected" : ""}`}>
              <input type="radio" name="profile-transition-strategy" value="end_now" checked={pendingProfile.transitionStrategy === "end_now"} onChange={() => setPendingProfile((current) => current ? { ...current, transitionStrategy: "end_now" } : current)} />
              <span><strong>End season now</strong><small>Try genuine exits for up to 90 seconds, then classify remaining inventory from fresh route evidence. No fill, win or loss is invented.</small></span>
            </label>
          </fieldset>}
          <div className={`profile-transition-impact ${pendingProfile.transitionStrategy === "end_now" && profileLocked ? "warning" : ""}`}>
            {pendingProfile.transitionStrategy === "end_now" && profileLocked ? <AlertTriangle size={15} /> : <ShieldCheck size={15} />}
            <span>{!profileLocked
              ? "This season has never started, so the exact target will replace it atomically without creating an empty scorecard."
              : pendingProfile.transitionStrategy === "end_now"
                ? `${portfolio.positions.filter((position) => position.market_status === "active").length} executable · ${portfolio.positions.filter((position) => position.market_status !== "active").length} non-executable · ${portfolio.pending_orders.filter((order) => order.side === "sell").length} exits already pending.`
                : `${portfolio.positions.length} open position${portfolio.positions.length === 1 ? "" : "s"} will keep the old policy until safely resolved.`}</span>
          </div>
          {pendingProfile.transitionStrategy === "end_now" && profileLocked && <p className="profile-manual-accounting">Remaining inventory is retained as a confirmed write-off or provider-unknown record—never as a made-up fill, win or loss. This manual boundary stays visible in Results but is excluded from strategy comparisons.</p>}
          <div className="profile-confirm-actions"><button type="button" className="button ghost" onClick={closeProfileDialog}>Cancel</button><button type="button" className={`button ${pendingProfile.transitionStrategy === "end_now" && profileLocked ? "warning" : ""}`} disabled={!pendingPlanChanged || pendingAmount === null || pendingAmount.error !== null || pendingDrawdownError !== null} onClick={() => { const target = pendingProfile; const policy = pendingResolvedPolicy; if (!policy || pendingAmount?.minor === null || pendingAmount?.error) return; closeProfileDialog(); void setRisk(target.mode, policy, target.transitionStrategy, target.quoteCurrency, target.startingAmount.trim()); }}>{!pendingPlanChanged ? "No changes" : pendingProfile.transitionStrategy === "end_now" && profileLocked ? "End season & apply" : profileLocked ? "Apply after safe finish" : "Apply settings"}</button></div>
        </section>
      </div>}
    </>
  );
}

function SetupArena({ snapshot, busy, setupPortfolio }: {
  snapshot: Snapshot;
  busy: boolean;
  setupPortfolio: (currency: QuoteCurrency, amount: string, riskMode: RiskMode, drawdownPolicy: DrawdownPolicy) => Promise<string | null>;
}) {
  const [currency, setCurrency] = useState<QuoteCurrency>("SOL");
  const [amount, setAmount] = useState("10");
  const [riskMode, setRiskMode] = useState<RiskMode>(snapshot.risk_mode);
  const [drawdownKind, setDrawdownKind] = useState<DrawdownPolicy["kind"]>("default");
  const [customDrawdown, setCustomDrawdown] = useState("");
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
    let drawdownPolicy: DrawdownPolicy = { kind: drawdownKind, custom_threshold_bps: null };
    if (drawdownKind === "custom") {
      const customMatch = /^(\d+)(?:\.(\d{1,2}))?$/.exec(customDrawdown.trim());
      const customValue = Number(customDrawdown);
      if (!customMatch || !Number.isFinite(customValue) || customValue < 1 || customValue > 99) {
        setError("Custom drawdown must be from 1% to 99%, using at most two decimals.");
        return;
      }
      drawdownPolicy = { kind: "custom", custom_threshold_bps: Math.round(customValue * 100) };
    }
    drawdownPolicy = canonicalDrawdownPolicy(riskMode, drawdownPolicy, snapshot.season_profile_catalog);
    const setupError = await setupPortfolio(currency, cleaned, riskMode, drawdownPolicy);
    if (setupError) setError(setupError);
  };

  return <>
    <section className="page-heading setup-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> First paper season</span><h1>Choose the bankroll. Start when ready.</h1><p>Nothing trades on a fresh install until you create the virtual bankroll and press Start.</p></div>
      <div className={`mode-chip ${snapshot.demo_mode ? "demo" : "live"}`}><span />{snapshot.demo_mode ? "Synthetic demo market" : "Solana mainnet paper feed"}</div>
    </section>
    <article className="card setup-card">
      <div className="setup-intro"><strong>Virtual starting balance</strong><p>This is paper money only. No wallet, seed phrase, or real funds are used.</p></div>
      <form onSubmit={(event) => void submit(event)} noValidate aria-busy={busy}>
        <fieldset className="currency-choice" disabled={busy}><legend>Account currency</legend><button type="button" className={currency === "SOL" ? "active" : ""} onClick={() => chooseCurrency("SOL")} aria-pressed={currency === "SOL"} aria-label="Use SOL for paper bankroll"><strong>SOL</strong><small>Native Solana accounting</small></button><button type="button" className={currency === "USDC" ? "active" : ""} onClick={() => chooseCurrency("USDC")} aria-pressed={currency === "USDC"} aria-label="Use USDC for paper bankroll"><strong>USDC</strong><small>Dollar-denominated accounting</small></button></fieldset>
        <fieldset className="risk-setup-choice" disabled={busy}><legend>First-season personality</legend><div>{RISK_MODES.map((mode) => {
          const profile = snapshot.season_profile_catalog.find((item) => item.risk_mode === mode) ?? null;
          return <button type="button" role="radio" aria-checked={riskMode === mode} className={riskMode === mode ? "active" : ""} onClick={() => setRiskMode(mode)} key={mode}><strong>{riskModeLabel(mode)}</strong><span>{riskCopy(mode)}</span><small>{profileLimitSummary(profile)}</small></button>;
        })}</div><small><ShieldCheck size={13} /> Structural, mint, route, stale-data and executable-market safety stay active in every personality.</small></fieldset>
        <details className="setup-drawdown-settings"><summary>Advanced: portfolio drawdown halt <ChevronDown size={13} /></summary><div>
          <label><input type="radio" name="setup-drawdown" checked={drawdownKind === "default"} disabled={busy} onChange={() => { setDrawdownKind("default"); setError(null); }} /> Personality default</label>
          <label><input type="radio" name="setup-drawdown" checked={drawdownKind === "custom"} disabled={busy} onChange={() => { setDrawdownKind("custom"); setError(null); }} /> Custom</label>
          {drawdownKind === "custom" && <label className="setup-drawdown-custom"><input aria-label="First season custom drawdown percentage" inputMode="decimal" value={customDrawdown} disabled={busy} onChange={(event) => { setCustomDrawdown(event.target.value); setError(null); }} /><b>%</b></label>}
          <label><input type="radio" name="setup-drawdown" checked={drawdownKind === "disabled"} disabled={busy} onChange={() => { setDrawdownKind("disabled"); setError(null); }} /> Off</label>
        </div><p>Off disables only the portfolio-level halt. Trade exits, exposure, position limits and permanent data safety remain active.</p></details>
        <label className="bankroll-input"><span>Starting amount</span><div><input value={amount} disabled={busy} onChange={(event) => { setAmount(event.target.value); setError(null); }} inputMode="decimal" autoComplete="off" aria-label="Starting amount" aria-describedby={error ? "bankroll-help bankroll-error" : "bankroll-help"} /><strong>{currency}</strong></div><small id="bankroll-help">You can reset the paper season later to choose a different amount or currency.</small></label>
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
  const [layout, setLayout] = useState(loadDecisionsLayout);
  const updateLayout = useCallback((update: (current: DecisionsLayoutPreferences) => DecisionsLayoutPreferences) => {
    setLayout((current) => {
      const next = update(current);
      saveDecisionsLayout(next);
      return next;
    });
  }, []);
  const toggleGroup = useCallback((group: DecisionGroupKey) => {
    updateLayout((current) => {
      const expandedGroups = new Set(current.expandedGroups);
      if (expandedGroups.has(group)) expandedGroups.delete(group);
      else expandedGroups.add(group);
      return { expandedGroups };
    });
  }, [updateLayout]);
  useEffect(() => {
    const syncLayout = (event: StorageEvent) => {
      if (event.key === DECISIONS_LAYOUT_KEY || event.key === null) {
        setLayout(loadDecisionsLayout());
      }
    };
    window.addEventListener("storage", syncLayout);
    return () => window.removeEventListener("storage", syncLayout);
  }, []);
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
          open={layout.expandedGroups.has("best")}
          onToggle={() => toggleGroup("best")}
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
          open={layout.expandedGroups.has("passed")}
          onToggle={() => toggleGroup("passed")}
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
          open={layout.expandedGroups.has("earlier")}
          onToggle={() => toggleGroup("earlier")}
          emptyCopy="No expired checkpoints yet."
          viewAsOfMs={viewAsOfMs}
        />
      </div>
    </>
  );
}

function DecisionGroup({ id, title: heading, subtitle, decisions, explain, explainingId, selectedDecisionId, toggleDetails, open, onToggle, ranked = false, emptyCopy, viewAsOfMs }: {
  id: string;
  title: string;
  subtitle: string;
  decisions: Decision[];
  explain: (decision: Decision) => Promise<void>;
  explainingId: string | null;
  selectedDecisionId: string | null;
  toggleDetails: (decision: Decision) => void;
  open: boolean;
  onToggle: () => void;
  ranked?: boolean;
  emptyCopy: string;
  viewAsOfMs: number;
}) {
  return (
    <section className={`decision-group ${open ? "open" : ""}`}>
      <button className="decision-group-toggle" onClick={onToggle} aria-expanded={open} aria-controls={id}>
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

function LearningDisclosure({ id, title: heading, subtitle, summary, children, open: controlledOpen, onToggle }: {
  id: string;
  title: string;
  subtitle: string;
  summary: string;
  children: React.ReactNode;
  open?: boolean;
  onToggle?: () => void;
}) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const toggle = onToggle ?? (() => setLocalOpen((value) => !value));
  return <section className={`learning-disclosure ${open ? "open" : ""}`}>
    <button
      className="learning-disclosure-toggle"
      type="button"
      aria-expanded={open}
      aria-controls={id}
      aria-label={`${open ? "Hide" : "Show"} ${heading.toLowerCase()}`}
      onClick={toggle}
    >
      <span><strong>{heading}</strong><small>{subtitle}</small></span>
      <span className="learning-disclosure-meta"><b>{summary}</b><ChevronDown size={17} /></span>
    </button>
    {open && <div className="learning-disclosure-body" id={id}>{children}</div>}
  </section>;
}

function readinessValue(gate: ReadinessGate, value: number | boolean | null): string {
  if (value === null) return "Collecting";
  if (gate.unit === "boolean") return value ? "Ready" : "Not ready";
  if (typeof value !== "number") return String(value);
  if (gate.unit === "fraction") return percent(value);
  if (gate.unit === "milliseconds") return value >= 1_000 ? duration(value / 1_000) : `${Math.round(value)} ms`;
  if (gate.unit === "count") return Math.round(value).toLocaleString();
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function ReadinessGates({ gates, emptyCopy }: { gates: ReadinessGate[]; emptyCopy: string }) {
  if (!gates.length) {
    return <p className="readiness-empty"><ShieldCheck size={14} />{emptyCopy}</p>;
  }
  const passed = gates.filter((gate) => gate.state === "passed").length;
  return <div className="readiness-gates">
    <div className="readiness-heading"><strong>{passed} / {gates.length} proof gates</strong><small>Reported by the engine; next evaluation timing is separate.</small></div>
    <div className="readiness-list">
      {gates.map((gate) => <div className={`readiness-row state-${gate.state}`} key={gate.id} title={gate.detail}>
        <span className="readiness-icon" aria-hidden="true">{gate.state === "passed" ? <Check size={13} /> : <span />}</span>
        <span><strong>{gate.label}</strong><small>{gate.detail}</small></span>
        <b>{readinessValue(gate, gate.current)} <em>{gate.comparison} {readinessValue(gate, gate.target)}</em></b>
      </div>)}
    </div>
  </div>;
}

const CHALLENGER_SKILL_LABELS: Record<ChallengerChampionEvent["skill"], string> = {
  entry: "Entry selection",
  manipulation: "Manipulation defence",
  sizing: "Position sizing",
  exit: "Exit timing",
};

function championEventTitle(event: ChallengerChampionEvent): string {
  if (event.kind === "first_champion") return "First Champion qualified";
  if (event.kind === "promoted") return "New Champion earned";
  if (event.kind === "defended") return "Champion defended";
  return "No safe winner yet";
}

function championEventDetail(event: ChallengerChampionEvent): string {
  if (event.kind === "first_champion") {
    return `${CHALLENGER_SKILL_LABELS[event.skill]} established its first best-proved policy.`;
  }
  if (event.kind === "promoted") {
    return `${compact(event.common_usable_count)} shared outcomes${event.uplift_lower_bound === null ? "" : ` · ${percentSigned(event.uplift_lower_bound)} conservative edge`}.`;
  }
  if (event.kind === "defended") {
    return `${compact(event.common_usable_count)} shared outcomes · the contender did not beat the saved Champion safely.`;
  }
  return `${compact(event.common_usable_count)} shared outcomes · neither policy proved a safe advantage.`;
}

function modelFamilyLabel(family?: "linear" | "xgboost" | "deterministic"): string {
  if (family === "xgboost") return "Nonlinear XGBoost";
  if (family === "deterministic") return "Deterministic policy";
  return "Linear learner";
}

function LearningLab({ snapshot, setLearningMode, setAiMode, setCoachResearch, setCoachContribution, busy, activeView, setActiveView, expandedSections, toggleSection, milestones, hasUnseenMilestones }: {
  snapshot: Snapshot;
  setLearningMode: (mode: LearningMode) => Promise<void>;
  setAiMode: (mode: AiDecisionMode) => Promise<void>;
  setCoachResearch: (enabled: boolean) => Promise<void>;
  setCoachContribution: (enabled: boolean) => Promise<void>;
  busy: boolean;
  activeView: LearningViewKey;
  setActiveView: (view: LearningViewKey) => void;
  expandedSections: Set<LearningSectionKey>;
  toggleSection: (section: LearningSectionKey) => void;
  milestones: LearningMilestone[];
  hasUnseenMilestones: boolean;
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
    active: "Qualified Challenger skills act only inside their separate safety gates.",
  }[learning.state];
  const stateCopy = liveHealth.state === "suspended"
    ? "A previously active learner showed confident harm on later unseen outcomes, so the baseline automatically took control."
    : !learning.collecting_from_current_source && learning.mode !== "off"
      ? "Demo stays separate. Switch to Solana mainnet when you want to collect live-paper lessons."
      : normalStateCopy;
  const canActivate = learning.activation_available && learning.collecting_from_current_source;
  const holdReview = learning.recommended_hold_seconds[snapshot.risk_mode];
  const timing = learning.hold_timing_validation[snapshot.risk_mode];
  const challengerGates = learning.qualification_gates ?? [];
  const challengerPassed = learning.qualification_passed
    ?? challengerGates.filter((gate) => gate.state === "passed").length;
  const challengerTotal = learning.qualification_total ?? challengerGates.length;
  const skillStatuses = learning.skills ?? [];
  const championJourney = learning.champion_journey ?? [];
  const evidenceLanes = learning.evidence_lanes ?? [];
  const baselineScorecard = learning.baseline_scorecard;
  const baselinePolicy = baselineScorecard?.policy;
  const latestChampionEvent = championJourney[0] ?? null;
  const commonForwardMinimum = learning.challenger_common_forward_minimum ?? 30;
  const minimumTournamentAvailability = learning.challenger_minimum_availability ?? 0.70;
  const activeSkillCount = Math.max(1, Object.keys(learning.active_skill_versions ?? {}).length);
  const baselineState = learning.mode === "active" ? "Core + bounded learner" : "In control";
  const challengerState = liveHealth.state === "suspended"
    ? "Suspended safely"
    : learning.mode === "off"
      ? "Off"
      : learning.mode === "active"
        ? "Active"
        : title(learning.state);
  const coachState = snapshot.coach.mode === "off"
    ? snapshot.ai_lab.mode === "off" ? "Off" : "Paused"
    : title(snapshot.coach.state);
  const views: Array<{ key: LearningViewKey; label: string; summary: string }> = [
    { key: "overview", label: "Overview", summary: "Team status and milestones" },
    { key: "baseline", label: "Baseline", summary: baselineState },
    { key: "challenger", label: "Challenger", summary: challengerState },
    { key: "coach", label: "AI Coach", summary: coachState },
    { key: "reviews", label: "Shadow Reviews", summary: snapshot.ai_lab.mode === "off" ? "Off" : "Shadow" },
    { key: "safety", label: "Safety", summary: `${learning.guardrails.length} boundaries` },
  ];
  const learningTabListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const activeTab = learningTabListRef.current?.querySelector<HTMLElement>(
      `[data-learning-view="${activeView}"]`,
    );
    activeTab?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activeView]);
  const selectAdjacentView = (event: React.KeyboardEvent<HTMLButtonElement>, current: LearningViewKey) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = views.findIndex((view) => view.key === current);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? views.length - 1
        : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + views.length) % views.length;
    const next = views[nextIndex]!;
    setActiveView(next.key);
    window.requestAnimationFrame(() => document.getElementById(`learning-tab-${next.key}`)?.focus());
  };

  return <>
    <section className="page-heading learning-heading">
      <div><span className="eyebrow"><GraduationCap size={14} /> Learning Lab</span><h1>Three players. One safely bounded team.</h1><p>{stateCopy}</p></div>
    </section>

    <div ref={learningTabListRef} className="learning-view-tabs" role="tablist" aria-label="Learning Lab sections">
      {views.map((view) => <button
        id={`learning-tab-${view.key}`}
        key={view.key}
        data-learning-view={view.key}
        type="button"
        role="tab"
        aria-selected={activeView === view.key}
        aria-controls="learning-view-panel"
        tabIndex={activeView === view.key ? 0 : -1}
        title={view.summary}
        onClick={() => setActiveView(view.key)}
        onKeyDown={(event) => selectAdjacentView(event, view.key)}
      ><span>{view.label}</span>{view.key === "overview" && hasUnseenMilestones && <i aria-label="New learning milestone" />}</button>)}
    </div>

    <section className={`learning-view-panel view-${activeView}`} id="learning-view-panel" role="tabpanel" aria-labelledby={`learning-tab-${activeView}`}>
    {activeView === "overview" && <>
      {milestones.length > 0 && <section className="learning-milestones" aria-label="Latest learning milestones">
        <div><Sparkles size={16} /><strong>Latest learning milestones</strong><small>Proof progress, never a promise of profit</small></div>
        {milestones.slice(0, 3).map((milestone) => <article className={`tone-${milestone.tone}`} key={milestone.id}><span /><div><strong>{milestone.title}</strong><small>{milestone.detail}</small></div></article>)}
      </section>}
      <section className="learning-team-strip" aria-label="Learning team status">
        <button type="button" onClick={() => setActiveView("baseline")}><span>Fast Baseline</span><strong>{baselineState}</strong><small>Deterministic · {title(snapshot.risk_mode)} · safe fallback</small><em>Open Baseline <ChevronRight size={12} /></em></button>
        <button type="button" onClick={() => setActiveView("challenger")}><span>Statistical Challenger</span><strong>{challengerState}</strong><small>{challengerTotal ? `${challengerPassed} / ${challengerTotal} proof gates` : "Server proof is collecting"}</small><em>Open Challenger <ChevronRight size={12} /></em></button>
        <button type="button" onClick={() => setActiveView("coach")}><span>Local AI Lab</span><strong>{snapshot.ai_lab.mode === "off" ? "Off" : "Shadow"} · {coachState}</strong><small>Coach + saved decision reviews · zero influence</small><em>Open AI Coach <ChevronRight size={12} /></em></button>
      </section>
      <div className="learning-overview-note"><ShieldCheck size={15} /><span><strong>The Baseline acts; the others must earn trust.</strong><small>Challenger and local AI evidence stays separate, measurable, bounded, and reversible.</small></span></div>
    </>}

    {activeView === "baseline" && <>
      <div className="learning-view-heading"><div><span>Fast Baseline</span><h2>The deterministic trader and permanent safe fallback</h2></div><strong>{baselineState} · {title(snapshot.risk_mode)}</strong></div>
      <article className="card baseline-overview">
        <div><Gauge size={19} /><span><strong>Acts on fresh market evidence</strong><small>Scores entries and manages exits without waiting for local AI.</small></span></div>
        <div><ShieldCheck size={19} /><span><strong>Does not fit itself</strong><small>The Challenger studies measured outcomes separately; the Baseline stays predictable.</small></span></div>
        <div><RotateCcw size={19} /><span><strong>Always available as fallback</strong><small>If learned behavior becomes harmful or unverifiable, control returns here automatically.</small></span></div>
      </article>
      {baselinePolicy && <section className="stats-grid learning-stats" aria-label="Current Baseline evidence">
        <Stat label="Independent entries" value={compact(baselinePolicy.usable_count)} hint={`${compact(baselinePolicy.observed_count)} outcomes observed`} />
        <Stat label="Median outcome" value={baselinePolicy.median_return === null ? "Collecting" : percentSigned(baselinePolicy.median_return)} hint="After modeled entry, exit and fees" tone={baselinePolicy.median_return === null ? undefined : baselinePolicy.median_return >= 0 ? "good" : "bad"} />
        <Stat label="Conservative floor" value={baselinePolicy.conservative_return === null ? "Collecting" : percentSigned(baselinePolicy.conservative_return)} hint="95% confidence-adjusted mean" tone={baselinePolicy.conservative_return === null ? undefined : baselinePolicy.conservative_return >= 0 ? "good" : "bad"} />
        <Stat label="Outcome coverage" value={percent(baselinePolicy.availability_fraction)} hint="Unknown exits stay unknown" />
      </section>}
    </>}

    {activeView === "challenger" && <>
      <div className="learning-view-heading"><div><span>Statistical Challenger</span><h2>Learns from forward, fee-inclusive outcomes without changing the Baseline</h2></div><strong>{learning.mode === "active" ? "Active" : learning.mode === "off" ? "Off" : "Shadow"} · {challengerState}</strong></div>
      {snapshot.demo_mode && learning.demo_excluded && <div className="learning-demo-note"><ShieldCheck size={17} /><div><strong>Demo experience stays separate</strong><p>Synthetic tokens can never train or activate the live learner.</p></div></div>}

      <div className="challenger-controls">
        <div><strong>Challenger control</strong><small>The next evaluation is not an unlock. Every proof gate must pass independently.</small></div>
        <div className="learning-controls">
          {learning.mode === "off"
            ? <button className="button learning-primary" onClick={() => void setLearningMode("shadow")} disabled={busy}><Play size={15} /> Start Challenger Shadow</button>
            : <button className="button ghost" onClick={() => void setLearningMode("off")} disabled={busy}><Pause size={15} /> Pause Challenger learning</button>}
          {learning.mode === "active"
            ? <button className="button learning-primary" onClick={() => void setLearningMode("shadow")} disabled={busy}><ShieldCheck size={15} /> Return Challenger to Shadow</button>
            : <button className="button learning-primary" onClick={() => void setLearningMode("active")} disabled={busy || !canActivate} title={!learning.collecting_from_current_source ? "Switch to Solana mainnet before activation" : learning.activation_available ? "Use the newest qualified challenger" : "Every server-side proof and current coverage gate must pass first"}><TrendingUp size={15} /> Use qualified Challenger</button>}
        </div>
      </div>

      <section className="card learning-progress-card">
        <div><span className={`learning-state state-${learning.state}`} /> <strong>{title(learning.state)}</strong><small>{learning.mode === "active" ? `${activeSkillCount} bounded skill${activeSkillCount === 1 ? "" : "s"} active · ${duration(holdReview)} hold review` : `Baseline remains in control · ${duration(holdReview)} hold review`}</small></div>
        <div className="learning-progress-copy"><strong>{latest ? `${learning.usable_outcome_count} usable` : `${learning.usable_outcome_count} / ${learning.minimum_training_samples}`}</strong><small>{latest ? `Minimum ${learning.minimum_training_samples} met · ${nextChallengerCopy}` : "usable five-minute outcomes before first training"}</small></div>
        <div className="learning-progress" role="progressbar" aria-label={progressLabel} aria-valuemin={0} aria-valuemax={progressMax} aria-valuenow={progressNow}><span style={{ width: `${progress * 100}%` }} /></div>
      </section>

      <section className="stats-grid learning-stats">
        <Stat label="Tokens remembered" value={compact(learning.observation_count)} hint={`Newest ${compact(learning.model_window_observations)} train · ${compact(learning.retained_observation_limit)} retained`} />
        <Stat label="Usable outcomes" value={compact(learning.usable_outcome_count)} hint="After entry, exit and fees" />
        <Stat label="Still unfolding" value={compact(learning.pending_count)} hint="Measured at 1, 5, 10, 15 and 20 minutes" />
        <Stat label="Unknown outcomes" value={compact(learning.unavailable_outcome_count)} hint="No fake P/L; unavailable exits reduce horizon utility" />
      </section>

      {skillStatuses.length > 0 && <section className="challenger-skill-grid" aria-label="Challenger skills">
        {skillStatuses.map((skill) => {
          const passed = skill.gates.filter((gate) => gate.state === "passed").length;
          const candidate = skill.testing_candidate ?? skill.latest_candidate;
          const latestSkillEvent = championJourney.find((event) => event.skill === skill.skill);
          const waitingGate = skill.gates.find((gate) => gate.state !== "passed") ?? null;
          const contenderState = skill.testing_version
            ? "Testing"
            : !candidate
              ? "Collecting"
              : candidate.version === skill.champion?.version
                ? "Champion"
                : candidate.qualified
                  ? "Qualified"
                  : "Building proof";
          const tournamentAvailability = typeof skill.tournament.availability_fraction === "number"
            ? skill.tournament.availability_fraction
            : null;
          const battleProgress = skill.testing_version
            ? skill.common_forward_count >= commonForwardMinimum
              && tournamentAvailability !== null
              && tournamentAvailability < minimumTournamentAvailability
              ? `${percent(tournamentAvailability)} coverage · needs ${percent(minimumTournamentAvailability)}`
              : `${skill.common_forward_count} / ${commonForwardMinimum} shared outcomes`
            : latestSkillEvent
              ? championEventTitle(latestSkillEvent)
              : candidate
                ? `${compact(candidate.sample_count)} outcomes`
                : "Independent proof";
          return <article className={`card challenger-skill-card skill-${skill.state}`} key={skill.skill}>
            <header><div><span>{skill.skill}</span><strong>{skill.label}</strong></div><b>{title(skill.state)}</b></header>
            <p>{skill.skill === "entry" ? "Selects among entries the Baseline already approved." : skill.skill === "manipulation" ? "Learns recurring adversarial flow patterns and may only veto." : skill.skill === "sizing" ? "Tests bounded 0.5x–2x sizes under the same executable route." : "May move the normal review earlier; hard exits never move."}</p>
            <div className="challenger-skill-facts">
              <span><small>Contender</small><strong title={candidate?.version}>{candidate?.codename ?? contenderState}</strong>{candidate && <em>{modelFamilyLabel(candidate.model_family)}</em>}</span>
              <span><small>Best proved</small><strong title={skill.champion?.version}>{skill.champion ? `${skill.champion_generation ? `Champion v${skill.champion_generation} · ` : ""}${skill.champion.codename ?? "Champion"}` : "None yet"}</strong>{skill.champion && <em>{modelFamilyLabel(skill.champion.model_family)}</em>}</span>
              <span><small>Influence</small><strong>{skill.active_version ? "Active" : skill.state === "suspended" ? "Suspended" : "Shadow"}</strong></span>
            </div>
            {!candidate?.qualified && waitingGate && <p className="challenger-waiting"><span>Waiting for evidence</span>{waitingGate.label} · {waitingGate.detail}</p>}
            {(candidate || skill.champion) && <details className="challenger-artifact-details">
              <summary>Artifact details</summary>
              <div>
                {candidate && <span><small>Contender recipe</small><strong>{modelFamilyLabel(candidate.model_family)} · {candidate.recipe_version ?? "legacy recipe"}</strong></span>}
                {candidate && <span><small>Evidence split</small><strong>{compact(candidate.training_count)} train · {compact(candidate.validation_count)} validation</strong></span>}
                {skill.champion && <span><small>Champion recipe</small><strong>{modelFamilyLabel(skill.champion.model_family)} · {skill.champion.recipe_version ?? "legacy recipe"}</strong></span>}
                {candidate?.training_cutoff_at && <span><small>Frozen cutoff</small><strong>{shortDate(candidate.training_cutoff_at)}</strong></span>}
              </div>
            </details>}
            <footer><span>{passed} / {skill.gates.length} skill gates</span><span>{battleProgress}{(skill.pending_versions?.length ?? 0) > 0 ? ` · ${skill.pending_versions!.length} queued` : ""}</span></footer>
          </article>;
        })}
      </section>}

      <LearningDisclosure
        id="champion-journey-details"
        title="Champion journey"
        subtitle="Recent honest promotions and defences for this personality"
        summary={latestChampionEvent ? championEventTitle(latestChampionEvent) : "Waiting for first Champion"}
        open={expandedSections.has("champion_journey")}
        onToggle={() => toggleSection("champion_journey")}
      >
        {championJourney.length > 0
          ? <ol className="champion-journey-list" aria-label="Recent Challenger Champion milestones">
            {championJourney.slice(0, 8).map((event) => <li key={event.event_id}>
              <span className={`champion-journey-icon event-${event.kind}`} aria-hidden="true">{event.kind === "promoted" || event.kind === "first_champion" ? <Trophy size={14} /> : <ShieldCheck size={14} />}</span>
              <span><small>{CHALLENGER_SKILL_LABELS[event.skill]}</small><strong title={event.champion_version}>{event.champion_generation ? `Champion v${event.champion_generation} · ` : ""}{event.champion_codename ? `${event.champion_codename} · ` : ""}{championEventTitle(event)}</strong><em>{championEventDetail(event)}</em></span>
              <time dateTime={event.occurred_at}>{shortDate(event.occurred_at)}</time>
            </li>)}
          </ol>
          : <EmptyState icon={<History size={22} />} title="No recorded Champion battles yet" copy="Existing Champions remain valid. Honest journey history begins with the next completed challenge; Signal Arcade does not invent past battles." />}
        <p className="champion-journey-note"><ShieldCheck size={13} />Season profit stays in Results. A Champion means safer forward proof, never guaranteed profit.</p>
      </LearningDisclosure>

      <LearningDisclosure
        id="challenger-readiness-details"
        title="Road to influence"
        subtitle="Authoritative proof gates from the engine"
        summary={challengerTotal ? `${challengerPassed} / ${challengerTotal} passed` : "Collecting"}
        open={expandedSections.has("challenger_proof")}
        onToggle={() => toggleSection("challenger_proof")}
      >
        <ReadinessGates gates={challengerGates} emptyCopy="This running backend predates detailed proof gates; qualification remains safely server-controlled." />
      </LearningDisclosure>

      <LearningDisclosure
        id="learning-evidence-details"
        title="Learning evidence"
        subtitle="Forward validation and the associations currently being tested"
        summary={latest ? latest.qualified ? "Model proof passed" : "Challenger testing" : "Collecting"}
        open={expandedSections.has("learning_evidence")}
        onToggle={() => toggleSection("learning_evidence")}
      >
        {evidenceLanes.length > 0 && <>
          <div className="learning-evidence-lanes" role="region" aria-label="Separated learning evidence lanes">
            {evidenceLanes.map((lane) => <article key={lane.id} className={`evidence-lane lane-${lane.qualification_role}`}>
              <header><strong>{lane.label}</strong><span>{lane.qualification_role === "authoritative" ? "Can qualify" : lane.qualification_role === "proposal" ? "Proposes" : "Audit only"}</span></header>
              <p>{lane.purpose}</p>
              <div><b>{compact(lane.usable_count)} usable</b><small>{compact(lane.observed_count)} observed · {compact(lane.pending_count)} unfolding · {compact(lane.unavailable_count)} unknown</small></div>
            </article>)}
          </div>
          <p className="evidence-generation-note"><ShieldCheck size={13} />
            {learning.evidence_contract?.collection_started_at
              ? <>Current retained proof begins {shortDate(learning.evidence_contract.collection_started_at)}. Older evidence remains preserved but cannot silently qualify this policy.</>
              : <>Current proof generation is waiting for its first actionable Baseline entry. Older evidence remains preserved but cannot silently qualify it.</>}
          </p>
        </>}
        <div className="learning-grid">
          <article className="card learning-card">
            <SectionHeader title="Forward test" subtitle="Newest observations are never used to fit the challenger being judged" />
            {latest ? <div className="learning-metrics">
              <div><span>Model proof</span><strong className={latest.qualified ? "positive" : "negative"}>{latest.qualified ? "Passed" : "Not yet"}</strong></div>
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
              <div><span>Live health guard</span><strong className={liveHealth.state === "healthy" ? "positive" : liveHealth.state === "suspended" || liveHealth.state === "degraded" ? "negative" : ""}>{liveHealth.state === "healthy" && liveHealth.estimated_uplift !== null ? `${percentSigned(liveHealth.estimated_uplift)} estimated` : liveHealth.state === "collecting" ? `${liveHealth.usable_count} / ${liveHealth.minimum_samples}` : liveHealth.state === "suspended" ? "Returned to Shadow" : title(liveHealth.state)}</strong></div>
            </div> : <EmptyState icon={<GraduationCap size={22} />} title="No model fitted yet" copy="Signal Arcade records outcomes but refuses to fit a learner from a tiny sample." />}
          </article>
          <article className="card learning-card">
            <SectionHeader title="What it is noticing" subtitle="Associations, not universal claims about every token" />
            {learning.lessons.length ? <div className="lesson-list">{learning.lessons.map((lesson) => <div key={lesson.feature}><span className={lesson.effect === "helped" ? "lesson-up" : "lesson-down"}>{lesson.effect === "helped" ? "↑" : "↓"}</span><div><strong>{title(lesson.label)}</strong><small>Associated with {lesson.effect === "helped" ? "better" : "worse"} fee-inclusive outcomes · strength {Math.abs(lesson.coefficient).toFixed(3)}</small></div></div>)}</div> : <EmptyState icon={<TrendingUp size={22} />} title="Lessons need time" copy="The first challenger appears only after enough live, forward five-minute outcomes exist." />}
          </article>
        </div>
      </LearningDisclosure>
    </>}

    {activeView === "coach" && <>
      <div className="learning-view-heading"><div><span>AI Coach</span><h2>Slow, asynchronous experiments that can never delay a trade</h2></div><strong>{snapshot.ai_lab.mode === "off" ? "Off" : `${coachState} · Shadow`}</strong></div>
      <div className="local-ai-boundary"><Bot size={17} /><div><strong>Research director, never a hidden trader</strong><small>The Coach studies saved outcomes. With your permission, a supported idea may enter a normal Challenger tournament; it can never bypass proof or act directly.</small></div></div>
      <CoachRoom snapshot={snapshot} setCoachResearch={setCoachResearch} setCoachContribution={setCoachContribution} busy={busy} expandedSections={expandedSections} toggleSection={toggleSection} />
    </>}

    {activeView === "reviews" && <>
      <div className="learning-view-heading"><div><span>Shadow Decision Reviews</span><h2>Saved decision explanations and counterfactual evidence</h2></div><strong>{snapshot.ai_lab.mode === "off" ? "Off" : "Shadow · no influence"}</strong></div>
      <div className="local-ai-boundary"><Bot size={17} /><div><strong>Completely off the live path</strong><small>Reviews use normalized saved evidence after decisions. They cannot create, resize, delay, or alter a trade.</small></div></div>
      <AiDecisionLabCard snapshot={snapshot} setAiMode={setAiMode} busy={busy} />
    </>}

    {activeView === "safety" && <>
      <div className="learning-view-heading"><div><span>Permanent boundaries</span><h2>Learning can become selective; it cannot become reckless</h2></div><strong>{learning.guardrails.length} always active</strong></div>
      <article className="card learning-guardrails"><div>{learning.guardrails.map((guardrail) => <span key={guardrail}><ShieldCheck size={15} />{guardrail}</span>)}</div></article>
    </>}
    </section>
  </>;
}

function CoachRoom({ snapshot, setCoachResearch, setCoachContribution, busy, expandedSections, toggleSection }: {
  snapshot: Snapshot;
  setCoachResearch: (enabled: boolean) => Promise<void>;
  setCoachContribution: (enabled: boolean) => Promise<void>;
  busy: boolean;
  expandedSections: Set<LearningSectionKey>;
  toggleSection: (section: LearningSectionKey) => void;
}) {
  const coach = snapshot.coach;
  const current = coach.recent_hypotheses.find((item) => item.context_active);
  const active = coach.mode === "shadow" && current?.state === "testing";
  const progress = current
    ? Math.min(1, current.forward_usable_count / current.minimum_forward_samples)
    : 0;
  const stateCopy: Record<typeof coach.state, string> = {
    off: snapshot.ai_lab.mode === "off"
      ? "Enable AI Shadow when you want the local coach to review completed evidence."
      : "Coach research is paused. Saved Shadow reviews and completed studies remain available.",
    waiting: coach.paused_reason === "protecting_open_positions"
      ? "The coach is waiting while the engine manages open positions."
      : coach.paused_reason === "protecting_market_throughput"
        ? "Market work has priority. Coaching will resume after the event queue settles."
        : coach.paused_reason === "ollama_busy"
          ? "Ollama is busy with another optional task; coaching will retry automatically."
          : "Waiting for enough new measured outcomes to review another idea.",
    reviewing: "The local model is comparing bounded experiments in the background.",
    testing: "A coaching idea is collecting only outcomes created after it was proposed.",
    promising: "This idea survived independent forward proof. It still cannot trade directly.",
    inconclusive: "The bounded study ended without enough reliable evidence to support it.",
    not_supported: "New forward evidence did not support this coaching idea.",
  };
  const latestReview = coach.recent_reviews[0];
  const coachGates = coach.qualification_gates ?? [];
  const coachPassed = coach.qualification_passed ?? coachGates.filter((gate) => gate.state === "passed").length;
  const coachTotal = coach.qualification_total ?? coachGates.length;
  const lanes = coach.research_lanes ?? [];
  const currentSkill = current?.skill
    ?? (current?.kind === "earlier_review" ? "exit" : current?.kind === "sizing_multiplier" ? "sizing" : current?.kind === "manipulation_veto" ? "manipulation" : "entry");
  const contributionEnabled = coach.contribution_enabled ?? false;
  const contributionReady = coach.contribution_ready ?? current?.contribution_state === "ready";
  const contributionCandidate = coach.contribution_candidate;
  const researchEnabled = coach.research_enabled ?? coach.mode === "shadow";
  const notebook = coach.recent_hypotheses.filter((item) => item.context_active);
  return <article className="card coach-card">
    <div className="coach-heading">
      <SectionHeader title="AI Coach" subtitle="Slow, allowlisted experiments for the fast engine · Shadow-only" />
      <div className="coach-heading-actions"><span className={`coach-state state-${coach.state}`}>{title(coach.state)}</span><button className="button subtle" disabled={busy || snapshot.ai_lab.mode === "off"} onClick={() => void setCoachResearch(!researchEnabled)}>{researchEnabled ? "Pause research" : "Start research"}</button></div>
    </div>
    <div className="coach-summary">
      <div><span>Coach mode</span><strong>{coach.mode === "shadow" ? "Watching" : snapshot.ai_lab.mode === "off" ? "Off" : "Paused"}</strong><small>{snapshot.ai_lab.mode === "off" ? "No local model work" : coach.mode === "off" ? "Research can resume without losing evidence" : coach.worker_running ? "Background worker healthy" : "No AI coach calls"}</small></div>
      <div><span>Influence</span><strong>Research only</strong><small>{contributionEnabled ? "Proved ideas may challenge · never act directly" : "Cannot change entries, exits, sizing or safety"}</small></div>
      <div><span>Next review</span><strong>{active ? "Forward test active" : coach.outcomes_until_review === 0 ? "When the engine is quiet" : `${coach.outcomes_until_review} outcomes`}</strong><small>{coach.outcomes_seen.toLocaleString()} fee-inclusive outcomes seen</small></div>
    </div>
    <p className="coach-state-copy"><Bot size={15} />{stateCopy[coach.state]}</p>
    {lanes.length > 0 && <section className="coach-lane-grid" aria-label="AI Coach research lanes">
      {lanes.map((lane) => <article key={lane.skill} className={`coach-lane lane-${lane.state}`}>
        <span>{lane.label}</span><strong>{title(lane.state)}</strong>
        <small>{lane.current_title || "Watching measured outcomes"}</small>
        <em>{lane.supported_studies} supported · {lane.studies} studied</em>
      </article>)}
    </section>}
    {current ? <div className="coach-experiment">
      <div className="coach-experiment-head">
        <div><span>{CHALLENGER_SKILL_LABELS[currentSkill]} research</span><strong>{current.title}</strong><small>{current.rationale}</small></div>
        <span className={`coach-experiment-state state-${current.state}`}>{title(current.state)}</span>
      </div>
      <div className="coach-proof-grid">
        <div><span>Historical screen</span><strong>{current.discovery_uplift_lower_bound === null ? "Unknown" : `${percentSigned(current.discovery_uplift_lower_bound)} floor`}</strong><small>{current.discovery_usable_count} usable · could only propose</small></div>
        <div><span>New forward evidence</span><strong>{current.forward_mean_uplift === null ? "Collecting" : percentSigned(current.forward_mean_uplift)}</strong><small>{current.forward_usable_count} / {current.minimum_forward_samples} usable</small></div>
        <div><span>Outcome coverage</span><strong>{percent(current.forward_availability_fraction)}</strong><small>Needs {percent(current.minimum_availability_fraction)}</small></div>
        <div><span>Independent seasons</span><strong>{current.forward_season_count} / {coach.minimum_forward_seasons}</strong><small>{coach.minimum_samples_per_season ?? 10}+ usable outcomes in each</small></div>
      </div>
      <div className="coach-progress" role="progressbar" aria-label="Coach forward-test progress" aria-valuemin={0} aria-valuemax={current.minimum_forward_samples} aria-valuenow={current.forward_usable_count}><span style={{ width: `${progress * 100}%` }} /></div>
    </div> : <div className="coach-empty">
      <BrainCircuit size={21} />
      <div><strong>{latestReview?.selected_candidate_id === "none" ? "No experiment cleared screening yet" : "The coach is observing"}</strong><small>{latestReview?.summary || "It will review compact, normalized outcomes without placing work on the live decision path."}</small></div>
    </div>}
    {coach.last_error && <p className="coach-safe-error"><ShieldCheck size={14} />Optional coaching is waiting after a local-model issue; the engine was unaffected.</p>}

    <LearningDisclosure id="coach-notebook" title="Research notebook" subtitle="Honest supported, rejected and inconclusive studies" summary={notebook.length ? `${notebook.length} recent ${notebook.length === 1 ? "study" : "studies"}` : "Waiting for first study"} open={expandedSections.has("coach_notebook")} onToggle={() => toggleSection("coach_notebook")}>
      {notebook.length > 0 ? <ol className="coach-notebook-list">
        {notebook.slice(0, 8).map((item) => <li key={item.hypothesis_id}>
          <span className={`state-${item.state}`}><BrainCircuit size={14} /></span>
          <div><small>{CHALLENGER_SKILL_LABELS[item.skill ?? (item.kind === "earlier_review" ? "exit" : "entry")]}</small><strong>{item.title}</strong><em>{title(item.state)} · {item.forward_usable_count} usable forward outcomes</em></div>
          <time dateTime={item.updated_at}>{shortDate(item.updated_at)}</time>
        </li>)}
      </ol> : <EmptyState icon={<BrainCircuit size={22} />} title="The notebook is empty" copy="The Coach will record the first bounded study only after enough fee-inclusive evidence clears screening." />}
    </LearningDisclosure>

    <LearningDisclosure id="coach-contribution" title="Road to contribution" subtitle="Coach proof first, then a completely new Challenger battle" summary={current?.contribution_state === "handed_off" ? "Contender handed off" : contributionEnabled ? "Permission on" : contributionReady ? "Permission available" : `${coachPassed} / ${coachTotal || 6} Coach gates`} open={expandedSections.has("coach_contribution")} onToggle={() => toggleSection("coach_contribution")}>
      <div className="coach-contribution-path" aria-label="Coach contribution path"><span>Allowlisted idea</span><ChevronRight size={14} /><span>Coach forward proof</span><ChevronRight size={14} /><span>Challenger contender</span><ChevronRight size={14} /><span>Champion battle</span></div>
      {contributionCandidate && <p className="coach-contribution-candidate"><BrainCircuit size={14} /><span><strong>{CHALLENGER_SKILL_LABELS[contributionCandidate.skill]} idea ready</strong><small>{contributionCandidate.title}{contributionCandidate.state === "waiting_for_champion" ? " · waiting for that skill's first statistical Champion" : ""}</small></span></p>}
      <ReadinessGates gates={coachGates} emptyCopy="No Coach experiment is selected yet, so its independent forward proof has not started." />
      <div className="coach-contribution-control"><div><strong>Allow proved Coach ideas to challenge</strong><small>Permission only hands a supported policy to the existing statistical tournament. It never enables direct AI trading.</small></div><button className={`button ${contributionEnabled ? "ghost" : "learning-primary"}`} disabled={busy || (!contributionEnabled && (snapshot.ai_lab.mode === "off" || !contributionReady))} onClick={() => void setCoachContribution(!contributionEnabled)}>{contributionEnabled ? "Turn contribution off" : "Allow contribution"}</button></div>
      {coachTotal > 0 && <p className="coach-proof-note"><ShieldCheck size={13} />{coachPassed} / {coachTotal} Coach proof gates passed. Challenger tournament evidence begins only after handoff.</p>}
    </LearningDisclosure>

    <LearningDisclosure id="coach-safety" title="Permanent Coach boundaries" subtitle="Performance, authority and data-quality limits" summary={`${coach.guardrails.length} always active`} open={expandedSections.has("coach_safety")} onToggle={() => toggleSection("coach_safety")}>
      <div className="coach-guardrails">{coach.guardrails.map((item) => <span key={item}><ShieldCheck size={13} />{item}</span>)}</div>
    </LearningDisclosure>
  </article>;
}

function AiDecisionLabCard({ snapshot, setAiMode, busy }: {
  snapshot: Snapshot;
  setAiMode: (mode: AiDecisionMode) => Promise<void>;
  busy: boolean;
}) {
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
  const aiGates = qualification.gates ?? [];
  const aiPassed = qualification.passed ?? aiGates.filter((gate) => gate.state === "passed").length;
  const aiTotal = qualification.total ?? aiGates.length;
  const coachGates = snapshot.coach.qualification_gates ?? [];
  const coachPassed = snapshot.coach.qualification_passed ?? coachGates.filter((gate) => gate.state === "passed").length;
  const coachTotal = snapshot.coach.qualification_total ?? coachGates.length;
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
      copy: coachTotal ? `${coachPassed}/${coachTotal} Coach Shadow gates · future` : "Coach proof collecting · future",
      futureHint: "Future update — Coach proof progress is shown above. This stage remains unavailable even after evidence passes, until its bounded influence path is implemented and validated.",
    },
    {
      key: "live-critic",
      label: "Live Critic",
      copy: "No readiness measure yet · future",
      futureHint: "Future update — no Live Critic readiness claim exists yet. It would be considered only after Qualified Coach proves useful, safe, bounded, and reversible.",
    },
  ];
  const recent = lab.recent_assessments.slice(0, 5);
  const displayedMode = lab.mode === "guarded" ? "Qualified Coach (legacy)" : title(lab.mode);
  return <article className="card ai-lab-card">
    <div className="ai-lab-heading">
      <SectionHeader title="Shadow Decision Reviews" subtitle="AI Decision Lab · reviews completed decisions only; Live Critic remains a future stage" />
      <span className={`ai-mode-badge ${lab.mode}`}>{displayedMode}</span>
    </div>
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
    <ReadinessGates gates={aiGates} emptyCopy="This running backend predates detailed AI Shadow evidence gates; later stages still remain unavailable." />
    {aiTotal > 0 && <p className="ai-proof-note"><ShieldCheck size={13} />{aiPassed} / {aiTotal} Shadow evidence gates passed. Qualified Coach remains a future feature even when all are met; Live Critic has no readiness claim yet.</p>}
    {recent.length > 0 && <div className="ai-assessment-list">
      {recent.map((assessment) => <div key={assessment.assessment_id}><span className={`ai-verdict ${assessment.valid ? assessment.verdict ?? "unknown" : "invalid"}`}>{assessment.valid ? title(assessment.verdict ?? "unknown") : aiFailureLabel(assessment.invalid_reason)}</span><div><strong title={tokenSymbolKnown(assessment.symbol) ? undefined : assessment.mint}>{tokenDisplayLabel(assessment.symbol, assessment.mint)}</strong><small>{assessment.valid ? assessment.summary || "Bounded assessment completed" : aiFailureDetail(assessment.invalid_reason)}</small></div><div><strong>{!assessment.valid ? "Ignored safely" : assessment.resolved_at ? assessment.counterfactual_uplift === null ? "No outcome" : `${percentSigned(assessment.counterfactual_uplift)} veto value` : "Measuring…"}</strong><small>{assessment.latency_ms.toLocaleString()} ms</small></div></div>)}
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
  const summaryCurrency = data?.summary.quote_currency ?? data?.rows[0]?.quote_currency;
  const summaryDecimals = data?.summary.quote_decimals ?? data?.rows[0]?.quote_decimals;
  const summaryMoneyReady = Boolean(
    data
    && summaryCurrency
    && typeof summaryDecimals === "number"
    && Number.isInteger(summaryDecimals),
  );
  const openTrades = data?.summary.open_trades
    ?? data?.rows.filter((row) => row.status === "open").length
    ?? 0;
  const availableRows = data?.available_rows
    ?? (data?.sort === "recent" ? data.rows.length : data?.summary.closed_trades)
    ?? 0;
  const hiddenResultRows = Math.max(0, availableRows - (data?.rows.length ?? 0));

  return <>
    <section className="page-heading leaderboard-heading">
      <div><span className="eyebrow"><Trophy size={14} /> Results board</span><h1>{view === "trades" ? "Wins, losses, and the evidence behind them." : "Is the strategy improving each season?"}</h1><p>{view === "trades" ? "Review this season's net-of-fee paper trades, then open the exact saved entry and exit evidence." : "Compare like-for-like bankrolls, profiles, and accounting rules while keeping every season scorecard available."}</p></div>
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
    <p className="results-scope-note"><History size={14} /><span><strong>Current season</strong> Most profit and Most loss rank closed trades; Latest also includes open positions.</span></p>
    {data && <section className="stats-grid leaderboard-stats">
      <Stat label="Closed trades" value={String(data.summary.closed_trades)} hint={`${openTrades} open · current season`} />
      <Stat label="Realized net P/L" value={summaryMoneyReady ? signedMoney(data.summary.total_realized_pnl_minor, summaryCurrency!, summaryDecimals!) : "—"} hint="After simulated fees" tone={data.summary.total_realized_pnl_minor > 0 ? "good" : data.summary.total_realized_pnl_minor < 0 ? "bad" : undefined} />
      <Stat label="Win rate" value={data.summary.closed_trades ? percent(data.summary.wins / data.summary.closed_trades) : "—"} hint={`${data.summary.wins}W · ${data.summary.losses}L`} />
      <Stat label="Simulated fees" value={summaryMoneyReady && Number.isFinite(data.summary.total_fees_minor) ? money(data.summary.total_fees_minor, summaryCurrency!, summaryDecimals!) : "—"} hint="Open + closed trades" />
    </section>}
    {data && <div className="results-exit-insight"><ShieldCheck size={15} /><div><strong>Exit audit</strong><span>{data.summary.closed_trades === 0
      ? "Exit evidence and winner reversals will appear after the first closed trade."
      : `${data.summary.audited_exits} of ${data.summary.closed_trades} closed trade${data.summary.closed_trades === 1 ? "" : "s"} ${data.summary.closed_trades === 1 ? "includes" : "include"} saved exit evidence. ${data.summary.winner_reversals ? `${data.summary.winner_reversals} ${data.summary.winner_reversals === 1 ? "trade was" : "trades were"} positive before closing negative.` : "No winner reversals recorded."}`}</span></div></div>}
    <div className="leaderboard-table" role="table" aria-busy={loading || changingSort}>
      <div className="leaderboard-row leaderboard-head" role="row"><span>Rank</span><span>Token</span><span>Paper P/L</span><span>Fees</span><span>Held</span><span>Outcome</span><span /></div>
      {data?.rows.map((row, index) => {
        const tokenLabel = tokenDisplayLabel(row.symbol, row.mint);
        return <div className="leaderboard-row" role="row" key={`${row.mint}-${row.status}`}>
        <span className="leader-rank">#{index + 1}</span>
        <span className="leaderboard-token"><strong title={tokenSymbolKnown(row.symbol) ? undefined : row.mint}>{tokenLabel}</strong><small>{shortMint(row.mint)} · {row.status}{row.status === "open" && row.market_status !== "active" ? ` · ${humanize(row.market_status)}` : ""}</small><MintActions mint={row.mint} symbol={row.symbol} compact /></span>
        <span className={`leaderboard-pnl ${row.pnl_minor >= 0 ? "positive" : "negative"}`}><strong>{signedMoney(row.pnl_minor, row.quote_currency, row.quote_decimals)}</strong><small>{row.status === "open" && !row.mark_is_executable ? `conservative · ${signedMoney(row.last_known_pnl_minor, row.quote_currency, row.quote_decimals)} last known` : percentSigned(row.return_fraction)}</small><small className="leaderboard-mobile-fee">{money(row.fees_minor, row.quote_currency, row.quote_decimals)} fees</small></span>
        <span className="leaderboard-fees">{money(row.fees_minor, row.quote_currency, row.quote_decimals)}</span>
        <span className="leaderboard-held">{duration(row.hold_seconds)}</span>
        <span className="leaderboard-outcome">{row.exit_assessment ? <button className="exit-review-toggle" aria-expanded={reviewingMint === row.mint} onClick={() => setReviewingMint((current) => current === row.mint ? null : row.mint)}>{humanize(row.exit_assessment.reason)}</button> : row.exit_reason ? humanize(row.exit_reason) : row.status === "open" ? "Still open" : "Closed"}</span>
        <span className="leaderboard-actions">{row.entry_decision_id && <button className="quick-explain" onClick={() => void explainEntry(row.entry_decision_id!)} disabled={explainingId === row.entry_decision_id}>{explainingId === row.entry_decision_id ? <span className="mini-loader" /> : <Sparkles size={14} />}Why it bought</button>}</span>
        {reviewingMint === row.mint && row.exit_assessment && <div className="leaderboard-exit-review"><div><strong>Why it sold</strong><small>{humanize(row.exit_assessment.reason)} · policy {row.exit_assessment.policy_version}</small></div><div><span>Hold support<strong>{percent(row.exit_assessment.support_score)}</strong></span><span>Best marked return<strong>{row.peak_return_fraction === null ? "—" : percentSigned(row.peak_return_fraction)}</strong></span><span>Peak profit captured<strong>{row.peak_capture_fraction === null ? "—" : percentSigned(row.peak_capture_fraction)}</strong></span><span>Entry mode<strong>{row.entry_risk_mode ? title(row.entry_risk_mode) : "Legacy"}</strong></span></div>{row.exit_assessment.evidence.length > 0 && <p>{row.exit_assessment.evidence.join(" · ")}</p>}</div>}
      </div>})}
      {data !== null && data.sort === sort && !loading && !data.rows.length && <EmptyState icon={<Trophy size={22} />} title={sort === "recent" ? "No current-season trades yet" : "No closed trades this season yet"} copy={sort === "recent" ? "New paper entries will appear here with simulated fees and saved evidence." : "Choose Latest to review any open positions while completed trades continue accumulating."} />}
      {data !== null && data.sort === sort && !loading && hiddenResultRows > 0 && <div className="leaderboard-list-note">Showing {data.rows.length.toLocaleString()} of {availableRows.toLocaleString()} {sort === "recent" ? "current-season trades, newest first." : `closed trades, ${sort === "profit" ? "highest net results" : "largest net losses"} first.`}</div>}
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
  const [profileFilter, setProfileFilter] = useState<string>("current");
  const [comparisonPickerOpen, setComparisonPickerOpen] = useState(false);
  const consecutiveFailures = useRef(0);
  const comparisonPickerTriggerRef = useRef<HTMLButtonElement>(null);
  const comparisonPickerDialogRef = useRef<HTMLElement>(null);

  const closeComparisonPicker = useCallback(() => setComparisonPickerOpen(false), []);
  useEffect(() => {
    if (!comparisonPickerOpen) return;
    const dialog = comparisonPickerDialogRef.current;
    const trigger = comparisonPickerTriggerRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => {
      const selected = dialog?.querySelector<HTMLElement>('[aria-checked="true"]');
      (selected ?? dialog)?.focus();
    });
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeComparisonPicker();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = [...dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
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
    document.addEventListener("keydown", handleKey);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [closeComparisonPicker, comparisonPickerOpen]);

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

  // Keep the Results view readable during a rolling backend/frontend update: an older
  // cached response is valid legacy history, not a reason to blank the entire tab.
  const derivedComparisonGroups = deriveSeasonComparisonGroups(data.seasons);
  const comparisonGroups = data.comparison_groups?.length
    ? data.comparison_groups.map((group) => ({
      ...derivedComparisonGroups.find(
        (derived) => derived.comparison_key === group.comparison_key,
      ),
      ...group,
    }))
    : derivedComparisonGroups;
  const currentSeason = data.seasons.find((season) => season.status === "current") ?? null;
  const currentComparisonKey = data.current_comparison_key
    ?? (currentSeason ? seasonComparisonKey(currentSeason) : null);
  const currentComparisonGroup = comparisonGroups.find(
    (group) => group.comparison_key === currentComparisonKey,
  ) ?? null;
  const comparisonPickerSections: SeasonComparisonPickerSection[] = [];
  if (currentComparisonKey) {
    comparisonPickerSections.push({
      label: "Current",
      options: [{
        value: "current",
        label: "Current comparison",
        detail: currentComparisonGroup
          ? `${seasonComparisonGroupLabel(currentComparisonGroup)} · ${seasonComparisonGroupContext(currentComparisonGroup)}`
          : "The exact settings used by the running paper season",
      }],
    });
  }
  for (const currency of ["SOL", "USDC"] as QuoteCurrency[]) {
    const variants = comparisonGroups.filter((group) => group.quote_currency === currency);
    if (!variants.length) continue;
    const seasonCount = variants.reduce((sum, group) => sum + group.season_count, 0);
    const exactOptions = variants
      .filter((group) => group.comparison_key !== currentComparisonKey)
      .map((group) => ({
        value: group.comparison_key,
        label: seasonComparisonGroupLabel(group, false),
        detail: seasonComparisonGroupContext(group),
      }));
    comparisonPickerSections.push({
      label: `${currency} seasons`,
      options: [{
        value: `currency:${currency}`,
        label: `All ${currency} seasons`,
        detail: `${seasonCount} retained season${seasonCount === 1 ? "" : "s"} across ${variants.length} comparison group${variants.length === 1 ? "" : "s"}`,
      }, ...exactOptions],
    });
  }
  comparisonPickerSections.push({
    label: "Complete history",
    options: [{
      value: "all",
      label: "All seasons",
      detail: `${data.seasons.length} retained season${data.seasons.length === 1 ? "" : "s"} across every currency and policy`,
    }],
  });
  const comparisonPickerOptions = comparisonPickerSections.flatMap((section) => section.options);
  const requestedPickerFilter = profileFilter === currentComparisonKey
    ? "current"
    : profileFilter;
  const normalizedProfileFilter = comparisonPickerOptions.some(
    (option) => option.value === requestedPickerFilter,
  )
    ? requestedPickerFilter
    : currentComparisonKey ? "current" : "all";
  const selectedPickerOption = comparisonPickerOptions.find(
    (option) => option.value === normalizedProfileFilter,
  ) ?? comparisonPickerOptions[0];
  const resolvedProfileFilter = normalizedProfileFilter === "current"
    ? currentComparisonKey ?? "all"
    : normalizedProfileFilter;
  const filteredCurrency = resolvedProfileFilter.startsWith("currency:")
    ? resolvedProfileFilter.slice("currency:".length) as QuoteCurrency
    : null;
  const filteredSeasons = resolvedProfileFilter === "all"
    ? data.seasons
    : filteredCurrency
      ? data.seasons.filter((season) => season.quote_currency === filteredCurrency)
      : data.seasons.filter((season) => seasonComparisonKey(season) === resolvedProfileFilter);
  const orderedSeasons = [...filteredSeasons].sort((left, right) => left.season_number - right.season_number);
  const completed = orderedSeasons.filter((season) => season.status === "completed");
  const comparableCompleted = completed.filter((season) => season.comparable !== false);
  const excludedCompletedCount = completed.length - comparableCompleted.length;
  const selectedGroups = filteredCurrency
    ? comparisonGroups.filter((group) => group.quote_currency === filteredCurrency)
    : comparisonGroups;
  const selectedComparison = resolvedProfileFilter === "all" || filteredCurrency
    ? selectedGroups.length === 1 ? selectedGroups[0] ?? null : null
    : comparisonGroups.find((group) => group.comparison_key === resolvedProfileFilter) ?? null;
  const mixedHistory = (resolvedProfileFilter === "all" || filteredCurrency !== null)
    && selectedGroups.length > 1;
  const legacyHistory = !mixedHistory && (
    selectedComparison?.profile_provenance !== "exact"
    || selectedComparison?.terminal_policy_version !== "executable-boundary-v2"
  );
  const comparisonClaimsHidden = mixedHistory || legacyHistory;
  const trend = mixedHistory
    ? { title: "Mixed comparison history", copy: "Choose one exact bankroll, profile and boundary policy for a like-for-like performance trend.", tone: "neutral" as const }
    : legacyHistory
      ? { title: "Legacy policy unknown", copy: "These scorecards remain available, but their exact policy cannot support an improvement claim.", tone: "neutral" as const }
    : seasonTrend(comparableCompleted);
  const bestCompleted = comparisonClaimsHidden ? null : comparableCompleted.reduce<PaperSeason | null>((best, season) => {
    if (season.net_return_fraction === null) return best;
    if (best === null || best.net_return_fraction === null || season.net_return_fraction > best.net_return_fraction) return season;
    return best;
  }, null);
  const chartEligibleSeasons = orderedSeasons.filter((season) => (
    season.status === "current"
    || (season.status === "completed" && season.accounting_status !== "empty" && season.meaningful_activity !== false)
  ));
  const chartSeasons = chartRange === "all" ? chartEligibleSeasons : chartEligibleSeasons.slice(-chartRange);
  const newestSeasons = [...orderedSeasons].reverse();
  const visibleHistory = historyLimit === "all" ? newestSeasons : newestSeasons.slice(0, historyLimit);
  const hiddenHistoryCount = newestSeasons.length - visibleHistory.length;
  const completedWinRates = comparableCompleted.flatMap((season) => season.win_rate === null ? [] : [season.win_rate]);
  const profitableCount = comparableCompleted.filter((season) => season.net_pnl_minor > 0).length;
  const averageWinRate = completedWinRates.length
    ? completedWinRates.reduce((total, value) => total + value, 0) / completedWinRates.length
    : null;
  return <>
    <section className="season-profile-filter card">
      <div><span>Compare seasons</span><strong>{mixedHistory ? `${filteredCurrency ? `All ${filteredCurrency}` : "All seasons"} · mixed settings` : seasonComparisonGroupLabel(selectedComparison)}</strong><small>{mixedHistory ? "These scorecards remain visible, but bankroll, policy or boundary differences hide aggregate improvement claims." : legacyHistory ? "This retained history predates exact boundary accounting; comparison claims stay hidden." : "Every comparison statistic uses the same currency, starting bankroll, exact profile and terminal policy."}</small></div>
      <div className="season-comparison-control"><span id="season-comparison-control-label">Season comparison</span><button ref={comparisonPickerTriggerRef} type="button" className="season-comparison-trigger" aria-labelledby="season-comparison-control-label" aria-haspopup="dialog" aria-expanded={comparisonPickerOpen} onClick={() => setComparisonPickerOpen(true)}><span><strong>{selectedPickerOption?.label ?? "Choose comparison"}</strong><small>{selectedPickerOption?.detail ?? "Select retained season history"}</small></span><ChevronDown size={15} /></button></div>
      {comparisonPickerOpen && <div className="season-comparison-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeComparisonPicker(); }}><section ref={comparisonPickerDialogRef} className="season-comparison-dialog" role="dialog" aria-modal="true" aria-labelledby="season-comparison-title" aria-describedby="season-comparison-copy" tabIndex={-1}><header><div><strong id="season-comparison-title">Choose season comparison</strong><small id="season-comparison-copy">Exact strategy and accounting generations remain separate.</small></div><button type="button" aria-label="Close season comparison" onClick={closeComparisonPicker}><X size={16} /></button></header><div className="season-comparison-options">{comparisonPickerSections.map((section) => <section key={section.label} aria-label={section.label}><h3>{section.label}</h3><div role="radiogroup" aria-label={section.label}>{section.options.map((option) => <button type="button" role="radio" aria-checked={normalizedProfileFilter === option.value} className={normalizedProfileFilter === option.value ? "selected" : ""} key={option.value} onClick={() => { setProfileFilter(option.value); setHistoryLimit(20); closeComparisonPicker(); }}><span><strong>{option.label}</strong><small>{option.detail}</small></span>{normalizedProfileFilter === option.value && <Check size={16} />}</button>)}</div></section>)}</div></section></div>}
    </section>
    {!orderedSeasons.length && <div className="leaderboard-table"><EmptyState icon={<History size={22} />} title="No seasons for this comparison" copy="This retained currency and profile combination has not produced a paper season yet." /></div>}
    {!!orderedSeasons.length && <>
    <section className="stats-grid leaderboard-stats season-stats">
      <Stat label="Seasons" value={String(orderedSeasons.length)} hint="Filtered set" />
      <Stat label="Completed" value={String(completed.length)} />
      <Stat label={mixedHistory ? "Groups" : "Profitable"} value={mixedHistory ? String(selectedGroups.length) : String(profitableCount)} hint={mixedHistory ? "Mixed history" : legacyHistory ? "Raw scorecards" : "Comparable seasons"} tone={!comparisonClaimsHidden && profitableCount ? "good" : undefined} />
      <Stat label="Average win rate" value={comparisonClaimsHidden || averageWinRate === null ? "—" : percent(averageWinRate)} hint={mixedHistory ? "Select one comparison" : legacyHistory ? "Exact policy unknown" : "Comparable seasons"} />
    </section>
    {excludedCompletedCount > 0 && <div className="season-comparison-note"><ShieldCheck size={15} /><span>{excludedCompletedCount} manual, empty, legacy, or provider-unknown season{excludedCompletedCount === 1 ? " is" : "s are"} retained below but excluded from best-season and performance comparisons.</span></div>}
    <section className="season-overview-grid">
      <article className="card season-chart-card">
        <div className="season-card-heading">
          <div><span>Win rate by season</span><strong>Performance progression</strong></div>
          <div className="season-chart-actions">
            <small>{chartRange === "all" ? `All ${chartEligibleSeasons.length} recorded seasons` : `Latest ${Math.min(chartRange, chartEligibleSeasons.length)} of ${chartEligibleSeasons.length}`}</small>
            {chartEligibleSeasons.length > 10 && <div className="season-range-tabs" role="group" aria-label="Season chart range">
              <button type="button" className={chartRange === 10 ? "active" : ""} aria-pressed={chartRange === 10} onClick={() => setChartRange(10)}>Latest 10</button>
              <button type="button" className={chartRange === 25 ? "active" : ""} aria-pressed={chartRange === 25} onClick={() => setChartRange(25)}>Latest 25</button>
              <button type="button" className={chartRange === "all" ? "active" : ""} aria-pressed={chartRange === "all"} onClick={() => setChartRange("all")}>All</button>
            </div>}
          </div>
        </div>
        <SeasonWinChart seasons={chartSeasons} all={chartRange === "all"} total={chartEligibleSeasons.length} />
        <p><BrainCircuit size={14} /> Starting a new season resets its bankroll, while retained learning continues across seasons.</p>
      </article>
      <article className={`card season-trend-card ${trend.tone}`}>
        <TrendingUp size={20} />
        <span>Season read</span>
        <strong>{trend.title}</strong>
        <p>{trend.copy}</p>
        {bestCompleted && <div className="season-best-read"><span>Best completed</span><b>Season {bestCompleted.season_number} · {percentSigned(bestCompleted.net_return_fraction!)}</b></div>}
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
    </>}
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
        return <div className={`season-chart-column ${season.status} ${seasonChartBoundaryClass(season)}`} key={season.season_id}>
          <div className="season-chart-value">{rate === null ? "—" : percent(rate)}</div>
          <div className="season-chart-track"><span style={{ height: rate === null ? "0" : `${Math.max(0, Math.min(100, rate * 100))}%` }} /></div>
          <strong>S{season.season_number}</strong>
          <small className={(season.net_return_fraction ?? 0) >= 0 ? "positive" : "negative"}>{season.net_return_fraction === null ? "—" : percentSigned(season.net_return_fraction)}</small>
        </div>;
      })}
    </div>
  </div>;
}

function sampledSeasonIndexes(seasons: PaperSeason[], maxPoints: number): number[] {
  const measured = seasons
    .map((season, index) => season.win_rate === null ? null : index)
    .filter((index): index is number => index !== null);
  if (measured.length <= maxPoints) return measured;

  const firstMeasured = measured[0];
  const lastMeasured = measured.at(-1);
  if (firstMeasured === undefined || lastMeasured === undefined) return [];
  const selected = new Set<number>([firstMeasured, lastMeasured]);
  const bucketCount = Math.max(1, Math.floor((maxPoints - 2) / 2));
  for (let bucket = 0; bucket < bucketCount; bucket += 1) {
    const start = Math.floor((bucket / bucketCount) * seasons.length);
    const end = Math.floor(((bucket + 1) / bucketCount) * seasons.length);
    let minimum: number | null = null;
    let maximum: number | null = null;
    for (let index = start; index < end; index += 1) {
      const rate = seasons[index]?.win_rate;
      if (rate === null || rate === undefined) continue;
      if (minimum === null || rate < seasons[minimum]!.win_rate!) minimum = index;
      if (maximum === null || rate > seasons[maximum]!.win_rate!) maximum = index;
    }
    if (minimum !== null) selected.add(minimum);
    if (maximum !== null) selected.add(maximum);
  }
  return [...selected].sort((left, right) => left - right);
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
  const xForIndex = (index: number) => left + (
    seasons.length <= 1 ? plotWidth / 2 : (index / (seasons.length - 1)) * plotWidth
  );
  const missingPrefix = [0];
  seasons.forEach((season) => {
    missingPrefix.push(missingPrefix.at(-1)! + (season.win_rate === null ? 1 : 0));
  });
  const sampledIndexes = sampledSeasonIndexes(seasons, MAX_SEASON_HISTORY_POINTS);
  const sampledPoints = sampledIndexes.map((index, sampleIndex) => {
    const season = seasons[index]!;
    const previousIndex = sampledIndexes[sampleIndex - 1];
    const breakBefore = previousIndex !== undefined
      && (
        missingPrefix[index]! - missingPrefix[previousIndex + 1]! > 0
        || season.comparable === false
        || seasons[previousIndex]?.comparable === false
      );
    return {
      season,
      index,
      x: xForIndex(index),
      y: top + (1 - Math.max(0, Math.min(1, season.win_rate!))) * plotHeight,
      breakBefore,
    };
  });
  let path = "";
  let drawing = false;
  for (const point of sampledPoints) {
    if (point.breakBefore) drawing = false;
    path += `${drawing ? " L" : " M"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    drawing = true;
  }
  const measured = seasons.filter((season) => season.win_rate !== null);
  const labelStep = Math.max(1, Math.ceil(Math.max(1, seasons.length - 1) / 8));
  const labelIndexes = new Set(seasons.map((_, index) => index).filter((index) => index === 0 || index === seasons.length - 1 || index % labelStep === 0));
  const rates = measured.map((season) => season.win_rate!);
  const minimumRate = rates.reduce((value, rate) => Math.min(value, rate), 1);
  const maximumRate = rates.reduce((value, rate) => Math.max(value, rate), 0);
  const latest = seasons.at(-1);
  const accessibleLabel = measured.length
    ? `All ${seasons.length} seasons. Measured win rates range from ${percent(minimumRate)} to ${percent(maximumRate)}. Latest is Season ${latest?.season_number}, ${latest?.win_rate === null ? "with no closed trades" : `${percent(latest?.win_rate ?? 0)} win rate`}.`
    : `All ${seasons.length} seasons. No season has a measured win rate yet.`;

  return <div className="season-history-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={accessibleLabel}>
      {[1, 0.5, 0].map((rate) => {
        const y = top + (1 - rate) * plotHeight;
        return <g key={rate}><line className="season-line-grid" x1={left} x2={width - right} y1={y} y2={y} /><text className="season-line-y-label" x={left - 8} y={y + 3}>{Math.round(rate * 100)}%</text></g>;
      })}
      {path && <path className="season-line-path" d={path.trim()} />}
      {sampledPoints.map((point) => <circle
        className={`season-line-point ${point.season.status} ${seasonChartBoundaryClass(point.season)} ${(point.season.net_return_fraction ?? 0) >= 0 ? "positive" : "negative"}`}
        cx={point.x}
        cy={point.y}
        r={point.season.status === "current" ? 4.5 : 3}
        key={point.season.season_id}
      ><title>{`Season ${point.season.season_number}: ${percent(point.season.win_rate!)} win rate, ${point.season.net_return_fraction === null ? "net return unavailable" : `${percentSigned(point.season.net_return_fraction)} net return`}${point.season.status === "current" ? ", current" : ""}`}</title></circle>)}
      {seasons.map((season, index) => labelIndexes.has(index) ? <text className="season-line-x-label" textAnchor={index === 0 ? "start" : index === seasons.length - 1 ? "end" : "middle"} x={xForIndex(index)} y={height - 8} key={`label-${season.season_id}`}>S{season.season_number}</text> : null)}
    </svg>
    {!measured.length && <span className="season-line-empty">Waiting for closed paper trades</span>}
    <div className="season-line-legend"><span><i /> Win rate across every season</span><small>{sampledPoints.length < measured.length ? `${sampledPoints.length.toLocaleString()} representative trend points · all exact values remain below` : "Exact values remain in the scorecards below"}</small></div>
  </div>;
}

function SeasonRow({ season }: { season: PaperSeason }) {
  const ending = season.ending_equity_minor;
  const winRate = season.win_rate;
  const boundaryInventory = season.unresolved_inventory ?? [];
  const unknownCount = boundaryInventory.filter((item) => item.terminal_disposition !== "write_off").length;
  const writeOffCount = season.write_off_count
    ?? boundaryInventory.filter((item) => item.terminal_disposition === "write_off").length;
  const unresolved = season.accounting_status === "incomplete_unknown"
    || season.result_quality === "unresolved"
    || unknownCount > 0;
  const empty = season.accounting_status === "empty";
  return <div className={`season-row ${season.status} ${season.comparable === false ? "not-comparable" : ""}`} role="row">
    <span className="season-identity" data-label="Season"><strong>Season {season.season_number}</strong><small>{season.status === "current" ? "Live scorecard" : `Finished ${shortDate(season.ended_at!)}`}</small><em>{season.status}</em>{writeOffCount > 0 && <em className="write-off">{writeOffCount} write-off{writeOffCount === 1 ? "" : "s"}</em>}{unresolved && <em className="unresolved">provider unknown</em>}{empty && <em className="not-compared">empty</em>}{season.comparable === false && !unresolved && !empty && <em className="not-compared">not compared</em>}<b>{season.profile ? `${riskModeLabel(season.profile.risk_mode)} · ${shortDrawdownLabel(season.profile)}` : "Legacy / unknown"}</b>{season.terminal_reason && <small>Ended: {terminalReasonLabel(season.terminal_reason)}</small>}</span>
    <span data-label="Bankroll"><strong>{money(season.starting_minor, season.quote_currency, season.quote_decimals)}</strong><small>{ending === null ? "No equity mark" : `${season.status === "current" ? "Now" : unresolved ? "Executable end" : "Ended"} ${money(ending, season.quote_currency, season.quote_decimals)}`}</small></span>
    <span data-label="Net result" className={season.net_pnl_minor >= 0 ? "positive" : "negative"}><strong>{signedMoney(season.net_pnl_minor, season.quote_currency, season.quote_decimals)}</strong><small>{season.comparable === false ? "Excluded from comparisons" : season.net_return_fraction === null ? "—" : percentSigned(season.net_return_fraction)}</small></span>
    <span data-label="Win rate"><strong>{winRate === null ? "—" : percent(winRate)}</strong><small>{season.wins}W · {season.losses}L{season.break_even ? ` · ${season.break_even} even` : ""}</small></span>
    <span data-label="Trades"><strong>{season.closed_trades.toLocaleString()}</strong><small>{money(season.total_fees_minor, season.quote_currency, season.quote_decimals)} fees</small></span>
    <span data-label="Drawdown"><strong>{percent(season.ending_drawdown_fraction)}</strong><small>{season.open_positions ? `${season.open_positions} ${unresolved ? "unresolved at boundary" : `open at ${season.status === "current" ? "present" : "finish"}`}` : "No open positions"}</small></span>
    <span data-label="Duration"><strong>{longDuration(season.duration_seconds)}</strong><small>Started {shortDate(season.started_at)}</small></span>
    {!!boundaryInventory.length && <details className="season-unresolved-detail">
      <summary>Review boundary inventory · {boundaryInventory.length}</summary>
      <div>{boundaryInventory.map((position) => <span key={position.position_id}>
        <strong title={position.mint}>{tokenDisplayLabel(position.symbol, position.mint)}</strong>
        <small>{position.token_units.toLocaleString()} raw token units · {humanize(position.market_status)} · {position.terminal_disposition === "write_off" ? "confirmed write-off" : "provider unknown"}</small>
        <small>Last-known indication {money(position.last_known_mark_minor, position.quote_currency, position.quote_decimals)} · not an executed sale</small>
        <small>{position.mark_blockers.length ? position.mark_blockers.map(humanize).join(" · ") : "No executable route at the season boundary"}</small>
      </span>)}</div>
    </details>}
  </div>;
}

function seasonChartBoundaryClass(season: PaperSeason) {
  if (season.accounting_status === "incomplete_unknown") return "boundary-unknown";
  if (season.boundary_type === "end_now") return "boundary-manual";
  if (season.accounting_status === "complete_with_writeoffs") return "boundary-write-off";
  return "";
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
  const integrityEvidence = [
    ["One-trade wallets", values.single_trade_wallet_ratio, "percent"],
    ["Wallet round trips", values.round_trip_wallet_ratio, "percent"],
    ["Round-trip volume", values.round_trip_volume_ratio, "percent"],
    ["Net flow vs gross volume", values.net_quote_flow_ratio, "percent"],
    ["Buy/sell alternation", values.side_alternation_ratio, "percent"],
    ["Clustered trade sizes", values.quantized_amount_repeat_ratio, "percent"],
    ["Slot concentration", values.slot_concentration_hhi, "percent"],
    ["One-way price movement", values.price_direction_consistency, "percent"],
    ["Multi-trade signatures", values.multi_trade_signature_ratio, "percent"],
  ] as const;
  const integrity = decision.integrity_assessment;
  const sizing = decision.sizing_assessment;
  return <section className="explain-evidence">
    <div className="explain-score-grid"><ScoreBar label="Opportunity" value={decision.score.opportunity} tone="good" /><ScoreBar label="Danger" value={decision.score.danger} tone="bad" /><ScoreBar label="Execution" value={decision.score.execution} tone="blue" /><ScoreBar label="Evidence confidence" value={decision.score.confidence} tone="purple" /></div>
    <h3>What the engine actually saw</h3>
    <div className="evidence-grid">{evidence.map(([label, item, format]) => <div key={label}><span>{label}</span><strong>{formatEvidence(item?.value, format)}</strong><small>{item ? `${Math.round(item.quality * 100)}% source quality · ${duration(item.freshness_seconds)} old` : "Not recorded"}</small></div>)}<div><span>Estimated entry impact</span><strong>{estimatedImpact === null ? "Unknown" : percent(estimatedImpact)}</strong><small>Planned paper size ÷ observed reserve depth</small></div></div>
    {sizing && <><h3>Paper sizing receipt</h3><div className="evidence-grid">
      <div><span>Reference size</span><strong>{sizing.base_size_sol.toFixed(4)} SOL</strong><small>The personality's cautious starting point</small></div>
      <div><span>Selected size</span><strong>{sizing.selected_size_sol.toFixed(4)} SOL</strong><small>{sizing.reasons.map(humanize).join(" · ")}</small></div>
      <div><span>Realized-bankroll allocation</span><strong>{percent(sizing.account_allocation_fraction)}</strong><small>Unrealized gains cannot increase this target</small></div>
      <div><span>Binding limit</span><strong>{sizing.constraints.map(humanize).join(" · ")}</strong><small>{humanize(sizing.policy_version)}</small></div>
    </div></>}
    {integrity && <><h3>Baseline market integrity</h3><div className="evidence-grid">
      <div><span>Conclusion</span><strong>{humanize(integrity.state)}</strong><small>{integrity.evidence[0] ?? "No conclusion recorded"}</small></div>
      <div><span>Usable coverage</span><strong>{percent(integrity.coverage)}</strong><small>{integrity.sample_count} trades in the frozen sample</small></div>
      <div><span>Corroborating categories</span><strong>{integrity.category_count}</strong><small>{integrity.categories.length ? integrity.categories.map(humanize).join(" · ") : "No corroborated pattern"}</small></div>
      <div><span>Integrity policy</span><strong>{humanize(integrity.policy_version)}</strong><small>Missing or short evidence remains uncertain</small></div>
    </div></>}
    <h3>{integrity ? "Evidence behind the integrity conclusion" : "Market integrity evidence · shadow learning"}</h3>
    <div className="evidence-grid">{integrityEvidence.map(([label, item, format]) => <div key={label}><span>{label}</span><strong>{formatEvidence(item?.value, format)}</strong><small>{item?.missing_reason ? humanize(item.missing_reason) : item ? `${Math.round(item.quality * 100)}% evidence coverage` : "Not recorded in this decision"}</small></div>)}</div>
    <div className="explain-gates"><div><strong>Positive evidence</strong>{decision.reasons.map((reason) => <span key={reason}><Check size={13} />{reason}</span>)}</div><div><strong>{decision.blockers.length ? "Gates that stopped entry" : "Safety gates"}</strong>{decision.blockers.length ? decision.blockers.map((blocker) => <span key={blocker}><AlertTriangle size={13} />{humanize(blocker)}</span>) : <span><ShieldCheck size={13} />All configured entry gates passed at this checkpoint.</span>}</div></div>
  </section>;
}

function Replay({ snapshot }: { snapshot: Snapshot }) {
  const currency = snapshot.portfolio.quote_currency;
  const fills = snapshot.fills;
  const buys = fills.filter((fill) => fill.side === "buy").length;
  const sells = fills.length - buys;
  const fees = fills.reduce(
    (total, fill) => total + fill.account_protocol_fee_minor + fill.account_network_fee_minor,
    0,
  );
  const averageImpact = fills.length
    ? fills.reduce((total, fill) => total + fill.price_impact_fraction, 0) / fills.length
    : null;
  const sortedLatencies = fills.map((fill) => fill.latency_ms).sort((left, right) => left - right);
  const middle = Math.floor(sortedLatencies.length / 2);
  const medianLatency = sortedLatencies.length
    ? sortedLatencies.length % 2
      ? sortedLatencies[middle]!
      : (sortedLatencies[middle - 1]! + sortedLatencies[middle]!) / 2
    : null;
  const receiptScope = fills.length === 30
    ? "Latest 30 current-season receipts · newest first"
    : `${fills.length.toLocaleString()} current-season receipt${fills.length === 1 ? "" : "s"} · newest first`;
  return <>
    <section className="page-heading"><div><span className="eyebrow"><History size={14} /> Replay</span><h1>The score is net of the friction.</h1><p>Review fills, latency, price impact, protocol charges and simulated network fees.</p></div></section>
    <section className="stats-grid replay-stats" aria-label="Visible receipt summary">
      <Stat label="Visible receipts" value={fills.length.toLocaleString()} hint={`${buys} buy${buys === 1 ? "" : "s"} · ${sells} sell${sells === 1 ? "" : "s"}${fills.length === 30 ? " · latest 30" : ""}`} />
      <Stat label="Visible fees" value={fills.length ? money(fees, currency, snapshot.portfolio.quote_decimals) : "—"} hint="Protocol + simulated network" />
      <Stat label="Average impact" value={averageImpact === null ? "—" : percent(averageImpact)} hint="Recorded price impact" />
      <Stat label="Median latency" value={medianLatency === null ? "—" : formatLatency(medianLatency)} hint="Order request to paper fill" />
    </section>
    <article className="card replay-chart"><SectionHeader title="Equity history" subtitle={`Current season · ${snapshot.equity_history.length} recorded market checkpoints · ${currency} account`} /><EquityChart points={snapshot.equity_history} tall /></article>
    <SectionHeader title="Fill receipts" subtitle={receiptScope} />
    {fills.length === 30 && <p className="replay-scope-note"><History size={14} />Replay keeps the live dashboard responsive with the newest 30 receipts; Results summarizes the complete current season.</p>}
    <div className="fills-table" role="table" aria-label="Current-season paper fill receipts">
      <div className="fill-row fill-head" role="row"><span role="columnheader">Time</span><span role="columnheader">Token</span><span role="columnheader">Side</span><span role="columnheader">Net flow</span><span role="columnheader">Fees</span><span role="columnheader">Impact</span><span role="columnheader">Latency</span></div>
      {fills.map((fill) => <FillRow fill={fill} key={fill.fill_id} />)}
      {!fills.length && <EmptyState icon={<CircleDollarSign size={22} />} title="No fills yet" copy="A receipt appears after order latency when the latest observed reserve state is still executable." />}
    </div>
  </>;
}

function StorageManager({ snapshot, refresh, busy, setBusy, reportIssue, resolveIssue }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
  busy: boolean;
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
    <form className="storage-form" onSubmit={save}><label>Maximum database<input type="number" min="0.5" max="100" step="0.5" value={maxGb} onChange={(event) => { setMaxGb(event.target.value); setSaved(false); }} disabled={saving || busy} /><span>GB</span></label><label>Raw event history<input type="number" min="1" max="720" step="1" value={retention} onChange={(event) => { setRetention(event.target.value); setSaved(false); }} disabled={saving || busy} /><span>hours</span></label><button className={`button${saved ? " saved" : ""}`} type="submit" disabled={saving || busy} aria-live="polite">{saving ? <span className="mini-loader" /> : saved ? <Check size={15} /> : <Save size={15} />}{saving ? "Saving…" : saved ? "Saved" : "Save"}</button></form>
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
  const [dismissedCompletionId, setDismissedCompletionId] = useState(loadDismissedMaintenanceNotice);
  const completionCopy = maintenanceCompletionCopy(operation, snapshot.version, snapshot.server_time);
  const completionOperationId = operation?.state === "completed"
    && typeof operation.operation_id === "string"
    && operation.operation_id.length > 0
    && operation.operation_id.length <= 180
    ? operation.operation_id
    : null;
  const showCompletion = Boolean(
    completionCopy && completionOperationId && completionOperationId !== dismissedCompletionId,
  );
  const activeDownload = snapshot.ai_lab.downloads.some(
    (download) => download.status === "queued" || download.status === "downloading",
  );

  useEffect(() => {
    const syncDismissedNotice = (event: StorageEvent) => {
      if (event.key === DISMISSED_MAINTENANCE_NOTICE_KEY || event.key === null) {
        setDismissedCompletionId(loadDismissedMaintenanceNotice());
      }
    };
    window.addEventListener("storage", syncDismissedNotice);
    return () => window.removeEventListener("storage", syncDismissedNotice);
  }, []);

  const dismissCompletion = () => {
    if (!completionOperationId) return;
    saveDismissedMaintenanceNotice(completionOperationId);
    setDismissedCompletionId(completionOperationId);
  };

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
        {showCompletion && <p className="maintenance-success" role="status"><Check size={14} /><span>{completionCopy}</span><button className="maintenance-success-dismiss" type="button" aria-label="Dismiss update confirmation" onClick={dismissCompletion}><X size={13} /></button></p>}
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
  const [pendingDemoMode, setPendingDemoMode] = useState<boolean | null>(null);
  const changeMode = async (demo: boolean) => {
    setBusy(true);
    try {
      await api.setDemo(demo);
      resolveIssue("mode");
      setPendingDemoMode(null);
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
        <label className="mode-option"><span><Radio size={18} /><strong>Solana mainnet</strong><small>Official program logs through the configured public or private RPC.</small></span><input type="radio" name="market-source" checked={!snapshot.demo_mode} disabled={busy} onChange={() => setPendingDemoMode(false)} /></label>
        <label className="mode-option"><span><Sparkles size={18} /><strong>Synthetic demo</strong><small>Fully offline market activity. External enrichment is paused in this mode.</small></span><input type="radio" name="market-source" checked={snapshot.demo_mode} disabled={busy} onChange={() => setPendingDemoMode(true)} /></label>
        {pendingDemoMode !== null && pendingDemoMode !== snapshot.demo_mode && <div className="source-confirm" role="alertdialog" aria-labelledby="source-confirm-title" aria-describedby="source-confirm-copy">
          <strong id="source-confirm-title">Switch to {pendingDemoMode ? "Synthetic demo" : "Solana mainnet"}?</strong>
          <p id="source-confirm-copy">This archives the current paper season, stops the engine, cancels unfilled orders and returns to bankroll setup so live and demo evidence never mix. Historical seasons and retained learning remain.</p>
          <div><button className="button ghost" type="button" disabled={busy} onClick={() => setPendingDemoMode(null)}>Keep {snapshot.demo_mode ? "Synthetic demo" : "Solana mainnet"}</button><button className="button danger" type="button" disabled={busy} onClick={() => void changeMode(pendingDemoMode)}>{busy ? "Switching safely…" : "Switch and archive season"}</button></div>
        </div>}
      </article>
      <article className="card settings-card">
        <SectionHeader title="Data health" subtitle="The engine abstains when required evidence is stale" />
        <HealthRows health={snapshot.provider_health} />
        <div className={`health-summary ${snapshot.database_ok ? "healthy" : "unhealthy"}`}><span />SQLite connection {snapshot.database_ok ? "healthy" : "failed"}</div>
        <div className={`health-summary pipeline-summary ${snapshot.event_pipeline.degraded ? "unhealthy" : "healthy"}`}><span /><div><strong>Market processing {snapshot.event_pipeline.degraded ? snapshot.event_pipeline.degraded_reasons.map(humanize).join(", ") : "current"}</strong><small>{compact(snapshot.event_pipeline.processed)} processed · {compact(snapshot.event_pipeline.ephemeral)} transient · {compact(snapshot.event_pipeline.persisted)} saved · {compact(snapshot.event_pipeline.shed_candidate_events ?? Math.max(0, snapshot.event_pipeline.dropped - (snapshot.event_pipeline.expired_candidate_events ?? 0)))} shed · {compact(snapshot.event_pipeline.expired_candidate_events ?? 0)} expired</small></div></div>
      </article>
      <StorageManager snapshot={snapshot} refresh={refresh} busy={busy} setBusy={setBusy} reportIssue={reportIssue} resolveIssue={resolveIssue} />
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
  const modelMutationActive = workingModel !== null;
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
          return <div className={`ai-model-row ${selected ? "selected" : ""}`} key={model.name}>
            <div className="ai-model-copy"><div><strong>{model.label}</strong>{model.role.includes("Recommended") && <span>Recommended</span>}</div><small>{model.role}</small><small>{formatBytes(model.download_bytes)} download · {model.recommended_ram_gb} GB RAM recommended{!model.fits_recommended_ram ? " · above detected RAM" : ""}</small></div>
            {downloading && download && <div className="model-download" role="status"><div><span style={{ width: `${download.progress_fraction * 100}%` }} /></div><small>{download.message} · {percent(download.progress_fraction)}</small></div>}
            {download?.status === "error" && <small className="model-error">{download.error ?? "Download failed"}</small>}
            <div className="ai-model-actions">
              {model.installed ? <>
                {selected ? <span className="model-selected"><Check size={14} />Selected</span> : <button className="button ghost" disabled={modelMutationActive || downloadActive} onClick={() => void act(model.name, "select")}>Select</button>}
                {confirmRemoval === model.name ? <>
                  <button className="button ghost" disabled={modelMutationActive} onClick={() => setConfirmRemoval(null)}>Cancel</button>
                  <button className="button danger" disabled={modelMutationActive || downloadActive || lab.inference_busy} title={lab.inference_busy ? "Wait for the current local AI assessment to finish" : selected ? "Removing the selected model turns the AI Decision Lab off; learning and history remain" : undefined} onClick={() => void act(model.name, "remove")}>Remove model</button>
                </> : <button className="button ghost" disabled={modelMutationActive || downloadActive || lab.inference_busy} title={lab.inference_busy ? "Wait for the current local AI assessment to finish" : selected ? "Removing the selected model turns the AI Decision Lab off; learning and history remain" : undefined} onClick={() => setConfirmRemoval(model.name)}>Remove</button>}
              </> : <button className="button ghost" disabled={modelMutationActive || downloadActive || !lab.ollama_reachable} onClick={() => void act(model.name, "download")}>{downloading ? "Downloading…" : download?.status === "error" ? "Retry" : "Download"}</button>}
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
    if (checked) {
      setSecretValues((current) => Object.fromEntries(
        Object.entries(current).filter(([key]) => !keys.includes(key)),
      ));
    }
    setClearSecrets((current) => checked
      ? [...new Set([...current, ...keys])]
      : current.filter((key) => !keys.includes(key)));
  };
  const updateSecret = (key: string, value: string, clearKeys: string[] = [key]) => {
    setSavedMessage(null);
    setSecretValues((current) => ({ ...current, [key]: value }));
    if (value.trim()) {
      setClearSecrets((current) => current.filter((item) => !clearKeys.includes(item)));
    }
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
    const effectiveClear = new Set(clearSecrets);
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
      if (value) {
        secrets[key] = value;
        effectiveClear.delete(key);
      }
    }
    if (solanaPresetId === "public") {
      effectiveClear.add("solana_http");
      effectiveClear.add("solana_ws");
    }
    if (guidedSolana && solanaApiKey?.trim()) {
      const endpoints = guidedSolanaEndpoints(guidedSolana, solanaApiKey);
      secrets.solana_http = endpoints.http;
      effectiveClear.delete("solana_http");
      if (endpoints.ws) {
        secrets.solana_ws = endpoints.ws;
        effectiveClear.delete("solana_ws");
      }
    }
    if (guidedSolana?.streamMode === "default") {
      delete secrets.solana_ws;
      effectiveClear.add("solana_ws");
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
          const solanaStreamHealthy = name === "solana"
            && provider.active
            && snapshot.provider_health.connected === true;
          const activity = name === "solana" && provider.active
            ? solanaStreamHealthy
              ? provider.stream_fallback_active ? "Stream connected · fallback" : "Stream connected"
              : snapshot.provider_health.next_retry_at ? "Stream retrying" : "Stream connecting"
            : providerActivity(name, provider.active);
          return <div className="provider-row" key={name}>
            <div><strong>{title(name)}</strong><small>{providerRole(name)} · {provider.policy.label} · {provider.endpoint}</small>{name === "solana" && <small className="provider-route-read">HTTP safety: {provider.endpoint} ({providerRouteSourceLabel(provider.http_source)}) · Live stream: {provider.stream_endpoint ?? "unavailable"} ({providerRouteSourceLabel(provider.stream_source)})</small>}</div>
            <div><span className={solanaStreamHealthy || (name !== "solana" && provider.active) ? "provider-active" : provider.active ? "provider-retrying" : "provider-idle"}>{activity}</span><small>{quota ? providerQuotaCopy(quota) : "No external calls"}</small></div>
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
          onChange={(value) => updateSecret("solana_api_key", value, guidedSolana.streamMode === "default" ? ["solana_http"] : ["solana_http", "solana_ws"])}
        />}
        {solanaPresetId === "public" && <p className="provider-connection-guide">No key required. Saving restores the configured environment endpoint or the bundled public Solana endpoint.</p>}
        {guidedSolana && <p className="provider-connection-guide">{guidedSolana.streamMode === "default" ? "Economy mode keeps keyed Helius for paced safety lookups and restores the environment/public WebSocket for the high-volume live stream." : "Signal Arcade creates the secure HTTP and WebSocket URLs automatically."} The key remains write-only.</p>}
        {solanaPresetId === "custom" && <>
          <SecretInput label="HTTP RPC URL" value={secretValues.solana_http ?? ""} placeholder={`${settings.providers.solana.endpoint} · blank keeps saved value`} onChange={(value) => updateSecret("solana_http", value, ["solana_http", "solana_ws"])} />
          <SecretInput label="WebSocket URL" value={secretValues.solana_ws ?? ""} placeholder={`${settings.providers.solana.stream_endpoint ?? "Saved stream"} · blank keeps saved value`} onChange={(value) => updateSecret("solana_ws", value, ["solana_http", "solana_ws"])} />
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
        <SecretInput label="API key" value={secretValues.jupiter_api_key ?? ""} placeholder={settings.providers.jupiter.api_key_configured ? "Saved on the local server · blank keeps it" : "Optional"} onChange={(value) => updateSecret("jupiter_api_key", value)} />
        <PolicyInputs policy={configuration.jupiter} onChange={(policy) => setPolicy("jupiter", policy)} />
        <label className="provider-check"><input type="checkbox" checked={clearSecrets.includes("jupiter_api_key")} onChange={(event) => toggleClear(["jupiter_api_key"], event.target.checked)} />Remove saved Jupiter key</label>
      </ProviderEditor>
      <ProviderEditor title="Local AI connection" copy="Docker uses the private bundled Ollama service automatically. Only set an override when you deliberately want another local Ollama server.">
        <SecretInput label="External Ollama URL override" value={secretValues.ollama_url ?? ""} placeholder={`${settings.providers.ollama.endpoint} · blank keeps the current connection`} onChange={(value) => updateSecret("ollama_url", value)} />
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
  return <label>{label}<input type="password" autoComplete="off" spellCheck={false} value={value} placeholder={placeholder} required={required} onChange={(event) => onChange(event.target.value)} /></label>;
}

function PolicyInputs({ policy, onChange }: { policy: ProviderPolicy; onChange: (policy: ProviderPolicy) => void }) {
  return <>
    <label>Requests per minute<input type="number" min="1" max="60000" value={policy.requests_per_minute} onChange={(event) => onChange({ ...policy, requests_per_minute: Number(event.target.value) })} /></label>
    <label>Monthly hard cap<input type="number" min="1" max="2000000000" required={policy.paid_mode} value={policy.monthly_limit ?? ""} placeholder={policy.paid_mode ? "Required for paid plans" : "No monthly cap"} onChange={(event) => onChange({ ...policy, monthly_limit: event.target.value ? Number(event.target.value) : null })} /></label>
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
  wsHost?: string;
  streamMode: "provider" | "default";
  httpTemplate: (encodedKey: string) => string;
  wsTemplate?: (encodedKey: string) => string;
}

const GUIDED_SOLANA_PROVIDERS: Record<string, GuidedSolanaProvider> = {
  helius_free: {
    name: "Helius",
    httpHost: "https://mainnet.helius-rpc.com",
    wsHost: "wss://mainnet.helius-rpc.com",
    streamMode: "provider",
    httpTemplate: (key) => `https://mainnet.helius-rpc.com/?api-key=${key}`,
    wsTemplate: (key) => `wss://mainnet.helius-rpc.com/?api-key=${key}`,
  },
  helius_economy: {
    name: "Helius",
    httpHost: "https://mainnet.helius-rpc.com",
    streamMode: "default",
    httpTemplate: (key) => `https://mainnet.helius-rpc.com/?api-key=${key}`,
  },
  alchemy_free: {
    name: "Alchemy",
    httpHost: "https://solana-mainnet.g.alchemy.com",
    wsHost: "wss://solana-mainnet.g.alchemy.com",
    streamMode: "provider",
    httpTemplate: (key) => `https://solana-mainnet.g.alchemy.com/v2/${key}`,
    wsTemplate: (key) => `wss://solana-mainnet.g.alchemy.com/v2/${key}`,
  },
  solanatracker_rpc_free: {
    name: "SolanaTracker RPC",
    httpHost: "https://rpc-mainnet.solanatracker.io",
    wsHost: "wss://rpc-mainnet.solanatracker.io",
    streamMode: "provider",
    httpTemplate: (key) => `https://rpc-mainnet.solanatracker.io?api_key=${key}`,
    wsTemplate: (key) => `wss://rpc-mainnet.solanatracker.io?api_key=${key}`,
  },
};

function guidedSolanaProvider(presetId: string): GuidedSolanaProvider | null {
  return GUIDED_SOLANA_PROVIDERS[presetId] ?? null;
}

function solanaProviderMatches(provider: Snapshot["provider_settings"]["providers"]["solana"], guided: GuidedSolanaProvider): boolean {
  return provider.endpoint === guided.httpHost && (
    guided.streamMode === "default"
      ? true
      : provider.stream_endpoint === guided.wsHost
  );
}

function guidedSolanaEndpoints(guided: GuidedSolanaProvider, apiKey: string): { http: string; ws?: string } {
  const encodedKey = encodeURIComponent(apiKey.trim());
  return {
    http: guided.httpTemplate(encodedKey),
    ws: guided.wsTemplate?.(encodedKey),
  };
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

function providerRouteSourceLabel(source: ProviderView["http_source"]): string {
  if (source === "saved_override") return "saved route";
  if (source === "environment_default") return "default route";
  return "route source unknown";
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
  const filledAt = new Date(fill.filled_at);
  const time = filledAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const date = shortDate(fill.filled_at);
  const cashFlow = fill.side === "buy" ? -fill.account_net_minor : fill.account_net_minor;
  const venueCopy = `${fill.venue}${exitReason ? `, ${humanize(exitReason)}` : fill.sol_usd_price ? `, SOL $${fill.sol_usd_price.toFixed(2)}` : ""}`;
  const feeCopy = `${money(fees, fill.account_currency, fill.account_decimals)} total, ${money(fill.account_protocol_fee_minor, fill.account_currency, fill.account_decimals)} protocol, ${money(fill.account_network_fee_minor, fill.account_currency, fill.account_decimals)} network`;
  return <div className="fill-row" role="row">
    <span role="cell" data-label="Time" aria-label={`Time ${date}, ${time}`}><strong>{time}</strong><small>{date}</small></span>
    <span role="cell" data-label="Token" aria-label={`Token ${tokenLabel}, ${venueCopy}`}><strong title={tokenSymbolKnown(fill.symbol) ? undefined : fill.mint}>{tokenLabel}</strong><small>{fill.venue}{exitReason ? ` · ${humanize(exitReason)}` : fill.sol_usd_price ? ` · SOL $${fill.sol_usd_price.toFixed(2)}` : ""}</small></span>
    <span role="cell" data-label="Side" aria-label={`Side ${fill.side}`}><ActionBadge action={fill.side === "buy" ? "enter" : "pass"} label={fill.side} /></span>
    <span role="cell" data-label={`Net ${fill.account_currency}`} aria-label={`Net ${fill.account_currency} ${cashFlow >= 0 ? "inflow" : "outflow"} ${money(Math.abs(cashFlow), fill.account_currency, fill.account_decimals)}`} className={`fill-flow ${cashFlow >= 0 ? "positive" : "negative"}`}><strong>{signedMoney(cashFlow, fill.account_currency, fill.account_decimals)}</strong><small>{money(fill.account_gross_minor, fill.account_currency, fill.account_decimals)} gross</small></span>
    <span role="cell" data-label="Fees" aria-label={`Fees ${feeCopy}`} className="fill-fees"><strong>{money(fees, fill.account_currency, fill.account_decimals)}</strong><small>{money(fill.account_protocol_fee_minor, fill.account_currency, fill.account_decimals)} protocol · {money(fill.account_network_fee_minor, fill.account_currency, fill.account_decimals)} network</small></span>
    <span role="cell" data-label="Impact" aria-label={`Impact ${percent(fill.price_impact_fraction)}`}><strong>{percent(fill.price_impact_fraction)}</strong></span>
    <span role="cell" data-label="Latency" aria-label={`Latency ${formatLatency(fill.latency_ms)}, ${Math.round(fill.latency_ms).toLocaleString()} milliseconds exact`}><strong>{formatLatency(fill.latency_ms)}</strong>{fill.latency_ms >= 1_000 && <small>{Math.round(fill.latency_ms).toLocaleString()}ms exact</small>}</span>
  </div>;
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
    <div className="equity-chart-toolbar"><small>{view === "journey" ? `${journey.length} meaningful equity moves · unchanged waits collapsed${plateau}` : "True elapsed-time spacing · unchanged waits preserved"}</small><div role="group" aria-label="Equity chart spacing"><button className={view === "journey" ? "active" : ""} aria-pressed={view === "journey"} title="Journey collapses repetitive unchanged checkpoints so the season's meaningful moves stay visible." onClick={() => setView("journey")}>Journey</button><button className={view === "time" ? "active" : ""} aria-pressed={view === "time"} title="Elapsed time preserves the real waiting time between recorded checkpoints." onClick={() => setView("time")}>Elapsed time</button></div></div>
    <canvas ref={ref} className={`equity-chart ${tall ? "tall" : ""}`} role="img" aria-label={`Paper equity ${view === "journey" ? "season journey with unchanged checkpoints collapsed" : "history spaced by elapsed time"}. ${points.length} recorded checkpoints.`}>Paper equity history</canvas>
  </div>;
}

function HealthRows({ health }: { health: Record<string, unknown> }) { return <div className="health-rows">{Object.entries(health).filter(([, value]) => typeof value !== "object").map(([key, value]) => <div key={key}><span>{humanize(key)}</span><strong>{formatHealthValue(key, value)}</strong></div>)}</div>; }
function ScoreBar({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className="score-bar"><div><span>{label}</span><strong>{percent(value)}</strong></div><div className={`bar ${tone}`}><span style={{ width: `${Math.max(2, value * 100)}%` }} /></div></div>; }
function ScoreRing({ score }: { score: number }) { return <span className="score-ring" style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}><strong>{score}</strong><small>/100</small></span>; }
function ActionBadge({ action, label }: { action: DecisionAction; label?: string }) { return <span className={`action-badge ${action}`}>{label ?? action}</span>; }
function SectionHeader({ title: heading, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) { return <div className="section-header"><div><h2>{heading}</h2><p>{subtitle}</p></div>{action}</div>; }
function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) { return <article className="card stat-card"><span>{label}</span><strong className={tone}>{value}</strong>{hint && <small>{hint}</small>}</article>; }
function EmptyState({ icon, title: heading, copy }: { icon: React.ReactNode; title: string; copy: string }) { return <div className="empty-state">{icon}<div><strong>{heading}</strong><p>{copy}</p></div></div>; }
function NavButton({ active, onClick, icon, label, attention = false }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string; attention?: boolean }) { return <button className={active ? "active" : ""} aria-label={label} aria-current={active ? "page" : undefined} aria-describedby={attention ? "learning-milestone-notice" : undefined} title={attention ? "New learning milestone" : undefined} onClick={onClick}>{icon}<span>{label}</span>{attention && <span className="nav-attention-dot" aria-hidden="true" />}{attention && <span className="sr-only" id="learning-milestone-notice">New learning milestone</span>}</button>; }
function LoadingState() { return <div className="loading-state"><span className="loader" /><strong>Starting the arcade…</strong><p>Checking the ledger and connecting to the selected market source.</p></div>; }

function minorAmountInput(value: number, decimals: number): string {
  const fixed = (value / 10 ** decimals).toFixed(decimals);
  const [whole = "0", fraction = ""] = fixed.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}
function parseStartingAmount(value: string, currency: QuoteCurrency): { minor: number | null; error: string | null } {
  const decimals = currency === "SOL" ? 9 : 6;
  const match = new RegExp(`^(\\d+)(?:\\.(\\d{1,${decimals}}))?$`).exec(value.trim());
  const amount = Number(value);
  if (!match || !Number.isFinite(amount) || amount <= 0) {
    return { minor: null, error: `Enter a positive ${currency} amount with at most ${decimals} decimals.` };
  }
  if (amount > 1_000_000_000 || (currency === "SOL" && amount > 1_000_000)) {
    return { minor: null, error: currency === "SOL" ? "SOL bankroll must not exceed 1,000,000." : "USDC bankroll must not exceed 1,000,000,000." };
  }
  const minor = Math.round(amount * 10 ** decimals);
  return Number.isSafeInteger(minor) && minor > 0
    ? { minor, error: null }
    : { minor: null, error: "That bankroll cannot be represented exactly." };
}
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
function formatLatency(milliseconds: number) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1_000) return `${Math.round(milliseconds).toLocaleString()}ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)}s`;
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
function riskModeLabel(mode: RiskMode) { return mode === "safe" ? "Safer" : title(mode); }
function drawdownProfileLabel(profile: SeasonProfile | null) {
  if (!profile) return "Legacy / unknown";
  if (profile.drawdown_policy.kind === "disabled") return "Off";
  const value = profile.effective_drawdown_bps === null ? "Unknown" : `${profile.effective_drawdown_bps / 100}%`;
  return profile.drawdown_policy.kind === "default" ? `${value} · Default` : `${value} · Custom`;
}
function drawdownPolicyTargetLabel(mode: RiskMode, policy: DrawdownPolicy, catalog: SeasonProfile[]) {
  if (policy.kind === "disabled") return "DD off";
  if (policy.kind === "custom") return `DD ${(policy.custom_threshold_bps ?? 0) / 100}%`;
  const profile = catalog.find((item) => item.risk_mode === mode);
  return `Default DD ${(profile?.effective_drawdown_bps ?? 0) / 100}%`;
}
function canonicalDrawdownPolicy(mode: RiskMode, policy: DrawdownPolicy, catalog: SeasonProfile[]): DrawdownPolicy {
  if (policy.kind !== "custom") return policy;
  const modeDefault = catalog.find((item) => item.risk_mode === mode && item.drawdown_policy.kind === "default");
  return policy.custom_threshold_bps === modeDefault?.effective_drawdown_bps
    ? { kind: "default", custom_threshold_bps: null }
    : policy;
}
function profileLimitSummary(profile: SeasonProfile | null) {
  if (!profile) return "Policy details unavailable";
  const positions = profile.risk_limits.max_open_positions;
  const exposure = profile.risk_limits.max_exposure_fraction;
  const drawdown = profile.effective_drawdown_bps;
  return `${positions} position${positions === 1 ? "" : "s"} · ${typeof exposure === "number" ? percent(exposure) : "—"} exposure · ${drawdown === null ? "DD off" : `${drawdown / 100}% DD`}`;
}
function shortDrawdownLabel(profile: SeasonProfile | null) {
  if (!profile) return "DD unavailable";
  if (profile.drawdown_policy.kind === "disabled") return "DD off";
  const value = profile.effective_drawdown_bps === null ? "DD unknown" : `DD ${profile.effective_drawdown_bps / 100}%`;
  return profile.drawdown_policy.kind === "default" ? `${value} default` : `${value} custom`;
}
function seasonComparisonKey(season: PaperSeason) {
  if (typeof season.comparison_key === "string" && season.comparison_key) {
    return season.comparison_key;
  }
  const exact = season.profile_provenance === "exact"
    && season.profile !== null
    && typeof season.profile_fingerprint === "string";
  return exact
    ? `${season.quote_currency}:bankroll:${season.starting_minor}:profile:${season.profile_fingerprint}:terminal:${season.terminal_policy_version ?? "legacy-v1"}`
    : `${season.quote_currency}:bankroll:${season.starting_minor}:legacy:terminal:${season.terminal_policy_version ?? "legacy-v1"}`;
}
function deriveSeasonComparisonGroups(seasons: PaperSeason[]): SeasonComparisonGroup[] {
  const groups = new Map<string, SeasonComparisonGroup>();
  for (const season of seasons) {
    const comparisonKey = seasonComparisonKey(season);
    const exact = season.profile_provenance === "exact"
      && season.profile !== null
      && typeof season.profile_fingerprint === "string";
    const existing = groups.get(comparisonKey);
    if (existing) {
      existing.season_count += 1;
      existing.first_season_number = Math.min(
        existing.first_season_number ?? season.season_number,
        season.season_number,
      );
      existing.last_season_number = Math.max(
        existing.last_season_number ?? season.season_number,
        season.season_number,
      );
      existing.has_current = Boolean(existing.has_current || season.status === "current");
      existing.completed_count = (existing.completed_count ?? 0) + Number(season.status === "completed");
      existing.comparable_count = (existing.comparable_count ?? 0)
        + Number(season.status === "completed" && season.comparable !== false);
      const boundary = season.boundary_type ?? "legacy";
      existing.boundary_types = existing.boundary_types?.includes(boundary)
        ? existing.boundary_types
        : [...(existing.boundary_types ?? []), boundary];
      continue;
    }
    groups.set(comparisonKey, {
      comparison_key: comparisonKey,
      quote_currency: season.quote_currency,
      quote_decimals: season.quote_decimals,
      starting_minor: season.starting_minor,
      terminal_policy_version: season.terminal_policy_version,
      profile_provenance: exact ? "exact" : "legacy_unknown",
      profile_fingerprint: exact ? season.profile_fingerprint : null,
      risk_mode: exact ? season.profile!.risk_mode : null,
      drawdown_policy: exact ? season.profile!.drawdown_policy : null,
      effective_drawdown_bps: exact ? season.profile!.effective_drawdown_bps : null,
      baseline_version: exact ? season.profile!.baseline_version ?? null : null,
      integrity_policy_version: exact ? season.profile!.integrity_policy_version ?? null : null,
      sizing_policy_version: exact ? season.profile!.sizing_policy_version ?? null : null,
      first_season_number: season.season_number,
      last_season_number: season.season_number,
      has_current: season.status === "current",
      completed_count: Number(season.status === "completed"),
      comparable_count: Number(season.status === "completed" && season.comparable !== false),
      boundary_types: [season.boundary_type ?? "legacy"],
      season_count: 1,
    });
  }
  return [...groups.values()].sort((left, right) => {
    const currencyOrder = left.quote_currency.localeCompare(right.quote_currency);
    if (currencyOrder !== 0) return currencyOrder;
    const bankrollOrder = (left.starting_minor ?? 0) - (right.starting_minor ?? 0);
    if (bankrollOrder !== 0) return bankrollOrder;
    if (left.profile_provenance !== right.profile_provenance) {
      return left.profile_provenance === "exact" ? -1 : 1;
    }
    return RISK_MODES.indexOf(left.risk_mode ?? "balanced")
      - RISK_MODES.indexOf(right.risk_mode ?? "balanced");
  });
}
function seasonComparisonGroupLabel(
  group: SeasonComparisonGroup | null,
  includeCurrency = true,
) {
  if (!group) return "Comparison unavailable";
  if (
    group.profile_provenance !== "exact"
    || group.risk_mode === null
    || group.drawdown_policy === null
  ) {
    const prefix = seasonComparisonBankrollLabel(group, includeCurrency);
    return `${prefix} · Legacy / unknown`;
  }
  const drawdown = group.drawdown_policy.kind === "disabled"
    ? "DD off"
    : `${group.drawdown_policy.kind === "default" ? "Default DD" : "Custom DD"} ${(group.effective_drawdown_bps ?? 0) / 100}%`;
  const label = `${riskModeLabel(group.risk_mode)} · ${drawdown}`;
  return `${seasonComparisonBankrollLabel(group, includeCurrency)} · ${label}`;
}
function seasonComparisonBankrollLabel(
  group: SeasonComparisonGroup,
  includeCurrency: boolean,
) {
  const decimals = group.quote_decimals ?? (group.quote_currency === "SOL" ? 9 : 6);
  const amount = group.starting_minor === undefined
    ? "amount unknown"
    : minorAmountInput(group.starting_minor, decimals);
  return includeCurrency ? `${group.quote_currency} ${amount}` : `${amount} ${group.quote_currency}`;
}
function seasonComparisonGroupContext(group: SeasonComparisonGroup) {
  const strategy = group.baseline_version
    ? group.baseline_version.replace("baseline-", "Baseline ")
    : "Legacy strategy";
  const accounting = group.terminal_policy_version === "executable-boundary-v2"
    ? "Modern accounting"
    : "Legacy accounting";
  const first = group.first_season_number;
  const last = group.last_season_number;
  const seasons = first === undefined || last === undefined
    ? `${group.season_count} season${group.season_count === 1 ? "" : "s"}`
    : first === last
      ? `S${first}`
      : `S${first}–S${last}`;
  const boundaries = (group.boundary_types ?? [])
    .filter((boundary) => boundary !== "open")
    .map(seasonBoundaryLabel);
  const boundary = group.has_current
    ? "Current"
    : boundaries.length
      ? [...new Set(boundaries)].join(" / ")
      : null;
  return [strategy, accounting, boundary, seasons].filter(Boolean).join(" · ");
}
function seasonBoundaryLabel(boundary: string) {
  if (boundary === "automatic") return "Automatic finish";
  if (boundary === "finish_safely") return "Safe finish";
  if (boundary === "end_now") return "Ended now";
  if (boundary === "reset") return "Manual reset";
  if (boundary === "legacy") return "Legacy boundary";
  if (boundary === "other") return "Other boundary";
  return humanize(boundary);
}
function terminalReasonLabel(reason: string) {
  if (reason === "profile_change") return "Profile change";
  if (reason === "profile_change_safe") return "Safe profile change";
  if (reason === "profile_change_manual") return "Profile changed now";
  if (reason === "auto_drawdown" || reason === "auto_drawdown_rollover") return "Drawdown halt";
  if (reason === "bankroll_exhausted") return "Bankroll exhausted";
  if (reason === "manual_reset") return "Manual reset";
  return humanize(reason);
}
