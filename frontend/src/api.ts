import type { AiDecisionMode, AiLabStatus, AiModelDownload, ChallengerJourneyPage, CoachStatus, Decision, DrawdownPolicy, HealthStatus, Leaderboard, LearningMode, LearningStatus, MaintenanceOperation, ProfileTransitionStrategy, ProviderSettings, ProviderSettingsUpdate, QuoteCurrency, RiskMode, SeasonAutomation, SeasonOperation, Seasons, Snapshot, StorageStatus } from "./types";

async function request<T>(path: string, init?: RequestInit, timeoutMs = 15_000): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort();
  init?.signal?.addEventListener("abort", abortFromCaller, { once: true });
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(body?.detail ?? `Request failed (${response.status})`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (timedOut) throw new Error("The app took too long to respond. Please try again.", { cause: error });
    throw error;
  } finally {
    window.clearTimeout(timeout);
    init?.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export const api = {
  health: () => request<HealthStatus>("/api/v1/health", undefined, 2_500),
  snapshot: () => request<Snapshot>("/api/v1/snapshot"),
  setRisk: (
    mode: RiskMode,
    drawdown_policy: DrawdownPolicy = { kind: "default", custom_threshold_bps: null },
    transition_strategy: ProfileTransitionStrategy = "finish_safely",
    quote_currency?: QuoteCurrency,
    starting_amount?: string,
  ) =>
    request<{ mode: RiskMode }>("/api/v1/risk", {
      method: "PUT",
      body: JSON.stringify({
        mode,
        drawdown_policy,
        transition_strategy,
        ...(quote_currency === undefined ? {} : { quote_currency }),
        ...(starting_amount === undefined ? {} : { starting_amount }),
      }),
    }),
  setSeasonAutomation: (enabled: boolean, grace_hours?: number) =>
    request<SeasonAutomation>("/api/v1/season-automation", {
      method: "PUT",
      body: JSON.stringify({ enabled, ...(grace_hours === undefined ? {} : { grace_hours }) }),
    }),
  setLearning: (mode: LearningMode) =>
    request<LearningStatus>("/api/v1/learning", {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
  championJourney: (cursor?: string, signal?: AbortSignal) => request<ChallengerJourneyPage>(
    `/api/v1/learning/champion-journey?limit=8${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    { signal },
  ),
  aiLab: () => request<AiLabStatus>("/api/v1/ai-lab"),
  setAiMode: (mode: AiDecisionMode) =>
    request<AiLabStatus>("/api/v1/ai-lab/mode", {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
  setCoachContribution: (enabled: boolean) =>
    request<CoachStatus>("/api/v1/ai-lab/coach-contribution", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  setCoachResearch: (enabled: boolean) =>
    request<CoachStatus>("/api/v1/ai-lab/coach-research", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  selectAiModel: (model: string) =>
    request<AiLabStatus>("/api/v1/ai-lab/model", {
      method: "PUT",
      body: JSON.stringify({ model }),
    }),
  pullAiModel: (model: string) =>
    request<AiModelDownload>("/api/v1/ai-lab/models/pull", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  removeAiModel: (model: string) =>
    request<AiLabStatus>("/api/v1/ai-lab/models", {
      method: "DELETE",
      body: JSON.stringify({ model }),
    }),
  setDemo: (demo_mode: boolean) =>
    request<{ demo_mode: boolean }>("/api/v1/mode", {
      method: "PUT",
      body: JSON.stringify({ demo_mode }),
    }),
  updateProviderSettings: (body: ProviderSettingsUpdate) =>
    request<{ provider_settings: ProviderSettings; source_restarted: boolean; paper_engine_stopped: boolean }>("/api/v1/provider-settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  updateStorageSettings: (max_database_gb: number, raw_trade_retention_hours: number) =>
    request<StorageStatus>("/api/v1/storage-settings", {
      method: "PUT",
      body: JSON.stringify({ max_database_gb, raw_trade_retention_hours }),
    }),
  leaderboard: (sort: "profit" | "loss" | "recent", signal?: AbortSignal) =>
    request<Leaderboard>(`/api/v1/leaderboard?sort=${sort}`, { signal }),
  seasons: (signal?: AbortSignal) => request<Seasons>("/api/v1/seasons", { signal }),
  decision: (id: string) => request<Decision>(`/api/v1/decisions/${id}`),
  setupPortfolio: (quote_currency: QuoteCurrency, starting_amount: string, risk_mode: RiskMode, drawdown_policy: DrawdownPolicy) =>
    request<{ initialized: true; quote_currency: QuoteCurrency; starting_minor: number; running: false }>("/api/v1/portfolio/setup", {
      method: "POST",
      body: JSON.stringify({ quote_currency, starting_amount, risk_mode, drawdown_policy }),
    }, 120_000),
  startEngine: () =>
    request<{ running: true }>("/api/v1/engine/start", { method: "POST" }),
  stopEngine: () =>
    request<{ running: false; cancelled_pending_orders: number }>("/api/v1/engine/stop", { method: "POST" }),
  prepareForUpgrade: () =>
    request<MaintenanceOperation>("/api/v1/maintenance/prepare", {
      method: "POST",
      body: JSON.stringify({ confirmation: "PREPARE FOR UPGRADE" }),
    }),
  cancelUpgradePreparation: () =>
    request<MaintenanceOperation>("/api/v1/maintenance/cancel", { method: "POST" }),
  reset: () =>
    request<SeasonOperation>("/api/v1/reset", {
      method: "POST",
      body: JSON.stringify({ confirmation: "RESET PAPER PORTFOLIO" }),
    }),
  explain: (id: string, signal?: AbortSignal) =>
    request<{ explanation: string; source: "local_ai" | "deterministic"; decision?: Decision }>(
      `/api/v1/decisions/${id}/explain`,
      { method: "POST", signal },
      40_000,
    ),
};
