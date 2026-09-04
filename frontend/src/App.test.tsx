import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";
import type { ChallengerSkillStatus, Decision, Fill, Position, SeasonAutomation, Snapshot } from "./types";

const arenaLayoutKey = "signal-arcade-arena-layout-v1";
const learningUiKey = "signal-arcade-learning-ui-v1";
const dismissedMaintenanceNoticeKey = "signal-arcade-dismissed-maintenance-notice-v1";

const activePosition: Position = {
  position_id: "position-personalized",
  mint: "mint-personalized",
  symbol: "PERSONALIZED",
  token_units: 1_000,
  entry_cost_lamports: 25_000_000,
  book_value_lamports: 24_000_000,
  opened_at: new Date().toISOString(),
  last_mark_lamports: 26_000_000,
  unrealized_pnl_lamports: 1_000_000,
  last_marked_at: new Date().toISOString(),
  mark_age_seconds: 0,
  mark_is_stale: false,
  mark_is_executable: true,
  mark_blockers: [],
  market_status: "active",
  risk_mode_at_entry: "balanced",
  peak_mark_lamports: 26_000_000,
  peak_marked_at: new Date().toISOString(),
  exit_assessment: null,
};

const decision: Decision = {
  decision_id: "decision-aaa",
  mint: "mint-aaa",
  symbol: "AAA",
  created_at: new Date().toISOString(),
  action: "watch",
  risk_mode: "balanced",
  score: {
    opportunity: 0.72,
    danger: 0.18,
    execution: 0.66,
    confidence: 0.81,
    net_edge_index: 0.03,
    composite: 74,
  },
  reasons: ["Buying activity is strengthening"],
  blockers: [],
  feature_snapshot: {
    mint: "mint-aaa",
    symbol: "AAA",
    name: "Alpha",
    venue: "pump",
    computed_at: new Date().toISOString(),
    values: {
      market_freshness: {
        value: 0,
        unit: "seconds",
        as_of: new Date().toISOString(),
        sources: ["test"],
        freshness_seconds: 0,
        quality: 1,
        missing_reason: null,
      },
    },
    data_confidence: 0.81,
    hard_flags: [],
  },
  model_version: "test",
  season_id: "season-test",
  configuration_fingerprint: "config-test",
  planned_order_size_sol: 0.025,
  integrity_assessment: {
    policy_version: "integrity-gates-v2",
    state: "clean",
    score: 0,
    coverage: 0.94,
    sample_count: 30,
    category_count: 0,
    categories: [],
    evidence: ["No corroborated manipulation pattern is present in the usable sample"],
  },
  sizing_assessment: {
    policy_version: "quality-size-v1",
    base_size_sol: 0.025,
    desired_size_sol: 0.08,
    selected_size_sol: 0.06,
    account_allocation_fraction: 0.018,
    constraints: ["price_impact_cap"],
    reasons: ["Clean, mature evidence allows bounded sizing from realized bankroll"],
  },
  learning_assessment: null,
};

const snapshot: Snapshot = {
  version: "1.4.4",
  running: true,
  service_running: true,
  started_at: new Date().toISOString(),
  server_time: new Date().toISOString(),
  demo_mode: true,
  paper_only: true,
  risk_mode: "balanced",
  season_profile: {
    schema_version: 1,
    provenance: "exact",
    risk_mode: "balanced",
    risk_policy_version: "risk-limits-v1",
    risk_limits: { max_open_positions: 4, max_exposure_fraction: 0.12 },
    drawdown_policy: { kind: "default", custom_threshold_bps: null },
    effective_drawdown_bps: 1500,
    profile_fingerprint: "balanced-default-profile",
    learning_fingerprint: "balanced-learning",
    locked_at: new Date().toISOString(),
  },
  season_profile_provenance: "exact",
  season_profile_catalog: [
    { schema_version: 1, provenance: "exact", risk_mode: "safe", risk_policy_version: "risk-limits-v1", risk_limits: { max_open_positions: 2, max_exposure_fraction: 0.05 }, drawdown_policy: { kind: "default", custom_threshold_bps: null }, effective_drawdown_bps: 800, profile_fingerprint: "safe-default-profile", learning_fingerprint: "safe-learning", locked_at: null },
    { schema_version: 1, provenance: "exact", risk_mode: "balanced", risk_policy_version: "risk-limits-v1", risk_limits: { max_open_positions: 4, max_exposure_fraction: 0.12 }, drawdown_policy: { kind: "default", custom_threshold_bps: null }, effective_drawdown_bps: 1500, profile_fingerprint: "balanced-default-profile", learning_fingerprint: "balanced-learning", locked_at: null },
    { schema_version: 1, provenance: "exact", risk_mode: "aggressive", risk_policy_version: "risk-limits-v1", risk_limits: { max_open_positions: 6, max_exposure_fraction: 0.2 }, drawdown_policy: { kind: "default", custom_threshold_bps: null }, effective_drawdown_bps: 2500, profile_fingerprint: "aggressive-default-profile", learning_fingerprint: "aggressive-learning", locked_at: null },
  ],
  candidate_window_minutes: 30,
  stale_market_seconds: 20,
  provider_health: { connected: true, synthetic: true },
  database_ok: true,
  events: {},
  event_pipeline: { queue_depth: 0, queue_capacity: 10_000, queue_utilization: 0, enqueued: 0, processed: 0, persisted: 0, ephemeral: 0, critical_processed: 0, dropped: 0, last_processed_at: null, last_source_event_at: null, processing_lag_seconds: 0, degraded: false, degraded_reasons: [] },
  portfolio: {
    initialized: true,
    quote_currency: "SOL",
    quote_decimals: 9,
    cash_lamports: 10_000_000_000,
    reserved_cash_lamports: 0,
    available_cash_lamports: 10_000_000_000,
    invested_value_lamports: 0,
    last_known_invested_value_lamports: 0,
    stale_invested_value_lamports: 0,
    stale_position_count: 0,
    route_blocked_invested_value_lamports: 0,
    route_blocked_position_count: 0,
    excluded_invested_value_lamports: 0,
    excluded_position_count: 0,
    starting_lamports: 10_000_000_000,
    equity_lamports: 10_000_000_000,
    last_known_equity_lamports: 10_000_000_000,
    realized_pnl_lamports: 0,
    unrealized_pnl_lamports: 0,
    drawdown_fraction: 0,
    risk_halted: false,
    risk_halt_reason: null,
    positions: [],
    pending_orders: [],
  },
  season_automation: {
    enabled: false,
    state: "off",
    detail: "Automatic seasons are off.",
    grace_seconds: 86_400,
    eligible_since: null,
    rollover_at: null,
    remaining_seconds: null,
    last_rollover_at: null,
  },
  season_operation: null,
  maintenance_operation: null,
  tokens: [],
  decisions: [],
  fills: [],
  equity_history: [],
  quotas: {},
  provider_settings: {
    providers: {
      solana: { active: false, endpoint: "https://api.mainnet-beta.solana.com", stream_endpoint: "wss://api.mainnet-beta.solana.com", custom_endpoint: false, policy: { label: "Public RPC", requests_per_minute: 120, monthly_limit: null, reserve_fraction: 0.1, paid_mode: false } },
      dexscreener: { active: false, endpoint: "https://api.dexscreener.com", custom_endpoint: false, policy: { label: "Free", requests_per_minute: 300, monthly_limit: null, reserve_fraction: 0.1, paid_mode: false } },
      jupiter: { active: false, endpoint: "https://api.jup.ag", api_key_configured: false, policy: { label: "Keyless", requests_per_minute: 30, monthly_limit: null, reserve_fraction: 0.1, paid_mode: false } },
      ollama: { active: true, endpoint: "http://127.0.0.1:11434", model: "qwen2.5:1.5b", policy: { label: "Local", requests_per_minute: 30, monthly_limit: null, reserve_fraction: 0.1, paid_mode: false } },
    },
    presets: { solana: [], jupiter: [] },
    secret_store_error: null,
    notes: { pump: "No Pump.fun API is called.", jupiter: "Optional.", monthly_pacing: "Paced.", streaming: "Streaming is provider-metered." },
  },
  learning: {
    mode: "shadow",
    state: "collecting",
    demo_excluded: true,
    collecting_from_current_source: false,
    live_only: true,
    observation_count: 0,
    usable_outcome_count: 0,
    pending_count: 0,
    unavailable_outcome_count: 0,
    minimum_training_samples: 80,
    retained_observation_limit: 5000,
    retained_model_limit: 1000,
    model_window_observations: 1000,
    entry_outcome_availability: {
      observed_count: 0,
      available_count: 0,
      availability_fraction: 0,
      minimum_fraction: 0.7,
      qualified: false,
    },
    outcomes_until_next_training: 80,
    challenger_interval_outcomes: 10,
    horizons_seconds: [60, 300, 600, 900, 1200],
    horizon_performance: [60, 300, 600, 900, 1200].map((horizon_seconds) => ({
      horizon_seconds,
      observed_count: 0,
      available_count: 0,
      availability_fraction: 0,
      mean_net_return: null,
      conservative_utility: null,
    })),
    recommended_hold_seconds: { safe: 300, balanced: 600, aggressive: 1200 },
    hold_timing_validation: Object.fromEntries(["safe", "balanced", "aggressive"].map((mode) => [mode, {
      qualified: false,
      selected_horizon_seconds: mode === "safe" ? 300 : mode === "balanced" ? 600 : 1200,
      baseline_horizon_seconds: mode === "safe" ? 300 : mode === "balanced" ? 600 : 1200,
      sample_count: 0,
      training_count: 0,
      validation_count: 0,
      embargoed_count: 0,
      selected_training_utility: null,
      baseline_training_utility: null,
      selected_validation_utility: null,
      baseline_validation_utility: null,
      validation_uplift_lower_bound: null,
      validation_availability_fraction: 0,
    }])) as Snapshot["learning"]["hold_timing_validation"],
    adaptive_hold_applied: false,
    latest_model: null,
    active_model: null,
    active_model_health: {
      state: "inactive",
      model_version: null,
      observed_count: 0,
      usable_count: 0,
      minimum_samples: 30,
      availability_fraction: 0,
      baseline_mean_return: null,
      learner_mean_return: null,
      estimated_uplift: null,
      uplift_upper_bound: null,
      supported_count: 0,
      vetoed_count: 0,
      winner_vetoed_count: 0,
    },
    activation_available: false,
    lessons: [],
    guardrails: ["Never trains on synthetic Demo Market data"],
  },
  ai_lab: {
    mode: "off",
    selected_model: "qwen3.5:4b",
    selected_model_installed: false,
    ollama_available: true,
    ollama_reachable: true,
    ollama_version: "0.33.1",
    deployment: "bundled",
    configured_accelerator: "cpu",
    runtime_compute: "idle",
    loaded_model_count: 0,
    loaded_model_bytes: 0,
    loaded_vram_bytes: 0,
    last_checked_at: new Date().toISOString(),
    system_memory_bytes: 16 * 1024 ** 3,
    catalog: [{ name: "qwen3.5:4b", label: "Qwen 3.5 · 4B", download_bytes: 3_400_000_000, recommended_ram_gb: 16, role: "Recommended mini-PC Shadow critic", installed: false, installed_bytes: null, digest: null, fits_recommended_ram: true }],
    downloads: [],
    queue_depth: 0,
    queue_capacity: 100,
    queue_drops: 0,
    inference_busy: false,
    qualification: { qualified: false, curated_model: true, model_digest: null, configuration_fingerprint: "config-test", assessments: 0, resolved: 0, minimum_resolved: 200, veto_outcomes: 0, minimum_veto_outcomes: 20, valid_fraction: 0, minimum_valid_fraction: 0.99, mean_counterfactual_uplift: null, uplift_lower_bound: null, p95_latency_ms: null, maximum_p95_latency_ms: 2500 },
    recent_assessments: [],
    model_storage: "ollama_external",
    model_storage_counts_toward_app_limit: false,
  },
  coach: {
    mode: "shadow",
    state: "waiting",
    influence: "none",
    worker_running: true,
    busy: false,
    paused_reason: null,
    last_error: null,
    last_attempt_at: null,
    review_interval_outcomes: 40,
    outcomes_seen: 0,
    outcomes_until_review: 40,
    minimum_forward_samples: 60,
    minimum_forward_seasons: 2,
    recent_hypotheses: [],
    recent_reviews: [],
    guardrails: [
      "The coach has no trading influence in Shadow mode.",
      "Only forward outcomes after a hypothesis is saved can support it.",
    ],
  },
  operational_incidents: [],
  storage: {
    market_events: 0, decisions: 0, paper_orders: 0, fills: 0, positions: 0,
    equity_points: 0, equity_rollups: 0, learning_observations: 0, learning_models: 0,
    ai_critic_assessments: 0, coach_reviews: 0, coach_hypotheses: 0,
    operational_incidents: 0,
    database_bytes: 0, live_bytes: 0, reclaimable_bytes: 0, wal_bytes: 0,
    total_disk_bytes: 0, max_database_bytes: 5 * 1024 ** 3,
    raw_trade_retention_hours: 6, maintenance_interval_seconds: 300, model_storage_included: false,
  },
};

function qualifiedLearningModel(version: string): NonNullable<Snapshot["learning"]["latest_model"]> {
  return {
    version,
    created_at: new Date().toISOString(),
    outcomes_seen: 120,
    risk_mode: "balanced",
    configuration_fingerprint: "config-test",
    sample_count: 120,
    resolved_count: 110,
    outcome_availability_fraction: 0.9,
    training_count: 80,
    validation_count: 30,
    embargoed_count: 10,
    validation_rmse: 0.08,
    naive_rmse: 0.1,
    learner_correlation: 0.2,
    baseline_correlation: 0.1,
    learner_top_mean_return: 0.04,
    baseline_top_mean_return: 0.01,
    overall_mean_return: 0.01,
    validation_in_distribution_fraction: 0.98,
    policy_validation_count: 30,
    policy_observed_count: 32,
    policy_outcome_availability_fraction: 0.94,
    policy_supported_count: 22,
    policy_veto_count: 8,
    policy_winner_veto_count: 0,
    policy_winner_veto_fraction: 0,
    policy_mean_uplift: 0.03,
    policy_uplift_lower_bound: 0.012,
    qualification_evidence_schema_version: "learning-evidence-v2",
    qualified: true,
  };
}

function challengerSkillStatus(
  skill: ChallengerSkillStatus["skill"],
  state: ChallengerSkillStatus["state"],
): ChallengerSkillStatus {
  const version = `challenger-skill-v1-${skill}`;
  const active = state === "active";
  return {
    skill,
    label: `${skill.charAt(0).toUpperCase()}${skill.slice(1)} skill`,
    state,
    latest_candidate: {
      version,
      created_at: new Date().toISOString(),
      skill,
      model_family: "linear",
      recipe_version: "linear-v1",
      outcomes_seen: 120,
      sample_count: 100,
      training_count: 70,
      validation_count: 30,
      embargoed_count: 4,
      qualified: true,
      metrics: {},
      parameters: {},
    },
    testing_version: state === "candidate_testing" ? version : null,
    champion: state === "collecting" ? null : {
      version,
      created_at: new Date().toISOString(),
      skill,
      model_family: "linear",
      recipe_version: "linear-v1",
      outcomes_seen: 120,
      sample_count: 100,
      training_count: 70,
      validation_count: 30,
      embargoed_count: 4,
      qualified: true,
      metrics: {},
      parameters: {},
    },
    active_version: active ? version : null,
    common_forward_count: active ? 30 : 0,
    tournament: active ? { result: "joined" } : {},
    health: {
      state: active ? "healthy" : "inactive",
      model_version: active ? version : null,
      observed_count: active ? 30 : 0,
      usable_count: active ? 30 : 0,
      minimum_samples: 30,
      availability_fraction: active ? 1 : 0,
      estimated_uplift: active ? 0.02 : null,
      uplift_upper_bound: active ? 0.04 : null,
    },
    gates: [{ id: "coverage", label: "Coverage", current: 1, target: 0.7, comparison: ">=", state: "passed", unit: "fraction", detail: "Forward route coverage" }],
  };
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("reconnects the live dashboard after a WebSocket interruption", async () => {
  class RecoveringWebSocket {
    static instances: RecoveringWebSocket[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: (() => void) | null = null;

    constructor() {
      RecoveringWebSocket.instances.push(this);
    }

    close() {}
  }

  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", RecoveringWebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }),
  );

  render(<App />);
  expect(RecoveringWebSocket.instances).toHaveLength(1);

  act(() => RecoveringWebSocket.instances[0]!.onclose?.());
  act(() => vi.advanceTimersByTime(999));
  expect(RecoveringWebSocket.instances).toHaveLength(1);
  await act(async () => vi.advanceTimersByTime(1));
  expect(RecoveringWebSocket.instances).toHaveLength(2);
});

test("renders the paper-only arena from a snapshot", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }),
  );
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  expect(screen.getByLabelText("Signal Arcade version 1.4.4")).toHaveTextContent("v1.4.4");
  expect(screen.getByText("Paper only")).toBeInTheDocument();
  expect(screen.getByText("Synthetic demo market")).toBeInTheDocument();
  expect(screen.getByText("Paper engine running")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "System status: all good" })).toBeInTheDocument();
});

test("shows a global strategy pause without misreporting service health", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...snapshot,
        portfolio: {
          ...snapshot.portfolio,
          drawdown_fraction: 0.1582,
          risk_halted: true,
          risk_halt_reason: "portfolio_drawdown_limit_reached",
        },
      }),
    }),
  );
  render(<App />);
  expect(await screen.findByRole("status", { name: "Risk paused" })).toHaveAttribute(
    "title",
    expect.stringContaining("15.8% drawdown"),
  );
  expect(screen.getByRole("button", { name: "System status: all good" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Replay" }));
  expect(screen.getByRole("status", { name: "Risk paused" })).toBeInTheDocument();
});

test("shows and safely toggles the guarded automatic season policy", async () => {
  const automatic = {
    ...snapshot,
    portfolio: {
      ...snapshot.portfolio,
      risk_halted: true,
      risk_halt_reason: "portfolio_drawdown_limit_reached",
    },
    season_automation: {
      ...snapshot.season_automation,
      enabled: true,
      state: "countdown" as const,
      detail: "3 dormant holdings; a new season starts in about 18h if none revives.",
      eligible_since: new Date().toISOString(),
      rollover_at: new Date(Date.now() + 18 * 60 * 60 * 1000).toISOString(),
      remaining_seconds: 18 * 60 * 60,
    },
  };
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input === "/api/v1/season-automation") {
      return { ok: true, json: async () => ({ ...automatic.season_automation, enabled: false }) };
    }
    return { ok: true, json: async () => automatic };
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  expect(await screen.findByText(/3 dormant holdings/)).toBeInTheDocument();
  expect(screen.getByLabelText("Automatic season status: 18h left")).toBeInTheDocument();
  const toggle = screen.getByRole("switch", { name: "Disable automatic new seasons" });
  expect(toggle).toHaveAttribute("aria-checked", "true");
  fireEvent.click(toggle);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/season-automation",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false }) }),
  ));
});

test.each([
  {
    name: "a live minute countdown",
    update: { state: "countdown", remaining_seconds: 3_900, verified_seconds: 120 },
    label: "Automatic season status: 1h 5m left",
  },
  {
    name: "verified time preserved during a data pause",
    update: { state: "paused", remaining_seconds: 1_380, verified_seconds: 2_220 },
    label: "Automatic season status: 37m / 1h saved",
  },
  {
    name: "a due rollover waiting for its safe boundary",
    update: { state: "due", remaining_seconds: 0, verified_seconds: 3_600 },
    label: "Automatic season status: Due now",
  },
  {
    name: "a countdown whose remaining telemetry is temporarily unavailable",
    update: { state: "countdown", remaining_seconds: null, verified_seconds: 120 },
    label: "Automatic season status: Counting",
  },
  {
    name: "a data pause whose verified telemetry is temporarily unavailable",
    update: { state: "paused", remaining_seconds: null, verified_seconds: null },
    label: "Automatic season status: Paused",
  },
  {
    name: "ordinary monitoring before a countdown starts",
    update: { state: "monitoring", remaining_seconds: null, verified_seconds: 0 },
    label: "Automatic season status: 1h rule",
  },
] as const)("shows $name in the automatic-season status chip", async ({ update, label }) => {
  const automation: SeasonAutomation = {
    ...snapshot.season_automation,
    enabled: true,
    grace_seconds: 3_600,
    detail: "Server-authoritative automatic season state.",
    ...update,
  };
  const current = { ...snapshot, season_automation: automation } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => current }));

  render(<App />);

  expect(await screen.findByLabelText(label)).toHaveAttribute("title", automation.detail);
});

test("saves a bounded automatic season delay before enabling it", async () => {
  let current = structuredClone(snapshot);
  const fetchMock = vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
    if (input === "/api/v1/season-automation") {
      const body = JSON.parse(String(init?.body)) as { enabled: boolean; grace_hours?: number };
      current = {
        ...current,
        season_automation: {
          ...current.season_automation,
          enabled: body.enabled,
          grace_seconds: (body.grace_hours ?? current.season_automation.grace_seconds / 3600) * 3600,
        },
      };
      return { ok: true, json: async () => current.season_automation };
    }
    return { ok: true, json: async () => current };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  const delay = await screen.findByLabelText("Automatic season wait");
  fireEvent.change(delay, { target: { value: "4" } });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/season-automation",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false, grace_hours: 4 }) }),
  ));
  expect(await screen.findByText(/Wait 4h after a guarded pause/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("switch", { name: "Enable automatic new seasons" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/season-automation",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true, grace_hours: 4 }) }),
  ));
});

test("keeps a reset operation visible across the whole app and blocks duplicate controls", async () => {
  const resetting = {
    ...snapshot,
    season_operation: {
      operation_id: "reset-one",
      kind: "reset" as const,
      state: "running" as const,
      stage: "archiving_season",
      detail: "Archiving the season and clearing only its active paper state.",
      started_at: new Date(Date.now() - 5_000).toISOString(),
      updated_at: new Date().toISOString(),
      completed_at: null,
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => resetting }));
  render(<App />);

  expect((await screen.findByText("Preparing the new season")).closest('[role="status"]')).toHaveTextContent("Archiving the season");
  expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Archiving the season and clearing only its active paper state.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start a new season" })).toBeDisabled();
});

test("uses a shortened mint instead of a broken question-mark token identity", async () => {
  const mint = "9abcDEFghijkLMNopqrstUVWxyz1234567890WXYZ";
  const label = "9abcDE…WXYZ";
  const unknownDecision: Decision = {
    ...decision,
    decision_id: "decision-unknown",
    mint,
    symbol: "?",
    action: "abstain",
    blockers: ["mint_safety_unverified"],
    feature_snapshot: {
      ...decision.feature_snapshot,
      mint,
      symbol: "?",
    },
  };
  const unknownSnapshot: Snapshot = { ...snapshot, decisions: [unknownDecision] };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => unknownSnapshot }),
  );

  render(<App />);
  expect(await screen.findByRole("button", { name: `Explain ${label} decision` })).toBeInTheDocument();
  expect(screen.getByText(label)).toHaveAttribute("title", mint);
  expect(screen.getByRole("button", { name: `Copy ${label} mint address` })).toHaveAttribute("title", mint);
  expect(screen.queryByText("?")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Decisions" }));
  fireEvent.click(screen.getByRole("button", { name: /Passed for now/i }));
  expect(screen.getByRole("button", { name: `Review ${label} decision details` })).toBeInTheDocument();
});

test("confirms a storage policy save without waiting for background refresh", async () => {
  let snapshotRequests = 0;
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input === "/api/v1/storage-settings") {
      return { ok: true, json: async () => snapshot.storage };
    }
    snapshotRequests += 1;
    if (snapshotRequests > 1) return new Promise(() => undefined);
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.change(screen.getByLabelText(/^Maximum database/), { target: { value: "2.5" } });
  fireEvent.change(screen.getByLabelText(/^Raw event history/), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByRole("button", { name: "Saved" })).toBeEnabled();
  expect(screen.getByText("Policy saved. Cleanup continues safely in the background.")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/storage-settings",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ max_database_gb: 2.5, raw_trade_retention_hours: 12 }),
    }),
  );
});

test("requires explicit confirmation before a market source archives the current season", async () => {
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    if (input === "/api/v1/mode") return new Promise(() => undefined);
    return Promise.resolve({ ok: true, json: async () => snapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("radio", { name: /Solana mainnet/ }));
  expect(screen.getByRole("alertdialog", { name: "Switch to Solana mainnet?" })).toHaveTextContent("archives the current paper season");
  expect(fetchMock.mock.calls.some(([path]) => path === "/api/v1/mode")).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "Keep Synthetic demo" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: /Solana mainnet/ }));
  fireEvent.click(screen.getByRole("button", { name: "Switch and archive season" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/mode",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ demo_mode: false }) }),
  ));
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("keeps future AI influence stages visible but unavailable", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Shadow Reviews" }));
  expect(screen.getAllByText("Shadow Decision Reviews").length).toBeGreaterThan(1);
  expect(screen.getByRole("button", { name: /Qualified Coach/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Live Critic/ })).toBeDisabled();
  expect(screen.getByRole("tooltip", { name: /Coach proof progress is shown above/ })).toBeInTheDocument();
  expect(screen.getByRole("tooltip", { name: /considered only after Qualified Coach proves useful/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Live Critic/ })).toHaveTextContent("No readiness measure yet");
  fireEvent.click(screen.getByRole("button", { name: /^ShadowObserves/ }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/mode",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ mode: "shadow" }) }),
  ));
});

test("keeps detailed learning evidence tidy until requested", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  const evidenceToggle = screen.getByRole("button", { name: "Show learning evidence" });
  const proofToggle = screen.getByRole("button", { name: "Show entry’s road to influence" });
  const journeyToggle = screen.getByRole("button", { name: "Show champion journey" });
  expect(evidenceToggle).toHaveAttribute("aria-expanded", "false");
  expect(proofToggle).toHaveAttribute("aria-expanded", "false");
  expect(journeyToggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Forward test")).not.toBeInTheDocument();
  expect(screen.queryByText("Learning can become selective; it cannot become reckless")).not.toBeInTheDocument();

  fireEvent.click(evidenceToggle);
  expect(screen.getByText("Forward test")).toBeInTheDocument();
  expect(screen.getByText("What it is noticing")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Safety" }));
  expect(screen.getByText("Learning can become selective; it cannot become reckless")).toBeInTheDocument();
});

test("organizes the Learning Lab by player and remembers its per-device layout", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  const first = render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByText("Acts on fresh market evidence")).not.toBeInTheDocument();
  expect(screen.queryByText("Forward test")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  const evidenceToggle = screen.getByRole("button", { name: "Show learning evidence" });
  expect(evidenceToggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(evidenceToggle);
  fireEvent.click(screen.getByRole("button", { name: "Show champion journey" }));
  expect(screen.getByText("Forward test")).toBeInTheDocument();
  await waitFor(() => expect(JSON.parse(window.localStorage.getItem(learningUiKey) ?? "null")).toMatchObject({
    version: 2,
    initialized: true,
    activeView: "challenger",
    expandedSections: ["champion_journey", "learning_evidence"],
  }));
  first.unmount();

  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByRole("tab", { name: "Challenger" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "Hide learning evidence" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("button", { name: "Hide champion journey" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Forward test")).toBeInTheDocument();
});

test("migrates the old Learning layout to a clean collapsed Overview", async () => {
  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 1,
    initialized: true,
    expandedSections: ["baseline", "challenger", "local_ai", "coach", "challenger_proof", "learning_evidence"],
    seenMilestoneIds: ["already-seen"],
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByText("Forward test")).not.toBeInTheDocument();
  await waitFor(() => expect(JSON.parse(window.localStorage.getItem(learningUiKey) ?? "null")).toMatchObject({
    version: 2,
    activeView: "overview",
    expandedSections: [],
    seenMilestoneIds: ["already-seen"],
  }));

  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByRole("button", { name: "Show learning evidence" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Show entry’s road to influence" })).toHaveAttribute("aria-expanded", "false");
});

test("brings a remembered Learning sub-tab into view on narrow screens", async () => {
  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 2,
    initialized: true,
    activeView: "safety",
    expandedSections: [],
    seenMilestoneIds: [],
  }));
  const scrollSpy = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  const safety = screen.getByRole("tab", { name: "Safety" });
  expect(safety).toHaveAttribute("aria-selected", "true");
  expect(scrollSpy).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
});

test("supports keyboard navigation between Learning sub-tabs", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  const overview = screen.getByRole("tab", { name: "Overview" });
  fireEvent.keyDown(overview, { key: "ArrowRight" });
  const baseline = screen.getByRole("tab", { name: "Baseline" });
  expect(baseline).toHaveAttribute("aria-selected", "true");
  await waitFor(() => expect(baseline).toHaveFocus());
  expect(screen.getByText("Acts on fresh market evidence")).toBeInTheDocument();
  fireEvent.keyDown(baseline, { key: "End" });
  const safety = screen.getByRole("tab", { name: "Safety" });
  expect(safety).toHaveAttribute("aria-selected", "true");
  await waitFor(() => expect(safety).toHaveFocus());
});

test("falls back safely when Learning preferences are corrupt or unavailable", async () => {
  window.localStorage.setItem(learningUiKey, "{not-json");
  const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (key: string, value: string) {
    if (key === learningUiKey) throw new DOMException("Storage unavailable", "SecurityError");
    window.localStorage.setItem(key, value);
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: "Baseline" }));
  expect(screen.getByText("Acts on fresh market evidence")).toBeInTheDocument();
  await waitFor(() => expect(setItem).toHaveBeenCalledWith(learningUiKey, expect.any(String)));
  setItem.mockRestore();
});

test("synchronizes Learning layout preferences changed in another browser tab", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 2,
    initialized: true,
    activeView: "coach",
    expandedSections: [],
    seenMilestoneIds: [],
  }));
  fireEvent(window, new StorageEvent("storage", { key: learningUiKey }));
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));

  await waitFor(() => expect(screen.getByRole("tab", { name: "AI Coach" })).toHaveAttribute("aria-selected", "true"));
  expect(screen.getByText("Slow, allowlisted experiments for the fast engine · Shadow-only")).toBeInTheDocument();
});

test("keeps a new milestone unread until the persisted Overview is actually visited", async () => {
  const readySnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      state: "ready" as const,
      activation_available: true,
      latest_model: qualifiedLearningModel("challenger-overview-notice"),
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 2,
    initialized: true,
    activeView: "challenger",
    expandedSections: [],
    seenMilestoneIds: [],
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => readySnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Learning" })).toHaveAttribute("title", "New learning milestone");

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByRole("tab", { name: "Challenger" })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByText("Qualified Challenger ready")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Learning" })).toHaveAttribute("title", "New learning milestone");

  fireEvent.click(screen.getByRole("tab", { name: /Overview/ }));
  expect(screen.getByText("Qualified Challenger ready")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Learning" })).not.toHaveAttribute("title"));
});

test("shows authoritative proof gates separately from the next Challenger evaluation", async () => {
  const proofSnapshot = {
    ...snapshot,
    demo_mode: false,
    learning: {
      ...snapshot.learning,
      collecting_from_current_source: true,
      state: "ready" as const,
      activation_available: true,
      outcomes_until_next_training: 4,
      latest_model: {
        version: "challenger-ready-1",
        created_at: new Date().toISOString(),
        outcomes_seen: 113,
        risk_mode: "balanced",
        configuration_fingerprint: "balanced-ready",
        sample_count: 113,
        resolved_count: 113,
        outcome_availability_fraction: 0.74,
        training_count: 80,
        validation_count: 25,
        embargoed_count: 8,
        validation_rmse: 0.08,
        naive_rmse: 0.1,
        learner_correlation: 0.2,
        baseline_correlation: 0.1,
        learner_top_mean_return: 0.04,
        baseline_top_mean_return: 0.01,
        overall_mean_return: 0.01,
        validation_in_distribution_fraction: 0.98,
        policy_validation_count: 30,
        policy_observed_count: 32,
        policy_outcome_availability_fraction: 0.94,
        policy_supported_count: 22,
        policy_veto_count: 8,
        policy_winner_veto_count: 0,
        policy_winner_veto_fraction: 0,
        policy_mean_uplift: 0.03,
        policy_uplift_lower_bound: 0.012,
        qualification_evidence_schema_version: "learning-evidence-v2",
        qualified: true,
      },
      qualification_passed: 2,
      qualification_total: 2,
      qualification_gates: [
        { id: "usable", label: "Usable outcomes", current: 113, target: 80, comparison: ">=" as const, state: "passed" as const, unit: "count" as const, detail: "Independent fee-inclusive outcomes." },
        { id: "coverage", label: "Current executable coverage", current: 0.74, target: 0.7, comparison: ">=" as const, state: "passed" as const, unit: "fraction" as const, detail: "Current exits remain measurable." },
      ],
      evidence_lanes: [
        { id: "discovery" as const, label: "Discovery", purpose: "Finds associations and proposes bounded contenders.", observed_count: 113, usable_count: 80, pending_count: 25, unavailable_count: 8, qualification_role: "proposal" as const },
        { id: "policy" as const, label: "Policy proof", purpose: "Judges untouched Baseline entries in this exact personality.", observed_count: 32, usable_count: 30, pending_count: 1, unavailable_count: 1, qualification_role: "authoritative" as const },
        { id: "execution" as const, label: "Paper executions", purpose: "Audits actual fills, exits, fees, and unresolved routes.", observed_count: 18, usable_count: 15, pending_count: 2, unavailable_count: 1, qualification_role: "audit" as const },
      ],
      evidence_contract: {
        evidence_schema_version: "learning-evidence-v2",
        feature_schema_version: "challenger-features-v4",
        baseline_version: "baseline-v1.4",
        collection_started_at: "2026-09-01T12:00:00Z",
      },
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({ version: 2, initialized: true, activeView: "overview", expandedSections: [], seenMilestoneIds: [] }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => proofSnapshot }));
  const first = render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  expect(screen.getByRole("button", { name: "Learning" })).toHaveAttribute("title", "New learning milestone");
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByText("Qualified Challenger ready")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Learning" })).not.toHaveAttribute("title"));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByText("Minimum 80 met · 4 more usable outcomes until the next challenger")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show entry’s road to influence" }));
  expect(screen.getByText("2 / 2 proof gates")).toBeInTheDocument();
  expect(screen.getByText("Current executable coverage")).toBeInTheDocument();
  expect(screen.getByText(/next evaluation timing is separate/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show learning evidence" }));
  const lanes = screen.getByRole("region", { name: "Separated learning evidence lanes" });
  expect(lanes).toHaveTextContent("Policy proof");
  expect(lanes).toHaveTextContent("Can qualify");
  expect(lanes).toHaveTextContent("30 usable");
  expect(screen.getByText(/Older evidence remains preserved but cannot silently qualify/)).toBeInTheDocument();
  await waitFor(() => expect(JSON.parse(window.localStorage.getItem(learningUiKey) ?? "null").seenMilestoneIds).toContain("challenger-ready-challenger-ready-1"));
  first.unmount();

  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Learning" })).not.toHaveAttribute("title");
});

test("does not announce historical Learning milestones on first use", async () => {
  const historical = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      state: "ready" as const,
      activation_available: true,
      latest_model: { version: "historical-ready", qualified: true } as NonNullable<Snapshot["learning"]["latest_model"]>,
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => historical }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Learning" })).not.toHaveAttribute("title"));
});

test("does not describe an already active Challenger as waiting to be enabled", async () => {
  const activeSnapshot = {
    ...snapshot,
    demo_mode: false,
    learning: {
      ...snapshot.learning,
      mode: "active" as const,
      state: "active" as const,
      collecting_from_current_source: true,
      activation_available: true,
      latest_model: qualifiedLearningModel("challenger-active-1"),
      active_model: qualifiedLearningModel("challenger-active-1"),
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({ version: 2, initialized: true, activeView: "overview", expandedSections: [], seenMilestoneIds: [] }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => activeSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByText("Qualified Challenger active")).toBeInTheDocument();
  expect(screen.queryByText("Qualified Challenger ready")).not.toBeInTheDocument();
});

test("shows each Challenger skill and the exact bounded active ensemble", async () => {
  const entrySkill = challengerSkillStatus("entry", "active");
  const manipulationSkill = challengerSkillStatus("manipulation", "active");
  const exitSkill = challengerSkillStatus("exit", "candidate_testing");
  exitSkill.testing_version = "challenger-skill-v2-exit";
  exitSkill.latest_candidate = {
    ...exitSkill.latest_candidate!,
    version: exitSkill.testing_version,
    model_family: "xgboost",
    recipe_version: "shallow-hist-v1",
  };
  exitSkill.testing_candidate = exitSkill.latest_candidate;
  exitSkill.pending_versions = ["challenger-skill-v3-exit"];
  exitSkill.common_forward_count = 18;
  const skills: ChallengerSkillStatus[] = [
    entrySkill,
    manipulationSkill,
    challengerSkillStatus("sizing", "qualified"),
    exitSkill,
  ];
  const championEvent = {
    event_id: "champion-event-sizing-promoted",
    occurred_at: new Date().toISOString(),
    skill: "sizing" as const,
    kind: "promoted" as const,
    candidate_version: "challenger-skill-v2-sizing",
    previous_champion_version: "challenger-skill-v1-sizing",
    champion_version: "challenger-skill-v2-sizing",
    candidate_codename: "Violet Balancer",
    previous_champion_codename: "Quiet Steward",
    champion_codename: "Violet Balancer",
    champion_generation: 2,
    common_observed_count: 32,
    common_usable_count: 30,
    availability_fraction: 0.9375,
    mean_uplift: 0.03,
    uplift_lower_bound: 0.012,
    candidate_model_family: "linear" as const,
    candidate_recipe_version: "linear-v1",
    champion_model_family: "linear" as const,
    champion_recipe_version: "linear-v1",
    previous_champion_model_family: "linear" as const,
    resolution: "The contender proved the required safe advantage and replaced the saved Champion.",
  };
  const skillSnapshot = {
    ...snapshot,
    demo_mode: false,
    learning: {
      ...snapshot.learning,
      mode: "active" as const,
      state: "active" as const,
      collecting_from_current_source: true,
      consent_granted: true,
      active_skill_versions: {
        entry: entrySkill.active_version!,
        manipulation: manipulationSkill.active_version!,
      },
      skills,
      nonlinear_entry: {
        state: "collecting" as const,
        eligible_training_count: 181,
        minimum_training_samples: 250,
        required_linear_improvement_fraction: 0.02,
        latest_artifact: null,
        entry_only: true as const,
      },
      champion_records: [{
        skill: "sizing" as const,
        champion_version: championEvent.champion_version,
        champion_codename: "Violet Balancer",
        champion_generation: 2,
        model_family: "linear" as const,
        recipe_version: "linear-v1",
        crowned_at: championEvent.occurred_at,
        retained_count: 4,
        inconclusive_count: 1,
        recorded_battle_count: 5,
        active: false,
        influence_state: "shadow" as const,
        history_complete: true,
      }],
      champion_journey: [championEvent],
      champion_journey_total: 1,
      champion_journey_next_cursor: null,
      champion_journey_cohort_key: "balanced-current-cohort",
      challenger_common_forward_minimum: 30,
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => skillSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByText(/2 bounded skills active/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Entry skill");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Manipulation skill");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Sizing skill");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Exit skill");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Contender");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Best proved");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("18 / 30 shared outcomes");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("Nonlinear XGBoost");
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent("1 queued");
  expect(screen.getByText("Nonlinear contender")).toBeInTheDocument();
  expect(screen.getByText("181 / 250 training rows")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "XGBoost Entry training eligibility" })).toHaveAttribute("aria-valuenow", "181");
  expect(screen.getByRole("region", { name: "Reigning Champions" })).toHaveTextContent("Champion v2 · Violet Balancer");
  expect(screen.getByRole("region", { name: "Reigning Champions" })).toHaveTextContent("4 crown retentions · 1 inconclusive");
  const journeyToggle = screen.getByRole("button", { name: "Show champion journey" });
  expect(journeyToggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("A Champion means safer forward proof, never guaranteed profit.")).not.toBeInTheDocument();
  fireEvent.click(journeyToggle);
  expect(screen.getByText("Violet Balancer replaced Quiet Steward")).toBeInTheDocument();
  expect(screen.getByText(/30 shared outcomes · \+1\.2% conservative edge/)).toBeInTheDocument();
  expect(screen.getByText(/never guaranteed profit/)).toBeInTheDocument();
  const viewBattle = screen.getByRole("button", { name: "View battle" });
  fireEvent.click(viewBattle);
  const battle = screen.getByRole("dialog", { name: "New Champion earned" });
  expect(battle).toHaveTextContent("Violet Balancer replaced Quiet Steward");
  expect(battle).toHaveTextContent("30");
  expect(battle).toHaveTextContent("93.8%");
  expect(battle).toHaveTextContent("The contender proved the required safe advantage");
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "New Champion earned" })).not.toBeInTheDocument();
  await waitFor(() => expect(viewBattle).toHaveFocus());

  const proofToggle = screen.getByRole("button", { name: "Show entry’s road to influence" });
  expect(proofToggle).toHaveTextContent("Entry ·");
  fireEvent.click(proofToggle);
  expect(screen.getByText("Entry is the Challenger’s foundation.")).toBeInTheDocument();
});

test("loads older Champion battles without duplicating the bounded initial history", async () => {
  const now = new Date();
  const first = {
    event_id: "champion-event-newest",
    occurred_at: now.toISOString(),
    skill: "exit" as const,
    kind: "defended" as const,
    candidate_version: "exit-contender-two",
    candidate_codename: "Quiet Navigator",
    previous_champion_version: "exit-champion-one",
    previous_champion_codename: "Clear Harbormaster",
    champion_version: "exit-champion-one",
    champion_codename: "Clear Harbormaster",
    champion_generation: 1,
    common_observed_count: 32,
    common_usable_count: 30,
    availability_fraction: 0.9375,
    mean_uplift: 0,
    uplift_lower_bound: 0,
    resolution: "The contender did not prove the safe advantage required for replacement.",
  };
  const older = {
    ...first,
    event_id: "champion-event-first",
    occurred_at: new Date(now.getTime() - 60_000).toISOString(),
    kind: "first_champion" as const,
    candidate_version: "exit-champion-one",
    candidate_codename: "Clear Harbormaster",
    previous_champion_version: null,
    previous_champion_codename: null,
    common_observed_count: 0,
    common_usable_count: 0,
    availability_fraction: 0,
    mean_uplift: null,
    uplift_lower_bound: null,
  };
  const historySnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      champion_journey: [first],
      champion_journey_total: 2,
      champion_journey_next_cursor: first.event_id,
      champion_journey_cohort_key: "history-pagination-cohort",
    },
  } satisfies Snapshot;
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/learning/champion-journey")) {
      return { ok: true, json: async () => ({ events: [older], total: 2, next_cursor: null }) };
    }
    return { ok: true, json: async () => historySnapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  fireEvent.click(screen.getByRole("button", { name: "Show champion journey" }));
  expect(screen.getByText("Clear Harbormaster retained the crown against Quiet Navigator")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load older battles" }));

  expect(await screen.findByText("Clear Harbormaster was crowned")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "View battle" })).toHaveLength(2);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/learning/champion-journey?limit=8&cursor=champion-event-newest",
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});

test("distinguishes different battle artifacts that share a friendly codename", async () => {
  const collisionEvent = {
    event_id: "champion-event-codename-collision",
    occurred_at: new Date().toISOString(),
    skill: "exit" as const,
    kind: "defended" as const,
    candidate_version: "exit-contender-collision",
    candidate_codename: "Clear Harbormaster",
    previous_champion_version: "exit-champion-collision",
    previous_champion_codename: "Clear Harbormaster",
    champion_version: "exit-champion-collision",
    champion_codename: "Clear Harbormaster",
    champion_generation: 1,
    common_observed_count: 30,
    common_usable_count: 30,
    availability_fraction: 1,
    mean_uplift: 0,
    uplift_lower_bound: 0,
  };
  const collisionSnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      champion_journey: [collisionEvent],
      champion_journey_total: 1,
      champion_journey_next_cursor: null,
      champion_journey_cohort_key: "codename-collision-cohort",
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => collisionSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  fireEvent.click(screen.getByRole("button", { name: "Show champion journey" }));
  expect(screen.getByText(
    "Clear Harbormaster (saved Champion) retained the crown against Clear Harbormaster (contender)",
  )).toBeInTheDocument();
});

test("does not invent Champion history for a pre-existing saved Champion", async () => {
  const legacyChampion = challengerSkillStatus("entry", "qualified");
  const legacySnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      skills: [legacyChampion],
      champion_journey: [],
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => legacySnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByText("Waiting for first Champion")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show champion journey" }));
  expect(screen.getByText(/Existing Champions remain valid/)).toBeInTheDocument();
  expect(screen.getByText(/does not invent past battles/)).toBeInTheDocument();
});

test("explains low executable coverage while a Challenger battle is still open", async () => {
  const skill = challengerSkillStatus("entry", "candidate_testing");
  skill.testing_version = "challenger-skill-v2-entry";
  skill.latest_candidate = { ...skill.latest_candidate!, version: skill.testing_version };
  skill.common_forward_count = 45;
  skill.tournament = {
    result: "collecting",
    common_observed_count: 75,
    common_usable_count: 45,
    availability_fraction: 0.60,
  };
  const lowCoverageSnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      skills: [skill],
      challenger_common_forward_minimum: 30,
      challenger_minimum_availability: 0.70,
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => lowCoverageSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByRole("region", { name: "Challenger skills" })).toHaveTextContent(
    "60.0% coverage · needs 70.0%",
  );
});

test("acknowledges only milestones that were actually visible", async () => {
  const hypotheses = ["one", "two", "three"].map((suffix) => ({
    hypothesis_id: `coach-${suffix}`,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    cutoff_at: new Date().toISOString(),
    kind: "entry_veto" as const,
    state: "testing" as const,
    title: `Coach idea ${suffix}`,
    rationale: "A bounded Shadow experiment.",
    risk_mode: "balanced" as const,
    model_name: "qwen3.5:4b",
    feature_name: "momentum_1m",
    operator: "<=" as const,
    threshold: -0.05,
    hold_seconds: null,
    discovery_observed_count: 120,
    discovery_usable_count: 100,
    discovery_availability_fraction: 0.83,
    discovery_mean_uplift: 0.03,
    discovery_uplift_lower_bound: 0.012,
    forward_observed_count: 10,
    forward_usable_count: 8,
    forward_availability_fraction: 0.8,
    forward_season_count: 1,
    forward_mean_uplift: null,
    forward_uplift_lower_bound: null,
    forward_uplift_upper_bound: null,
    minimum_forward_samples: 60,
    minimum_availability_fraction: 0.7,
    last_evaluated_at: new Date().toISOString(),
    influence_applied: false as const,
    context_active: true,
  }));
  const crowdedSnapshot = {
    ...snapshot,
    learning: {
      ...snapshot.learning,
      state: "ready" as const,
      activation_available: true,
      latest_model: qualifiedLearningModel("challenger-crowded"),
    },
    coach: { ...snapshot.coach, state: "testing" as const, recent_hypotheses: hypotheses },
    ai_lab: {
      ...snapshot.ai_lab,
      qualification: {
        ...snapshot.ai_lab.qualification,
        qualified: true,
        configuration_fingerprint: "qualified-config",
      },
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({ version: 2, initialized: true, activeView: "overview", expandedSections: [], seenMilestoneIds: [] }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => crowdedSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  await waitFor(() => {
    const seen = JSON.parse(window.localStorage.getItem(learningUiKey) ?? "null").seenMilestoneIds as string[];
    expect(seen).toEqual(expect.arrayContaining([
      "challenger-ready-challenger-crowded",
      "coach-coach-one-testing",
      "coach-coach-two-testing",
    ]));
    expect(seen).not.toContain("coach-coach-three-testing");
    expect(seen).not.toContain("ai-shadow-proof-qualified-config");
  });
});

test("labels a persisted legacy guarded mode without unlocking future roadmap stages", async () => {
  const guardedSnapshot: Snapshot = {
    ...snapshot,
    ai_lab: { ...snapshot.ai_lab, mode: "guarded" },
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => guardedSnapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Shadow Reviews" }));
  expect(screen.getByText("Qualified Coach (legacy)")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Qualified Coach/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /^Off/ }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/mode",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ mode: "off" }) }),
  ));
});

test("shows bounded local AI failures as safely ignored instead of raw errors", async () => {
  const timedOutSnapshot: Snapshot = {
    ...snapshot,
    ai_lab: {
      ...snapshot.ai_lab,
      mode: "shadow",
      selected_model: "qwen3.5:4b",
      selected_model_installed: true,
      inference_busy: true,
      catalog: snapshot.ai_lab.catalog.map((model) => ({ ...model, installed: true })),
      recent_assessments: [{
        assessment_id: "assessment-timeout",
        decision_id: "decision-timeout",
        mint: "MintTimeout111111111111111111111111111111111",
        symbol: "WAIT",
        created_at: "2026-01-01T00:00:00Z",
        mode: "shadow",
        applied: false,
        model_name: "qwen3.5:2b",
        input_sha256: "abc",
        input_payload: {},
        latency_ms: 28_000,
        valid: false,
        invalid_reason: "ollama_unavailable_or_timed_out",
        verdict: null,
        confidence: null,
        evidence_refs: [],
        risk_flags: [],
        summary: "",
        outcome_net_return: null,
        counterfactual_uplift: null,
        outcome_missing_reason: null,
        resolved_at: null,
      }],
    },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => timedOutSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Shadow Reviews" }));
  expect(screen.getByText("Timed out")).toBeInTheDocument();
  expect(screen.getByText("Ignored safely")).toBeInTheDocument();
  expect(screen.getByText(/missed its bounded time budget/)).toBeInTheDocument();
  expect(screen.getByText(/CPU · working/)).toBeInTheDocument();
});

test("starts a curated model download from Settings without blocking the page", async () => {
  const fetchMock = vi.fn().mockImplementation(async (input: string) => ({
    ok: true,
    json: async () => input === "/api/v1/ai-lab/models/pull"
      ? { model: "qwen3.5:4b", status: "queued", completed_bytes: 0, total_bytes: 3_400_000_000, progress_fraction: 0, message: "Waiting for Ollama", error: null }
      : snapshot,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Runtime ready")).toBeInTheDocument();
  expect(screen.getByText("Bundled Docker service")).toBeInTheDocument();
  expect(screen.getByText("Local AI models")).toBeInTheDocument();
  expect(screen.getByText(/GB download/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Download" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/models/pull",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ model: "qwen3.5:4b" }) }),
  ));
  expect(screen.getByText("Data providers")).toBeInTheDocument();
});

test("removes an installed local model only after inline confirmation", async () => {
  const installedSnapshot = {
    ...snapshot,
    ai_lab: {
      ...snapshot.ai_lab,
      selected_model_installed: true,
      catalog: snapshot.ai_lab.catalog.map((model) => ({
        ...model,
        installed: true,
        installed_bytes: model.download_bytes,
        digest: "digest-installed",
      })),
    },
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => installedSnapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show local AI models" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(screen.getByRole("button", { name: "Remove model" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove model" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/models",
    expect.objectContaining({ method: "DELETE", body: JSON.stringify({ model: "qwen3.5:4b" }) }),
  ));
});

test("serializes local model mutations across every model row", async () => {
  const installedSnapshot: Snapshot = {
    ...snapshot,
    ai_lab: {
      ...snapshot.ai_lab,
      selected_model: "qwen3.5:4b",
      selected_model_installed: true,
      catalog: [
        { ...snapshot.ai_lab.catalog[0]!, installed: true, installed_bytes: 3_400_000_000, digest: "digest-four" },
        { ...snapshot.ai_lab.catalog[0]!, name: "qwen3.5:2b", label: "Qwen 3.5 · 2B", installed: true, installed_bytes: 2_000_000_000, digest: "digest-two" },
      ],
    },
  };
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    if (input === "/api/v1/ai-lab/model") return new Promise(() => undefined);
    return Promise.resolve({ ok: true, json: async () => installedSnapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show local AI models" }));
  expect(screen.getAllByRole("button", { name: "Remove" }).some((button) => button.title.includes("turns the AI Decision Lab off"))).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Select" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/model",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ model: "qwen3.5:2b" }) }),
  ));
  expect(screen.getByRole("button", { name: "Select" })).toBeDisabled();
  screen.getAllByRole("button", { name: "Remove" }).forEach((button) => expect(button).toBeDisabled());
});

test("keeps core settings visible while secondary model and provider details stay tidy", async () => {
  const installedSnapshot: Snapshot = {
    ...snapshot,
    ai_lab: {
      ...snapshot.ai_lab,
      selected_model_installed: true,
      catalog: snapshot.ai_lab.catalog.map((model) => ({
        ...model,
        installed: true,
        installed_bytes: model.download_bytes,
        digest: "digest-installed",
      })),
    },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => installedSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Data health")).toBeInTheDocument();
  expect(screen.getByText("0 processed · 0 transient · 0 saved · 0 shed · 0 expired")).toBeInTheDocument();
  expect(screen.getByText("Storage budget")).toBeInTheDocument();
  expect(screen.getByText("Selected model")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Show local AI models" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Show data providers" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Runtime ready")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Manage" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Show local AI models" }));
  expect(screen.getByText("Runtime ready")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hide local AI models" })).toHaveAttribute("aria-expanded", "true");

  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  expect(screen.getByRole("button", { name: "Manage" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hide data providers" })).toHaveAttribute("aria-expanded", "true");
});

test("confirms upgrade preparation and blocks app controls while it settles", async () => {
  const startedAt = new Date().toISOString();
  const runningOperation = {
    operation_id: "upgrade-running",
    kind: "upgrade" as const,
    state: "running" as const,
    stage: "settling_paper_actions",
    detail: "Finishing the current atomic paper action and cancelling unfilled orders.",
    started_at: startedAt,
    updated_at: startedAt,
    ready_at: null,
    completed_at: null,
    prepared_version: "1.6.6",
    restarted_version: null,
    previous_running: true,
    auto_season_remaining_seconds: 3_600,
    cancelled_pending_orders: 0,
    interrupted_ai_downloads: 0,
  };
  let current: Snapshot = snapshot;
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input === "/api/v1/maintenance/prepare") {
      current = { ...snapshot, running: false, maintenance_operation: runningOperation };
      return { ok: true, json: async () => runningOperation };
    }
    return { ok: true, json: async () => current };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Prepare for upgrade" }));
  expect(screen.getByText("Prepare Signal Arcade for an update?")).toBeInTheDocument();
  expect(screen.getByText(/does not expose the Docker socket/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Prepare safely" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/maintenance/prepare",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ confirmation: "PREPARE FOR UPGRADE" }),
    }),
  ));
  expect(await screen.findByText("Preparing Signal Arcade for an update")).toBeInTheDocument();
  expect(screen.getAllByText(/Finishing the current atomic paper action/)).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Start a new season" })).toBeDisabled();
});

test("shows host update commands only after preparation is ready and can resume safely", async () => {
  const now = new Date().toISOString();
  const readyOperation = {
    operation_id: "upgrade-ready",
    kind: "upgrade" as const,
    state: "ready" as const,
    stage: "ready",
    detail: "Signal Arcade is ready. Open positions and learning remain preserved.",
    started_at: now,
    updated_at: now,
    ready_at: now,
    completed_at: null,
    prepared_version: "1.6.6",
    restarted_version: null,
    previous_running: true,
    auto_season_remaining_seconds: 3_600,
    cancelled_pending_orders: 2,
    interrupted_ai_downloads: 1,
  };
  let current: Snapshot = { ...snapshot, running: false, maintenance_operation: readyOperation };
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input === "/api/v1/maintenance/cancel") {
      const cancelled = { ...readyOperation, state: "cancelled" as const, stage: "cancelled", completed_at: new Date().toISOString() };
      current = { ...snapshot, maintenance_operation: cancelled };
      return { ok: true, json: async () => cancelled };
    }
    return { ok: true, json: async () => current };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Ready for the Docker update")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("docker compose pull")).toBeInTheDocument();
  expect(screen.getByText("docker compose up -d")).toBeInTheDocument();
  expect(screen.getByText("docker compose up -d --build")).toBeInTheDocument();
  expect(screen.getByText(/2 unfilled orders cancelled/)).toBeInTheDocument();
  expect(screen.getByText(/Restart 1 model download/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel and resume without updating" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/maintenance/cancel",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByRole("button", { name: "Prepare for upgrade" })).toBeEnabled();
});

test("shows only a recent completion for the running version and remembers dismissal", async () => {
  const now = new Date().toISOString();
  const completedOperation = {
    operation_id: "upgrade-completed-current",
    kind: "upgrade" as const,
    state: "completed" as const,
    stage: "restarted",
    detail: "The app restarted safely.",
    started_at: now,
    updated_at: now,
    ready_at: now,
    completed_at: now,
    prepared_version: "1.4.3",
    restarted_version: snapshot.version,
    previous_running: true,
    auto_season_remaining_seconds: 3_600,
    cancelled_pending_orders: 0,
    interrupted_ai_downloads: 0,
  };
  const completedSnapshot: Snapshot = { ...snapshot, maintenance_operation: completedOperation };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => completedSnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText(`Updated safely from v1.4.3 to v${snapshot.version}.`)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss update confirmation" }));
  expect(screen.queryByText(`Updated safely from v1.4.3 to v${snapshot.version}.`)).not.toBeInTheDocument();
  expect(window.localStorage.getItem(dismissedMaintenanceNoticeKey)).toBe(completedOperation.operation_id);

  cleanup();
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.queryByText(`Updated safely from v1.4.3 to v${snapshot.version}.`)).not.toBeInTheDocument();
});

test("hides stale or malformed maintenance completions and labels same-version restarts accurately", async () => {
  const now = new Date().toISOString();
  const baseOperation = {
    operation_id: "upgrade-completed-edge",
    kind: "upgrade" as const,
    state: "completed" as const,
    stage: "restarted",
    detail: "The app restarted safely.",
    started_at: now,
    updated_at: now,
    ready_at: now,
    completed_at: now,
    prepared_version: snapshot.version,
    restarted_version: snapshot.version,
    previous_running: true,
    auto_season_remaining_seconds: null,
    cancelled_pending_orders: 0,
    interrupted_ai_downloads: 0,
  };
  let current: Snapshot = {
    ...snapshot,
    maintenance_operation: { ...baseOperation, restarted_version: "1.7.2" },
  };
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => ({ ok: true, json: async () => current })));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.queryByText(/Updated safely from/)).not.toBeInTheDocument();

  cleanup();
  current = { ...snapshot, maintenance_operation: { ...baseOperation, completed_at: "not-a-date" } };
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.queryByText(/Restarted safely on/)).not.toBeInTheDocument();

  cleanup();
  current = {
    ...snapshot,
    maintenance_operation: {
      ...baseOperation,
      completed_at: new Date(Date.parse(snapshot.server_time) - 25 * 60 * 60 * 1_000).toISOString(),
    },
  };
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.queryByText(/Restarted safely on/)).not.toBeInTheDocument();

  cleanup();
  current = { ...snapshot, maintenance_operation: baseOperation };
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText(`Restarted safely on v${snapshot.version}.`)).toBeInTheDocument();
});

test("shows ranked realized results with a link back to entry evidence", async () => {
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return {
        ok: true,
        json: async () => ({
          sort: "profit",
          available_rows: 1,
          summary: { closed_trades: 1, open_trades: 0, wins: 1, losses: 0, total_realized_pnl_minor: 500_000_000, audited_exits: 1, winner_reversals: 0, average_peak_capture_fraction: 0.8, total_fees_minor: 30_000, quote_currency: "SOL", quote_decimals: 9 },
          rows: [{
            mint: "mint-winner", symbol: "WIN", status: "closed", pnl_minor: 500_000_000, last_known_pnl_minor: 500_000_000,
            return_fraction: 0.5, fees_minor: 30_000, opened_at: new Date().toISOString(),
            closed_at: new Date().toISOString(), hold_seconds: 45, exit_reason: "take_profit",
            exit_assessment: { policy_version: "adaptive-exit-v1", evaluated_at: new Date().toISOString(), action: "exit", reason: "take_profit", support_score: 0.42, pnl_fraction: 0.5, peak_return_fraction: 0.62, drawdown_from_peak_fraction: 0.08, age_seconds: 45, soft_hold_seconds: 600, hard_hold_seconds: 1800, evidence: ["5m buy ratio 41%", "1m momentum -4.0%"] },
            peak_return_fraction: 0.62, peak_capture_fraction: 0.8, entry_risk_mode: "balanced",
            entry_decision_id: "decision-win", mark_is_stale: false, market_status: "closed", mark_is_executable: true,
            quote_currency: "SOL", quote_decimals: 9,
          }],
        }),
      };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));

  expect(await screen.findByText("Wins, losses, and the evidence behind them.")).toBeInTheDocument();
  expect(screen.getByText("WIN")).toBeInTheDocument();
  expect(screen.getAllByText("+0.500 SOL")).toHaveLength(2);
  expect(screen.getByText("Realized net P/L").closest("article")).toHaveTextContent("+0.500 SOL");
  expect(screen.getByText("Simulated fees").closest("article")).toHaveTextContent("0.00003 SOL");
  expect(screen.getByText(/Most profit and Most loss rank closed trades/i)).toBeInTheDocument();
  expect(screen.getByText(/1 of 1 closed trade includes saved exit evidence/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Why it bought/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open WIN on GMGN" })).toHaveAttribute("href", "https://gmgn.ai/sol/token/mint-winner");
  fireEvent.click(screen.getByRole("button", { name: "Take profit" }));
  expect(screen.getByText("Why it sold")).toBeInTheDocument();
  expect(screen.getByText("5m buy ratio 41% · 1m momentum -4.0%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Take profit" }).closest(".leaderboard-outcome")).not.toBeNull();
  expect(screen.getByText("0.00003 SOL fees")).toHaveClass("leaderboard-mobile-fee");
});

test("keeps impossible legacy timing visible for audit without ranking its profit", async () => {
  const now = new Date().toISOString();
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      const recent = input.includes("sort=recent");
      return {
        ok: true,
        json: async () => ({
          sort: recent ? "recent" : "profit",
          available_rows: recent ? 1 : 0,
          summary: { closed_trades: 0, open_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, invalid_results: 1, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0, quote_currency: "USDC", quote_decimals: 6 },
          rows: recent ? [{
            mint: "legacy-impossible", symbol: "OLD", status: "closed", pnl_minor: 30_460_000, last_known_pnl_minor: 30_460_000,
            return_fraction: 1.56, fees_minor: 480_000, opened_at: now, closed_at: now, hold_seconds: null,
            audit_status: "invalid", audit_reason: "sell predates its paper position", exit_reason: "take_profit", exit_assessment: null,
            peak_return_fraction: 1.89, peak_capture_fraction: null, entry_risk_mode: "balanced", entry_decision_id: null,
            mark_is_stale: false, market_status: "closed", mark_is_executable: true, quote_currency: "USDC", quote_decimals: 6,
          }] : [],
        }),
      };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  expect(await screen.findByText("Legacy result not counted")).toBeInTheDocument();
  expect(screen.queryByText("OLD")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Latest" }));
  expect(await screen.findByText("OLD")).toBeInTheDocument();
  expect(screen.getByText("Not counted")).toBeInTheDocument();
  expect(screen.getByText("sell predates its paper position")).toBeInTheDocument();
  expect(screen.getByText("Execution audit")).toBeInTheDocument();
});

test("audit-pauses a quarantined current season without hiding its preserved figures", async () => {
  const quarantined: Snapshot = {
    ...snapshot,
    running: false,
    paper_execution_audit: {
      status: "quarantined",
      issues: [{
        fill_id: "bad-fill",
        order_id: "bad-order",
        mint: "bad-mint",
        side: "sell",
        reason: "sell predates its paper position",
      }],
    },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => quarantined }));
  render(<App />);

  expect(await screen.findByText("Paper engine audit-paused")).toBeInTheDocument();
  expect(screen.getByText("Current season preserved but not trusted")).toBeInTheDocument();
  expect(screen.getByText(/1 impossible execution record was detected/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Audit hold" })).toBeDisabled();
  expect(screen.getByText("Paper equity")).toBeInTheDocument();
});

test("labels capped current-season trade views and explains where open positions appear", async () => {
  const now = new Date().toISOString();
  const closedRow = {
    mint: "mint-capped", symbol: "CAP", status: "closed" as const, pnl_minor: 10_000_000, last_known_pnl_minor: 10_000_000,
    return_fraction: 0.1, fees_minor: 50_000, opened_at: now, closed_at: now, hold_seconds: 30,
    exit_reason: "take_profit", exit_assessment: null, peak_return_fraction: 0.1, peak_capture_fraction: null,
    entry_risk_mode: "balanced" as const, entry_decision_id: null, mark_is_stale: false,
    market_status: "closed" as const, mark_is_executable: true, quote_currency: "SOL" as const, quote_decimals: 9,
  };
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      const recent = input.includes("sort=recent");
      return { ok: true, json: async () => ({
        sort: recent ? "recent" : "profit",
        available_rows: recent ? 130 : 125,
        summary: { closed_trades: 125, open_trades: 5, wins: 60, losses: 65, total_realized_pnl_minor: -1_000_000, audited_exits: 125, winner_reversals: 8, average_peak_capture_fraction: 0.5, total_fees_minor: 4_000_000, quote_currency: "SOL", quote_decimals: 9 },
        rows: [recent ? { ...closedRow, mint: "mint-open", symbol: "OPEN", status: "open", closed_at: null, exit_reason: null, market_status: "active" } : closedRow],
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  expect(await screen.findByText("Showing 1 of 125 closed trades, highest net results first.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Latest" }));
  expect(await screen.findByText("Showing 1 of 130 current-season trades, newest first.")).toBeInTheDocument();
  expect(screen.getByText("Still open")).toBeInTheDocument();
});

test("keeps trades as the default Results view and separates legacy currencies", async () => {
  const now = new Date().toISOString();
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({
        generated_at: now,
        summary: { season_count: 2, completed_seasons: 1, profitable_seasons: 1, losing_seasons: 0, average_win_rate: 2 / 3, best_return_fraction: 0.2 },
        seasons: [
          { season_id: "season-1", season_number: 1, started_at: now, ended_at: now, quote_currency: "SOL", quote_decimals: 9, starting_minor: 1_000_000_000, ending_equity_minor: 1_200_000_000, last_known_ending_equity_minor: 1_200_000_000, peak_equity_minor: 1_250_000_000, realized_pnl_minor: 200_000_000, net_pnl_minor: 200_000_000, total_fees_minor: 2_000_000, closed_trades: 3, wins: 2, losses: 1, break_even: 0, ending_drawdown_fraction: 0.04, open_positions: 0, status: "completed", win_rate: 2 / 3, net_return_fraction: 0.2, duration_seconds: 86_400 },
          { season_id: "season-2", season_number: 2, started_at: now, ended_at: null, quote_currency: "USDC", quote_decimals: 6, starting_minor: 100_000_000, ending_equity_minor: 105_000_000, last_known_ending_equity_minor: 105_000_000, peak_equity_minor: 110_000_000, realized_pnl_minor: 5_000_000, net_pnl_minor: 5_000_000, total_fees_minor: 500_000, closed_trades: 2, wins: 1, losses: 1, break_even: 0, ending_drawdown_fraction: 0.045, open_positions: 1, status: "current", win_rate: 0.5, net_return_fraction: 0.05, duration_seconds: 3_600 },
        ],
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  expect(await screen.findByText("Wins, losses, and the evidence behind them.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Trades" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Exit evidence and winner reversals will appear after the first closed trade.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Seasons" }));
  expect(await screen.findByText("Is the strategy improving each season?")).toBeInTheDocument();
  expect(await screen.findByText("Season 2")).toBeInTheDocument();
  expect(screen.queryByText("Season 1")).not.toBeInTheDocument();
  expect(screen.getByText("Now 105.00 USDC")).toBeInTheDocument();
  expect(screen.getByText("Legacy policy unknown")).toBeInTheDocument();
  expect(screen.queryByText("Best completed")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Season comparison" }));
  fireEvent.click(within(screen.getByRole("dialog", { name: "Choose season comparison" })).getByRole("radio", { name: /^All seasons/ }));
  expect(screen.getByText("Ended 1.200 SOL")).toBeInTheDocument();
  expect(screen.getByText("Mixed comparison history")).toBeInTheDocument();
  expect(screen.queryByText("Best completed")).not.toBeInTheDocument();
});

test("filters every season view by exact profile and marks all-profile history as mixed", async () => {
  const now = new Date().toISOString();
  const balancedDefault = snapshot.season_profile!;
  const balancedOff = {
    ...balancedDefault,
    drawdown_policy: { kind: "disabled" as const, custom_threshold_bps: null },
    effective_drawdown_bps: null,
    profile_fingerprint: "balanced-off-profile",
  };
  const aggressiveDefault = snapshot.season_profile_catalog.find((profile) => profile.risk_mode === "aggressive")!;
  const makeSeason = (season_number: number, profile: typeof balancedDefault, status: "current" | "completed", net: number) => ({
    season_id: `profile-season-${season_number}`, season_number, started_at: now,
    ended_at: status === "current" ? null : now, quote_currency: "SOL" as const, quote_decimals: 9,
    starting_minor: 1_000_000_000, ending_equity_minor: 1_000_000_000 + net,
    last_known_ending_equity_minor: 1_000_000_000 + net, peak_equity_minor: 1_100_000_000,
    realized_pnl_minor: net, net_pnl_minor: net, total_fees_minor: 1_000_000,
    closed_trades: status === "current" ? 0 : 10, wins: status === "current" ? 0 : 6,
    losses: status === "current" ? 0 : 4, break_even: 0, ending_drawdown_fraction: 0.1,
    open_positions: status === "current" ? 1 : 0, status,
    win_rate: status === "current" ? null : 0.6, net_return_fraction: net / 1_000_000_000,
    duration_seconds: 3_600, risk_mode: profile.risk_mode,
    profile_fingerprint: profile.profile_fingerprint, profile, profile_provenance: "exact" as const,
    profile_locked_at: profile.locked_at, terminal_reason: status === "current" ? null : "auto_drawdown",
    terminal_policy_version: "executable-boundary-v2", accounting_status: status === "current" ? "current" as const : "complete" as const,
    boundary_type: status === "current" ? "open" : "automatic", meaningful_activity: true, comparable: true,
  });
  const seasons = [
    makeSeason(1, balancedDefault, "completed", -100_000_000),
    makeSeason(2, balancedOff, "completed", 500_000_000),
    makeSeason(3, aggressiveDefault, "completed", 400_000_000),
    makeSeason(4, balancedDefault, "current", 0),
    {
      ...makeSeason(5, balancedDefault, "completed", 10_000_000),
      season_id: "profile-season-5-usdc",
      quote_currency: "USDC" as const,
      quote_decimals: 6,
    },
  ];
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({
        generated_at: now,
        current_profile_fingerprint: balancedDefault.profile_fingerprint,
        profiles: [
          { profile_fingerprint: balancedDefault.profile_fingerprint, risk_mode: "balanced", drawdown_policy: balancedDefault.drawdown_policy, effective_drawdown_bps: 1_500, season_count: 2 },
          { profile_fingerprint: balancedOff.profile_fingerprint, risk_mode: "balanced", drawdown_policy: balancedOff.drawdown_policy, effective_drawdown_bps: null, season_count: 1 },
          { profile_fingerprint: aggressiveDefault.profile_fingerprint, risk_mode: "aggressive", drawdown_policy: aggressiveDefault.drawdown_policy, effective_drawdown_bps: 2_500, season_count: 1 },
        ],
        seasons,
        summary: { season_count: 5, completed_seasons: 4, profitable_seasons: 3, losing_seasons: 1, average_win_rate: 0.6, best_return_fraction: 0.5 },
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));
  const comparisonTrigger = await screen.findByRole("button", { name: "Season comparison" });
  const chooseComparison = (name: RegExp) => {
    fireEvent.click(comparisonTrigger);
    const dialog = screen.getByRole("dialog", { name: "Choose season comparison" });
    fireEvent.click(within(dialog).getByRole("radio", { name }));
  };
  expect(screen.getByText("Season 1")).toBeInTheDocument();
  expect(screen.getByText("Season 4")).toBeInTheDocument();
  expect(screen.queryByText("Season 2")).not.toBeInTheDocument();
  expect(screen.queryByText("Season 5")).not.toBeInTheDocument();
  fireEvent.click(comparisonTrigger);
  const picker = screen.getByRole("dialog", { name: "Choose season comparison" });
  expect(within(picker).getByRole("region", { name: "SOL seasons" })).toBeInTheDocument();
  expect(within(picker).getByRole("region", { name: "USDC seasons" })).toBeInTheDocument();
  fireEvent.click(within(picker).getByRole("radio", { name: /^All seasons/ }));
  expect(screen.getByText("All seasons · mixed settings")).toBeInTheDocument();
  expect(screen.getByText("Season 2")).toBeInTheDocument();
  expect(screen.getByText("Season 3")).toBeInTheDocument();
  expect(screen.getByText("Season 5")).toBeInTheDocument();
  expect(screen.getByText("Mixed comparison history")).toBeInTheDocument();

  chooseComparison(/^All SOL seasons/);
  expect(screen.getByText("All SOL · mixed settings")).toBeInTheDocument();
  expect(screen.getByText("Groups").closest("article")).toHaveTextContent("3");
  expect(screen.queryByText("Season 5")).not.toBeInTheDocument();

  chooseComparison(/^1 SOL · Balanced · DD off/);
  expect(screen.getByText("SOL 1 · Balanced · DD off")).toBeInTheDocument();
  expect(screen.getByText("Season 2")).toBeInTheDocument();
  expect(screen.queryByText("Season 1")).not.toBeInTheDocument();

  chooseComparison(/^1000 USDC · Balanced · Default DD 15%/);
  expect(screen.getByText("USDC 1000 · Balanced · Default DD 15%")).toBeInTheDocument();
  expect(screen.getByText("Season 5")).toBeInTheDocument();
  expect(screen.queryByText("Season 4")).not.toBeInTheDocument();
});

test("distinguishes matching season settings by strategy and accounting generation on mobile", async () => {
  const now = new Date().toISOString();
  const customDrawdown = { kind: "custom" as const, custom_threshold_bps: 2_000 };
  const oldProfile = {
    ...snapshot.season_profile!,
    profile_fingerprint: "balanced-custom-old",
    drawdown_policy: customDrawdown,
    effective_drawdown_bps: 2_000,
  };
  const currentProfile = {
    ...oldProfile,
    profile_fingerprint: "balanced-custom-current",
    baseline_version: "baseline-v1.3",
  };
  const makeSeason = (
    seasonNumber: number,
    profile: typeof oldProfile,
    terminalPolicy: string,
    boundaryType: "legacy" | "reset" | "open",
    status: "completed" | "current",
  ) => ({
    season_id: `generation-season-${seasonNumber}`,
    season_number: seasonNumber,
    started_at: now,
    ended_at: status === "current" ? null : now,
    quote_currency: "USDC" as const,
    quote_decimals: 6,
    starting_minor: 200_000_000,
    ending_equity_minor: 200_000_000,
    last_known_ending_equity_minor: 200_000_000,
    peak_equity_minor: 200_000_000,
    realized_pnl_minor: 0,
    net_pnl_minor: 0,
    total_fees_minor: 0,
    closed_trades: status === "current" ? 0 : 1,
    wins: 0,
    losses: status === "current" ? 0 : 1,
    break_even: 0,
    ending_drawdown_fraction: 0,
    open_positions: 0,
    status,
    win_rate: status === "current" ? null : 0,
    net_return_fraction: 0,
    duration_seconds: 3_600,
    risk_mode: "balanced" as const,
    profile_fingerprint: profile.profile_fingerprint,
    profile,
    profile_provenance: "exact" as const,
    profile_locked_at: profile.locked_at,
    terminal_reason: status === "current" ? null : "manual_reset",
    terminal_policy_version: terminalPolicy,
    accounting_status: status === "current" ? "current" as const : "complete" as const,
    boundary_type: boundaryType,
    meaningful_activity: true,
    comparable: terminalPolicy === "executable-boundary-v2",
  });
  const seasons = [
    makeSeason(12, oldProfile, "legacy-v1", "legacy", "completed"),
    makeSeason(13, oldProfile, "legacy-v1", "legacy", "completed"),
    makeSeason(14, oldProfile, "executable-boundary-v2", "reset", "completed"),
    makeSeason(15, currentProfile, "executable-boundary-v2", "open", "current"),
  ];
  const oldLegacyKey = "USDC:bankroll:200000000:profile:balanced-custom-old:terminal:legacy-v1";
  const oldModernKey = "USDC:bankroll:200000000:profile:balanced-custom-old:terminal:executable-boundary-v2";
  const currentKey = "USDC:bankroll:200000000:profile:balanced-custom-current:terminal:executable-boundary-v2";
  const group = (
    comparisonKey: string,
    terminalPolicy: string,
    first: number,
    last: number,
    seasonCount: number,
    boundaryTypes: string[],
    hasCurrent: boolean,
    profileFingerprint: string,
    baselineVersion: string | null,
  ) => ({
    comparison_key: comparisonKey,
    quote_currency: "USDC" as const,
    quote_decimals: 6,
    starting_minor: 200_000_000,
    terminal_policy_version: terminalPolicy,
    profile_provenance: "exact" as const,
    profile_fingerprint: profileFingerprint,
    risk_mode: "balanced" as const,
    drawdown_policy: customDrawdown,
    effective_drawdown_bps: 2_000,
    baseline_version: baselineVersion,
    integrity_policy_version: baselineVersion ? "integrity-gates-v2" : null,
    sizing_policy_version: baselineVersion ? "quality-size-v1" : null,
    first_season_number: first,
    last_season_number: last,
    has_current: hasCurrent,
    completed_count: hasCurrent ? 0 : seasonCount,
    comparable_count: terminalPolicy === "executable-boundary-v2" && !hasCurrent ? seasonCount : 0,
    boundary_types: boundaryTypes,
    season_count: seasonCount,
  });
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({
        generated_at: now,
        current_profile_fingerprint: currentProfile.profile_fingerprint,
        current_comparison_key: currentKey,
        profiles: [],
        comparison_groups: [
          group(oldLegacyKey, "legacy-v1", 12, 13, 2, ["legacy"], false, oldProfile.profile_fingerprint, null),
          group(oldModernKey, "executable-boundary-v2", 14, 14, 1, ["reset"], false, oldProfile.profile_fingerprint, null),
          {
            comparison_key: currentKey,
            quote_currency: "USDC",
            quote_decimals: 6,
            starting_minor: 200_000_000,
            terminal_policy_version: "executable-boundary-v2",
            profile_provenance: "exact",
            profile_fingerprint: currentProfile.profile_fingerprint,
            risk_mode: "balanced",
            drawdown_policy: customDrawdown,
            effective_drawdown_bps: 2_000,
            season_count: 1,
          },
        ],
        seasons,
        summary: { season_count: 4, completed_seasons: 3, comparable_seasons: 1, comparison_group_count: 3, comparison_claims_available: false, profitable_seasons: 0, losing_seasons: 1, average_win_rate: 0, best_return_fraction: 0 },
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));

  const trigger = await screen.findByRole("button", { name: "Season comparison" });
  fireEvent.click(trigger);
  const picker = screen.getByRole("dialog", { name: "Choose season comparison" });
  expect(within(picker).getAllByRole("radio")).toHaveLength(5);
  expect(within(picker).getByRole("radio", { name: /Current comparison.*Baseline v1\.3.*Current.*S15/ })).toBeInTheDocument();
  expect(within(picker).getByRole("radio", { name: /Legacy strategy.*Legacy accounting.*Legacy boundary.*S12–S13/ })).toBeInTheDocument();
  expect(within(picker).getByRole("radio", { name: /Legacy strategy.*Modern accounting.*Manual reset.*S14/ })).toBeInTheDocument();
  expect(within(picker).getAllByRole("radio", { name: /^200 USDC · Balanced · Custom DD 20%/ })).toHaveLength(2);

  fireEvent.click(within(picker).getByRole("radio", { name: /Legacy accounting.*S12–S13/ }));
  expect(screen.getByText("Season 12")).toBeInTheDocument();
  expect(screen.getByText("Season 13")).toBeInTheDocument();
  expect(screen.queryByText("Season 14")).not.toBeInTheDocument();

  fireEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Choose season comparison" })).toBeInTheDocument();
  expect(document.body.style.overflow).toBe("hidden");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Choose season comparison" })).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("");
  expect(document.activeElement).toBe(trigger);
});

test("defaults completed-only season history to the honest all-seasons selection", async () => {
  const now = new Date().toISOString();
  const profile = snapshot.season_profile!;
  const comparisonKey = `SOL:bankroll:1000000000:profile:${profile.profile_fingerprint}:terminal:executable-boundary-v2`;
  const completedSeason = {
    season_id: "completed-only-season",
    season_number: 7,
    started_at: now,
    ended_at: now,
    quote_currency: "SOL" as const,
    quote_decimals: 9,
    starting_minor: 1_000_000_000,
    ending_equity_minor: 950_000_000,
    last_known_ending_equity_minor: 950_000_000,
    peak_equity_minor: 1_000_000_000,
    realized_pnl_minor: -50_000_000,
    net_pnl_minor: -50_000_000,
    total_fees_minor: 1_000_000,
    closed_trades: 1,
    wins: 0,
    losses: 1,
    break_even: 0,
    ending_drawdown_fraction: 0.05,
    open_positions: 0,
    status: "completed" as const,
    win_rate: 0,
    net_return_fraction: -0.05,
    duration_seconds: 3_600,
    risk_mode: profile.risk_mode,
    profile_fingerprint: profile.profile_fingerprint,
    profile,
    profile_provenance: "exact" as const,
    profile_locked_at: profile.locked_at,
    terminal_reason: "manual_reset",
    terminal_policy_version: "executable-boundary-v2",
    accounting_status: "complete" as const,
    boundary_type: "reset",
    meaningful_activity: true,
    comparable: true,
  };
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({
        generated_at: now,
        current_profile_fingerprint: null,
        current_comparison_key: null,
        profiles: [],
        comparison_groups: [{
          comparison_key: comparisonKey,
          quote_currency: "SOL",
          quote_decimals: 9,
          starting_minor: 1_000_000_000,
          terminal_policy_version: "executable-boundary-v2",
          profile_provenance: "exact",
          profile_fingerprint: profile.profile_fingerprint,
          risk_mode: profile.risk_mode,
          drawdown_policy: profile.drawdown_policy,
          effective_drawdown_bps: profile.effective_drawdown_bps,
          season_count: 1,
        }],
        seasons: [completedSeason],
        summary: { season_count: 1, completed_seasons: 1, comparable_seasons: 1, comparison_group_count: 1, comparison_claims_available: true, profitable_seasons: 0, losing_seasons: 1, average_win_rate: 0, best_return_fraction: -0.05 },
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));

  const trigger = await screen.findByRole("button", { name: "Season comparison" });
  expect(trigger).toHaveTextContent("All seasons");
  expect(screen.getByText("Season 7")).toBeInTheDocument();
  fireEvent.click(trigger);
  const picker = screen.getByRole("dialog", { name: "Choose season comparison" });
  expect(within(picker).queryByRole("region", { name: "Current" })).not.toBeInTheDocument();
  expect(within(picker).getByRole("radio", { name: /^All seasons/ })).toHaveAttribute("aria-checked", "true");
});

test("scales season history past 100 scorecards without hiding or deleting older seasons", async () => {
  const now = new Date().toISOString();
  const seasons = Array.from({ length: 105 }, (_, index) => {
    const seasonNumber = index + 1;
    const current = seasonNumber === 105;
    const measured = !current && seasonNumber % 17 !== 0;
    const winRate = measured ? (seasonNumber % 70 + 15) / 100 : null;
    const netReturn = current ? -0.01 : ((seasonNumber % 13) - 6) / 100;
    return {
      season_id: `season-${seasonNumber}`,
      season_number: seasonNumber,
      started_at: now,
      ended_at: current ? null : now,
      quote_currency: "SOL",
      quote_decimals: 9,
      starting_minor: 1_000_000_000,
      ending_equity_minor: 1_000_000_000 + Math.round(netReturn * 1_000_000_000),
      last_known_ending_equity_minor: 1_000_000_000 + Math.round(netReturn * 1_000_000_000),
      peak_equity_minor: 1_100_000_000,
      realized_pnl_minor: Math.round(netReturn * 1_000_000_000),
      net_pnl_minor: Math.round(netReturn * 1_000_000_000),
      total_fees_minor: 1_000_000,
      closed_trades: measured ? 20 : 0,
      wins: winRate === null ? 0 : Math.round(winRate * 20),
      losses: winRate === null ? 0 : 20 - Math.round(winRate * 20),
      break_even: 0,
      ending_drawdown_fraction: 0.08,
      open_positions: current ? 1 : 0,
      status: current ? "current" : "completed",
      win_rate: winRate,
      net_return_fraction: netReturn,
      duration_seconds: 3_600,
    } as const;
  }).reverse();
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({
        generated_at: now,
        summary: { season_count: 105, completed_seasons: 104, profitable_seasons: 48, losing_seasons: 56, average_win_rate: 0.49, best_return_fraction: 0.06 },
        seasons,
      }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));
  expect(await screen.findByText("Complete season history")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Latest 10" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("img", { name: /Latest 10 of 105 seasons, Seasons 96 through 105/ })).toBeInTheDocument();

  const seasonTable = screen.getByRole("table", { name: "Paper season scorecards" });
  const initialRows = Array.from(seasonTable.querySelectorAll(".season-identity > strong"), (node) => node.textContent);
  expect(initialRows).toHaveLength(20);
  expect(initialRows).toContain("Season 105");
  expect(initialRows).toContain("Season 86");
  expect(initialRows).not.toContain("Season 1");

  fireEvent.click(screen.getByRole("button", { name: "Latest 25" }));
  expect(screen.getByRole("img", { name: /Latest 25 of 105 seasons, Seasons 81 through 105/ })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "All" }));
  expect(screen.getByRole("img", { name: /All 105 seasons/ })).toBeInTheDocument();
  const historyPath = container.querySelector(".season-line-path");
  expect(historyPath).not.toBeNull();
  expect(historyPath?.getAttribute("d")).not.toContain("NaN");
  expect(container.querySelectorAll(".season-line-point")).toHaveLength(98);

  fireEvent.click(screen.getByRole("button", { name: "Show 20 older" }));
  expect(screen.getByText("Showing 40 of 105")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show all 105 seasons" }));
  const allRows = Array.from(seasonTable.querySelectorAll(".season-identity > strong"), (node) => node.textContent);
  expect(allRows).toHaveLength(105);
  expect(allRows.at(-1)).toBe("Season 1");
  expect(screen.queryByText(/older scorecards safely retained/)).not.toBeInTheDocument();
});

test("bounds an extreme all-season chart while preserving endpoints, extremes, and missing-data gaps", async () => {
  const now = new Date().toISOString();
  const seasons = Array.from({ length: 1001 }, (_, index) => {
    const seasonNumber = index + 1;
    const current = seasonNumber === 1001;
    const measured = seasonNumber % 97 !== 0;
    const winRate = measured ? ((seasonNumber * 37) % 101) / 100 : null;
    const netReturn = ((seasonNumber % 17) - 8) / 100;
    return {
      season_id: `long-season-${seasonNumber}`, season_number: seasonNumber, started_at: now,
      ended_at: current ? null : now, quote_currency: "SOL", quote_decimals: 9,
      starting_minor: 1_000_000_000, ending_equity_minor: 1_000_000_000 + Math.round(netReturn * 1_000_000_000),
      last_known_ending_equity_minor: 1_000_000_000 + Math.round(netReturn * 1_000_000_000), peak_equity_minor: 1_100_000_000,
      realized_pnl_minor: Math.round(netReturn * 1_000_000_000), net_pnl_minor: Math.round(netReturn * 1_000_000_000), total_fees_minor: 1_000_000,
      closed_trades: measured ? 100 : 0, wins: winRate === null ? 0 : Math.round(winRate * 100), losses: winRate === null ? 0 : 100 - Math.round(winRate * 100), break_even: 0,
      ending_drawdown_fraction: 0.08, open_positions: current ? 1 : 0, status: current ? "current" : "completed",
      win_rate: winRate, net_return_fraction: netReturn, duration_seconds: 3_600,
    };
  });
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", available_rows: 0, summary: { closed_trades: 0, open_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0, quote_currency: "SOL", quote_decimals: 9 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({ generated_at: now, seasons, summary: { season_count: 1001, completed_seasons: 1000, profitable_seasons: 471, losing_seasons: 470, average_win_rate: 0.5, best_return_fraction: 0.08 } }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));
  fireEvent.click(await screen.findByRole("button", { name: "All" }));
  expect(screen.getByRole("img", { name: /All 1001 seasons/ })).toBeInTheDocument();
  const sampledPoints = container.querySelectorAll(".season-line-point");
  expect(sampledPoints.length).toBeGreaterThan(100);
  expect(sampledPoints.length).toBeLessThanOrEqual(240);
  expect(screen.getByText(/representative trend points · all exact values remain below/i)).toBeInTheDocument();
  const path = container.querySelector(".season-line-path")?.getAttribute("d") ?? "";
  expect((path.match(/M/g) ?? []).length).toBeGreaterThan(1);
  expect(container.querySelector(".season-line-point title")?.textContent).toContain("Season 1:");
  expect(Array.from(container.querySelectorAll(".season-line-point title")).at(-1)?.textContent).toContain("Season 1001:");
  const sampledTitles = Array.from(container.querySelectorAll(".season-line-point title"), (node) => node.textContent ?? "");
  expect(sampledTitles.some((title) => title.includes("100.0% win rate"))).toBe(true);
  expect(sampledTitles.some((title) => title.includes("0.00% win rate"))).toBe(true);
  expect(screen.getByRole("table", { name: "Paper season scorecards" }).querySelectorAll(".season-identity")).toHaveLength(20);
});

test("keeps an all-season chart honest when no season has a closed outcome", async () => {
  const now = new Date().toISOString();
  const seasons = Array.from({ length: 11 }, (_, index) => ({
    season_id: `empty-season-${index + 1}`,
    season_number: index + 1,
    started_at: now,
    ended_at: index === 10 ? null : now,
    quote_currency: "SOL" as const,
    quote_decimals: 9,
    starting_minor: 1_000_000_000,
    ending_equity_minor: 1_000_000_000,
    last_known_ending_equity_minor: 1_000_000_000,
    peak_equity_minor: 1_000_000_000,
    realized_pnl_minor: 0,
    net_pnl_minor: 0,
    total_fees_minor: 0,
    closed_trades: 0,
    wins: 0,
    losses: 0,
    break_even: 0,
    ending_drawdown_fraction: 0,
    open_positions: 0,
    status: index === 10 ? "current" as const : "completed" as const,
    win_rate: null,
    net_return_fraction: 0,
    duration_seconds: 60,
  }));
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return { ok: true, json: async () => ({ sort: "profit", summary: { closed_trades: 0, wins: 0, losses: 0, total_realized_pnl_minor: 0, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null, total_fees_minor: 0 }, rows: [] }) };
    }
    if (input === "/api/v1/seasons") {
      return { ok: true, json: async () => ({ generated_at: now, seasons, summary: { season_count: 11, completed_seasons: 10, profitable_seasons: 0, losing_seasons: 0, average_win_rate: null, best_return_fraction: 0 } }) };
    }
    return { ok: true, json: async () => snapshot };
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Seasons" }));
  fireEvent.click(await screen.findByRole("button", { name: "All" }));
  expect(screen.getByRole("img", { name: "All 11 seasons. No season has a measured win rate yet." })).toBeInTheDocument();
  expect(screen.getByText("Waiting for closed paper trades")).toBeInTheDocument();
  expect(container.querySelector(".season-line-path")).toBeNull();
  expect(container.querySelectorAll(".season-line-point")).toHaveLength(0);
  expect(screen.queryByText("Complete season history")).not.toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Paper season scorecards" }).querySelectorAll(".season-identity")).toHaveLength(11);
});

test("keeps one transient Results failure quiet but surfaces a repeated failure", async () => {
  let leaderboardCalls = 0;
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      leaderboardCalls += 1;
      return Promise.reject(new Error("temporary results delay"));
    }
    return Promise.resolve({ ok: true, json: async () => snapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  await waitFor(() => expect(leaderboardCalls).toBe(1));
  expect(await screen.findByText("Saved results are taking longer. Retrying…")).toBeInTheDocument();
  expect(screen.queryByText("No paper results yet")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "System status: all good" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Most loss" }));
  await waitFor(() => expect(leaderboardCalls).toBe(2));
  expect(await screen.findByRole("button", { name: "System status: issue" })).toBeInTheDocument();
});

test("retains the last good Results table while a new sort retries", async () => {
  let leaderboardCalls = 0;
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      leaderboardCalls += 1;
      if (leaderboardCalls > 1) return Promise.reject(new Error("temporary sort delay"));
      return Promise.resolve({
        ok: true,
        json: async () => ({
          sort: "profit",
          summary: { closed_trades: 1, wins: 1, losses: 0, total_realized_pnl_minor: 1, audited_exits: 0, winner_reversals: 0, average_peak_capture_fraction: null },
          rows: [{
            mint: "mint-kept", symbol: "KEPT", status: "closed", pnl_minor: 1, last_known_pnl_minor: 1,
            return_fraction: 0.01, fees_minor: 0, opened_at: new Date().toISOString(), closed_at: new Date().toISOString(),
            hold_seconds: 10, exit_reason: "take_profit", exit_assessment: null, peak_return_fraction: 0.01,
            peak_capture_fraction: null, entry_risk_mode: "balanced", entry_decision_id: null,
            mark_is_stale: false, market_status: "closed", mark_is_executable: true,
            quote_currency: "SOL", quote_decimals: 9,
          }],
        }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => snapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Results" }));
  expect(await screen.findByText("KEPT")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Most loss" }));
  await waitFor(() => expect(leaderboardCalls).toBe(2));
  expect(await screen.findByText("Showing the last saved order while Results retries…")).toBeInTheDocument();
  expect(screen.getByText("KEPT")).toBeInTheDocument();
  expect(screen.queryByText("No paper results yet")).not.toBeInTheDocument();
});

test("makes missing token identity useful without overstating confidence", async () => {
  const unknownMint = "9abcDEFghijkLMNopqrstUVWxyz1234567890WXYZ";
  const identityValue = (value: string, quality: number, missingReason: string | null) => ({
    value,
    unit: "label",
    as_of: new Date().toISOString(),
    sources: ["dexscreener"],
    freshness_seconds: 0,
    quality,
    missing_reason: missingReason,
  });
  const radarSnapshot: Snapshot = {
    ...snapshot,
    tokens: [
      {
        ...decision.feature_snapshot,
        mint: unknownMint,
        symbol: "?",
        name: "Unknown token",
        data_confidence: 1,
        values: {
          ...decision.feature_snapshot.values,
          identity_source: identityValue("unavailable", 0, "name_and_symbol_not_observed"),
        },
      },
      {
        ...decision.feature_snapshot,
        mint: "DexMint111111111111111111111111111111111111",
        symbol: "DEX",
        name: "DEX Name",
        values: {
          ...decision.feature_snapshot.values,
          identity_source: identityValue("dexscreener", 0.6, null),
        },
      },
    ],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => radarSnapshot }));
  render(<App />);

  expect(await screen.findByText("Name unavailable")).toBeInTheDocument();
  expect(screen.getByText(`${unknownMint.slice(0, 6)}…${unknownMint.slice(-4)}`)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: `Copy ${unknownMint} mint address` })).toBeInTheDocument();
  expect(screen.getByText("DEX display label")).toBeInTheDocument();
  expect(screen.getAllByText("Market data confidence")).toHaveLength(2);
  expect(screen.queryByText("?")).not.toBeInTheDocument();
});

test("manages provider plans and write-only keys from settings", async () => {
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      presets: {
        solana: [{ id: "public", label: "Public RPC", requests_per_minute: 120, monthly_limit: null, paid_mode: false }],
        jupiter: [{ id: "free_key", label: "Free API key", requests_per_minute: 60, monthly_limit: null, paid_mode: false }],
      },
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
    if (path.includes("/provider-settings") && init?.method === "PUT") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          provider_settings: managedSnapshot.provider_settings,
          source_restarted: false,
          paper_engine_stopped: false,
        }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => managedSnapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  expect(screen.getByText(/Keyless secondary USD and liquidity context/)).toBeInTheDocument();
  expect(screen.getAllByLabelText("Requests per minute")).toHaveLength(3);
  fireEvent.change(screen.getByLabelText("API key"), {
    target: { value: "write-only-test-key" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save providers" }));

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(([path, init]) => {
        if (!String(path).includes("/provider-settings") || init?.method !== "PUT") return false;
        const body = JSON.parse(String(init.body)) as { secrets: Record<string, unknown> };
        return body.secrets.jupiter_api_key === "write-only-test-key";
      }),
    ).toBe(true);
  });
});

test("makes replacing and clearing a write-only provider key mutually exclusive", async () => {
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      providers: {
        ...snapshot.provider_settings.providers,
        jupiter: { ...snapshot.provider_settings.providers.jupiter, api_key_configured: true },
      },
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/api/v1/provider-settings" && init?.method === "PUT") {
      return Promise.resolve({ ok: true, json: async () => ({ provider_settings: managedSnapshot.provider_settings, source_restarted: false, paper_engine_stopped: false }) });
    }
    return Promise.resolve({ ok: true, json: async () => managedSnapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  const removeKey = screen.getByLabelText("Remove saved Jupiter key");
  fireEvent.click(removeKey);
  expect(removeKey).toBeChecked();
  fireEvent.change(screen.getByLabelText("API key"), { target: { value: "replacement-key" } });
  expect(removeKey).not.toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Save providers" }));

  await waitFor(() => {
    const call = fetchMock.mock.calls.find(([path, init]) => path === "/api/v1/provider-settings" && init?.method === "PUT");
    expect(call).toBeDefined();
    const body = JSON.parse(String(call?.[1]?.body)) as { secrets: { jupiter_api_key?: string; clear: string[] } };
    expect(body.secrets.jupiter_api_key).toBe("replacement-key");
    expect(body.secrets.clear).not.toContain("jupiter_api_key");
  });
});

test("builds both Solana endpoints from one guided provider key", async () => {
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      presets: {
        solana: [
          { id: "public", label: "Public RPC", requests_per_minute: 120, monthly_limit: null, paid_mode: false },
          { id: "helius_free", label: "Helius Free (500k HTTP reserve)", requests_per_minute: 600, monthly_limit: 500_000, paid_mode: false },
        ],
        jupiter: [],
      },
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
    if (path.includes("/provider-settings") && init?.method === "PUT") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          provider_settings: managedSnapshot.provider_settings,
          source_restarted: true,
          paper_engine_stopped: true,
        }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => managedSnapshot });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  expect(screen.queryByLabelText("HTTP RPC URL")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("RPC service"), { target: { value: "helius_free" } });
  fireEvent.change(screen.getByLabelText("Helius API key"), {
    target: { value: "guided-key / test" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save providers" }));

  await waitFor(() => {
    const request = fetchMock.mock.calls.find(([path, init]) => String(path).includes("/provider-settings") && init?.method === "PUT");
    expect(request).toBeDefined();
    const body = JSON.parse(String(request?.[1]?.body)) as { secrets: Record<string, unknown> };
    expect(body.secrets.solana_http).toBe("https://mainnet.helius-rpc.com/?api-key=guided-key%20%2F%20test");
    expect(body.secrets.solana_ws).toBe("wss://mainnet.helius-rpc.com/?api-key=guided-key%20%2F%20test");
    expect(body.secrets.solana_api_key).toBeUndefined();
  });
});

test("uses keyed Helius HTTP while restoring the default stream in economy mode", async () => {
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      presets: {
        solana: [
          { id: "public", label: "Public RPC", requests_per_minute: 120, monthly_limit: null, paid_mode: false },
          { id: "helius_economy", label: "Helius Economy (keyed HTTP + public stream)", requests_per_minute: 600, monthly_limit: 500_000, paid_mode: false },
        ],
        jupiter: [],
      },
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => Promise.resolve({
    ok: true,
    json: async () => path.includes("/provider-settings") && init?.method === "PUT"
      ? { provider_settings: managedSnapshot.provider_settings, source_restarted: true, paper_engine_stopped: true }
      : managedSnapshot,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  fireEvent.change(screen.getByLabelText("RPC service"), { target: { value: "helius_economy" } });
  expect(screen.getByText(/keyed Helius for paced safety lookups/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Helius API key"), { target: { value: "economy-key" } });
  fireEvent.click(screen.getByRole("button", { name: "Save providers" }));

  await waitFor(() => {
    const request = fetchMock.mock.calls.find(([path, init]) => String(path).includes("/provider-settings") && init?.method === "PUT");
    expect(request).toBeDefined();
    const body = JSON.parse(String(request?.[1]?.body)) as { secrets: { solana_http?: string; solana_ws?: string; clear: string[] } };
    expect(body.secrets.solana_http).toBe("https://mainnet.helius-rpc.com/?api-key=economy-key");
    expect(body.secrets.solana_ws).toBeUndefined();
    expect(body.secrets.clear).toContain("solana_ws");
    expect(body.secrets.clear).not.toContain("solana_http");
  });
});

test("can move a saved full Helius route to economy without asking for the key again", async () => {
  const heliusPolicy = { label: "Helius Free (500k HTTP reserve)", requests_per_minute: 600, monthly_limit: 500_000, reserve_fraction: 0.1, paid_mode: false };
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      providers: {
        ...snapshot.provider_settings.providers,
        solana: {
          ...snapshot.provider_settings.providers.solana,
          endpoint: "https://mainnet.helius-rpc.com",
          stream_endpoint: "wss://mainnet.helius-rpc.com",
          custom_endpoint: true,
          policy: heliusPolicy,
        },
      },
      presets: {
        solana: [
          { id: "helius_free", label: heliusPolicy.label, requests_per_minute: 600, monthly_limit: 500_000, paid_mode: false },
          { id: "helius_economy", label: "Helius Economy (keyed HTTP + public stream)", requests_per_minute: 600, monthly_limit: 500_000, paid_mode: false },
        ],
        jupiter: [],
      },
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => Promise.resolve({
    ok: true,
    json: async () => path.includes("/provider-settings") && init?.method === "PUT"
      ? { provider_settings: managedSnapshot.provider_settings, source_restarted: true, paper_engine_stopped: true }
      : managedSnapshot,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  fireEvent.change(screen.getByLabelText("RPC service"), { target: { value: "helius_economy" } });
  expect(screen.getByLabelText("Helius API key")).not.toBeRequired();
  fireEvent.click(screen.getByRole("button", { name: "Save providers" }));

  await waitFor(() => {
    const request = fetchMock.mock.calls.find(([path, init]) => String(path).includes("/provider-settings") && init?.method === "PUT");
    const body = JSON.parse(String(request?.[1]?.body)) as { secrets: { solana_http?: string; solana_ws?: string; clear: string[] } };
    expect(body.secrets.solana_http).toBeUndefined();
    expect(body.secrets.solana_ws).toBeUndefined();
    expect(body.secrets.clear).toContain("solana_ws");
    expect(body.secrets.clear).not.toContain("solana_http");
  });
});

test("keeps explicit Solana endpoints behind the custom RPC option", async () => {
  const managedSnapshot: Snapshot = {
    ...snapshot,
    provider_settings: {
      ...snapshot.provider_settings,
      presets: {
        solana: [{ id: "public", label: "Public RPC", requests_per_minute: 120, monthly_limit: null, paid_mode: false }],
        jupiter: [],
      },
    },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => managedSnapshot }));
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Show data providers" }));
  fireEvent.click(screen.getByRole("button", { name: "Manage" }));
  fireEvent.change(screen.getByLabelText("RPC service"), { target: { value: "custom" } });

  expect(screen.getByLabelText("HTTP RPC URL")).toBeInTheDocument();
  expect(screen.getByLabelText("WebSocket URL")).toBeInTheDocument();
  expect(screen.getByText("Restore environment/default RPC endpoints")).toBeInTheDocument();
});

test("fresh installs require a bankroll and do not start trading automatically", async () => {
  const fresh = {
    ...snapshot,
    running: false,
    portfolio: {
      ...snapshot.portfolio,
      initialized: false,
      cash_lamports: 0,
      available_cash_lamports: 0,
      starting_lamports: 0,
      equity_lamports: 0,
    },
  };
  const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve({
    ok: true,
    json: async () => path.includes("/portfolio/setup")
      ? { initialized: true, quote_currency: "USDC", starting_minor: 1_000_000_000, running: false }
      : fresh,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Choose the bankroll. Start when ready.")).toBeInTheDocument();
  expect(screen.queryByText("Paper engine running")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Use USDC for paper bankroll" }));
  fireEvent.change(screen.getByLabelText("Starting amount"), { target: { value: "1250" } });
  fireEvent.click(screen.getByRole("button", { name: "Create paper bankroll" }));

  await act(async () => undefined);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/portfolio/setup", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ quote_currency: "USDC", starting_amount: "1250", risk_mode: "balanced", drawdown_policy: { kind: "default", custom_threshold_bps: null } }),
  }));
  expect(fetchMock.mock.calls.some(([path]) => String(path).includes("/engine/start"))).toBe(false);
});

test("keeps setup controls in a creating state while the server transaction is pending", async () => {
  const fresh = {
    ...snapshot,
    running: false,
    portfolio: {
      ...snapshot.portfolio,
      initialized: false,
      cash_lamports: 0,
      available_cash_lamports: 0,
      starting_lamports: 0,
      equity_lamports: 0,
    },
  } satisfies Snapshot;
  let finishSetup: (() => void) | null = null;
  const pendingSetup = new Promise<{ ok: boolean; json: () => Promise<{ initialized: true }> }>(
    (resolve) => {
      finishSetup = () => resolve({ ok: true, json: async () => ({ initialized: true }) });
    },
  );
  vi.stubGlobal("fetch", vi.fn().mockImplementation((path: string) => (
    path.includes("/portfolio/setup")
      ? pendingSetup
      : Promise.resolve({ ok: true, json: async () => fresh })
  )));
  render(<App />);

  expect(await screen.findByText("Choose the bankroll. Start when ready.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create paper bankroll" }));

  const creating = await screen.findByRole("button", { name: "Creating…" });
  expect(creating).toBeDisabled();
  expect(screen.getByLabelText("Starting amount")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Use USDC for paper bankroll" })).toBeDisabled();
  expect(screen.queryByText(/took too long/i)).not.toBeInTheDocument();

  await act(async () => {
    finishSetup?.();
    await pendingSetup;
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Create paper bankroll" })).toBeEnabled());
});

test("reconciles authoritative bankroll state after a lost setup response", async () => {
  const fresh = {
    ...snapshot,
    running: false,
    portfolio: {
      ...snapshot.portfolio,
      initialized: false,
      cash_lamports: 0,
      available_cash_lamports: 0,
      starting_lamports: 0,
      equity_lamports: 0,
    },
  } satisfies Snapshot;
  const initialized = {
    ...snapshot,
    running: false,
    portfolio: { ...snapshot.portfolio, initialized: true },
  } satisfies Snapshot;
  let setupAttempted = false;
  vi.stubGlobal("fetch", vi.fn().mockImplementation((path: string) => {
    if (path.includes("/portfolio/setup")) {
      setupAttempted = true;
      return Promise.reject(new TypeError("response connection closed"));
    }
    return Promise.resolve({
      ok: true,
      json: async () => setupAttempted ? initialized : fresh,
    });
  }));
  render(<App />);

  expect(await screen.findByText("Choose the bankroll. Start when ready.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create paper bankroll" }));

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  expect(screen.queryByText(/response connection closed/i)).not.toBeInTheDocument();
});

test("chooses a deliberate first-season personality and typed drawdown policy", async () => {
  const fresh = {
    ...snapshot,
    running: false,
    portfolio: { ...snapshot.portfolio, initialized: false, cash_lamports: 0, available_cash_lamports: 0, starting_lamports: 0, equity_lamports: 0 },
  } satisfies Snapshot;
  const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve({
    ok: true,
    json: async () => path.includes("/portfolio/setup") ? { initialized: true } : fresh,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(await screen.findByRole("radio", { name: /Aggressive/ }));
  fireEvent.click(screen.getByText("Advanced: portfolio drawdown halt"));
  fireEvent.click(screen.getByRole("radio", { name: "Off" }));
  fireEvent.click(screen.getByRole("button", { name: "Create paper bankroll" }));

  await act(async () => undefined);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/portfolio/setup", expect.objectContaining({
    body: JSON.stringify({ quote_currency: "SOL", starting_amount: "10", risk_mode: "aggressive", drawdown_policy: { kind: "disabled", custom_threshold_bps: null } }),
  }));
});

test("confirms a locked drawdown-only profile change before starting a new season", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit next season" }));
  const editor = within(screen.getByRole("dialog", { name: "Edit the next paper season" }));
  fireEvent.click(editor.getByRole("radio", { name: /OffStructural safety/ }));
  expect(editor.getByRole("radio", { name: /Finish safely/ })).toBeChecked();
  expect(screen.getByRole("dialog").parentElement).toHaveClass("profile-confirm-backdrop");
  fireEvent.click(editor.getByRole("button", { name: "Apply after safe finish" }));

  await act(async () => undefined);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/risk", expect.objectContaining({
    body: JSON.stringify({ mode: "balanced", drawdown_policy: { kind: "disabled", custom_threshold_bps: null }, transition_strategy: "finish_safely", quote_currency: "SOL", starting_amount: "10" }),
  }));
});

test("keeps the active risk profile concise and moves every change into one editor", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  const profileCard = screen.getByText("Current season profile").closest("article");
  expect(profileCard).not.toBeNull();
  const card = within(profileCard!);
  expect(card.getByRole("heading", { name: "Balanced" })).toBeInTheDocument();
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("10 SOL");
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("4 positions");
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("12.0%");
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("15% · Default");
  expect(card.queryByRole("radiogroup", { name: "Season risk personality" })).not.toBeInTheDocument();
  expect(screen.queryByText("Advanced drawdown setting")).not.toBeInTheDocument();

  fireEvent.click(card.getByRole("button", { name: "Edit next season" }));
  const editor = within(screen.getByRole("dialog", { name: "Edit the next paper season" }));
  expect(editor.getByRole("group", { name: "Risk personality" })).toBeInTheDocument();
  expect(editor.getByRole("group", { name: "Portfolio drawdown halt" })).toBeInTheDocument();
});

test("keeps a legacy profile honest when exact limits are unavailable", async () => {
  const legacySnapshot = {
    ...snapshot,
    season_profile: null,
    season_profile_provenance: "legacy_unknown" as const,
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => legacySnapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  const profileCard = screen.getByText("Current season profile").closest("article");
  const card = within(profileCard!);
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("Unavailable");
  expect(card.getByLabelText("Current season settings")).toHaveTextContent("Legacy / unknown");
  expect(card.getByText(/Locked for this season/)).toBeInTheDocument();
  fireEvent.click(card.getByRole("button", { name: "Edit next season" }));
  expect(screen.getByRole("group", { name: "How should this season finish?" })).toBeInTheDocument();
});

test("blocks profile edits while an existing profile transition owns the boundary", async () => {
  const transitioningSnapshot = {
    ...snapshot,
    season_operation: {
      operation_id: "profile-transition-one",
      kind: "profile_transition" as const,
      state: "running" as const,
      stage: "waiting_for_positions",
      detail: "Finishing the current season safely.",
      started_at: new Date(Date.now() - 5_000).toISOString(),
      updated_at: new Date().toISOString(),
      completed_at: null,
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => transitioningSnapshot }));
  render(<App />);

  expect(await screen.findByRole("button", { name: "Edit next season" })).toBeDisabled();
  expect(screen.queryByRole("dialog", { name: "Edit the next paper season" })).not.toBeInTheDocument();
});

test("edits currency amount personality and drawdown as one exact next-season plan", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit next season" }));
  const editor = within(screen.getByRole("dialog", { name: "Edit the next paper season" }));
  fireEvent.click(editor.getByRole("radio", { name: /USDCDollar-denominated/ }));
  fireEvent.change(editor.getByLabelText("Next season starting amount"), {
    target: { value: "200" },
  });
  fireEvent.click(editor.getByRole("radio", { name: /Aggressive6 positions/ }));
  fireEvent.click(editor.getByRole("radio", { name: /CustomA separate season/ }));
  fireEvent.change(editor.getByLabelText("Next season custom drawdown percentage"), {
    target: { value: "18.5" },
  });
  fireEvent.click(editor.getByRole("button", { name: "Apply after safe finish" }));

  await act(async () => undefined);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/risk", expect.objectContaining({
    body: JSON.stringify({ mode: "aggressive", drawdown_policy: { kind: "custom", custom_threshold_bps: 1850 }, transition_strategy: "finish_safely", quote_currency: "USDC", starting_amount: "200" }),
  }));
});

test("can end a locked season now without implying fabricated exits", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit next season" }));
  const editor = within(screen.getByRole("dialog", { name: "Edit the next paper season" }));
  fireEvent.click(editor.getByRole("radio", { name: /OffStructural safety/ }));
  fireEvent.click(editor.getByRole("radio", { name: /End season now/ }));
  expect(editor.getByText(/never as a made-up fill, win or loss/i)).toBeInTheDocument();
  expect(editor.getByText(/excluded from strategy comparisons/i)).toBeInTheDocument();
  fireEvent.click(editor.getByRole("button", { name: "End season & apply" }));

  await act(async () => undefined);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/risk", expect.objectContaining({
    body: JSON.stringify({ mode: "balanced", drawdown_policy: { kind: "disabled", custom_threshold_bps: null }, transition_strategy: "end_now", quote_currency: "SOL", starting_amount: "10" }),
  }));
});

test("cancels the centered profile dialog with Escape", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit next season" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("canonicalizes a custom drawdown equal to the personality default", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit next season" }));
  const editor = within(screen.getByRole("dialog", { name: "Edit the next paper season" }));
  fireEvent.click(editor.getByRole("radio", { name: /CustomA separate season/ }));
  fireEvent.change(editor.getByLabelText("Next season custom drawdown percentage"), {
    target: { value: "15" },
  });

  expect(editor.getByRole("button", { name: "No changes" })).toBeDisabled();
  expect(fetchMock.mock.calls.some(([path]) => path === "/api/v1/risk")).toBe(false);
});

test("stops and resumes the paper engine through explicit controls", async () => {
  const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve({
    ok: true,
    json: async () => path.includes("/engine/stop") ? { running: false, cancelled_pending_orders: 0 } : snapshot,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Paper engine running")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await act(async () => undefined);
  expect(fetchMock.mock.calls.some(([path]) => String(path).includes("/engine/stop"))).toBe(true);
});

test("shows learning progress without mixing demo outcomes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByText("Three players. One safely bounded team.")).toBeInTheDocument();
  expect(screen.getByText(/Switch to Solana mainnet when you want to collect/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.getByText("Demo experience stays separate")).toBeInTheDocument();
  expect(screen.getByText("0 / 80")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use qualified Challenger" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText(/learned experience remain/)).toBeInTheDocument();
});

test("separates the training minimum from progress toward the next challenger", async () => {
  const challengerSnapshot: Snapshot = {
    ...snapshot,
    demo_mode: false,
    learning: {
      ...snapshot.learning,
      state: "challenger_testing",
      collecting_from_current_source: true,
      observation_count: 2_321,
      usable_outcome_count: 976,
      pending_count: 29,
      unavailable_outcome_count: 1_047,
      outcomes_until_next_training: 1,
      latest_model: {
        version: "learner-test",
        created_at: new Date().toISOString(),
        outcomes_seen: 975,
        risk_mode: "balanced",
        configuration_fingerprint: "balanced-test",
        sample_count: 976,
        resolved_count: 976,
        outcome_availability_fraction: 0.61,
        training_count: 650,
        validation_count: 300,
        embargoed_count: 26,
        validation_rmse: 0.1,
        naive_rmse: 0.11,
        learner_correlation: 0.2,
        baseline_correlation: 0.1,
        learner_top_mean_return: -0.01,
        baseline_top_mean_return: 0,
        overall_mean_return: -0.02,
        validation_in_distribution_fraction: 0.96,
        policy_validation_count: 20,
        policy_observed_count: 28,
        policy_outcome_availability_fraction: 0.71,
        policy_supported_count: 15,
        policy_veto_count: 5,
        policy_winner_veto_count: 1,
        policy_winner_veto_fraction: 0.2,
        policy_mean_uplift: -0.01,
        policy_uplift_lower_bound: -0.02,
        qualification_evidence_schema_version: "learning-evidence-v2",
        qualified: false,
      },
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => challengerSnapshot }),
  );
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "Challenger" }));
  expect(screen.queryByText("Demo experience stays separate")).not.toBeInTheDocument();
  expect(screen.getByText("976 usable")).toBeInTheDocument();
  expect(screen.getByText("Minimum 80 met · 1 more usable outcome until the next challenger")).toBeInTheDocument();
  expect(screen.queryByText("976 / 80")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Progress toward next challenger" })).toHaveAttribute("aria-valuenow", "9");
  expect(screen.getByRole("progressbar", { name: "Progress toward next challenger" })).toHaveAttribute("aria-valuemax", "10");
});

test("shows the risk rule that caused a sell fill", async () => {
  const replaySnapshot: Snapshot = {
    ...snapshot,
    fills: [{
      fill_id: "sell-fill",
      order_id: "sell-order",
      mint: "mint-aaa",
      symbol: "AAA",
      side: "sell",
      filled_at: "2026-08-30T10:18:35Z",
      token_units: 1_000,
      gross_sol_lamports: 20_000_000,
      protocol_fee_lamports: 250_000,
      network_fee_lamports: 30_000,
      net_sol_lamports: 19_720_000,
      price_impact_fraction: 0.002,
      latency_ms: 1_100,
      venue: "pump_curve",
      assumptions: ["scheduled_reason:stop_loss"],
      account_currency: "SOL",
      account_decimals: 9,
      account_gross_minor: 20_000_000,
      account_protocol_fee_minor: 250_000,
      account_network_fee_minor: 30_000,
      account_net_minor: 19_720_000,
      sol_usd_price: null,
      exit_assessment: null,
      position_opened_at: new Date().toISOString(),
      entry_risk_mode: "balanced",
      peak_account_minor: 22_000_000,
      realized_return_fraction: -0.1,
      peak_return_fraction: 0.05,
    }],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => replaySnapshot }));
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Replay" }));
  expect(screen.getByRole("table", { name: "Current-season paper fill receipts" })).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Net flow" })).toBeInTheDocument();
  expect(screen.getByText("pump_curve · Stop loss")).toBeInTheDocument();
  expect(screen.getByText("+0.01972 SOL")).toBeInTheDocument();
  expect(screen.getByText("0.00025 SOL protocol · 0.00003 SOL network")).toBeInTheDocument();
  expect(screen.getAllByText("0.20%").length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByText("1.1s").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText("1,100ms exact")).toBeInTheDocument();
  expect(screen.getByText(/2026/)).toBeInTheDocument();
  expect(screen.getByText("1 current-season receipt · newest first")).toBeInTheDocument();
  const receiptSummary = screen.getByText("Visible receipts").closest(".stat-card");
  expect(receiptSummary).toHaveTextContent("1");
  expect(receiptSummary).toHaveTextContent("0 buys · 1 sell");
  const row = screen.getByText("AAA").closest("[role='row']");
  expect(row?.querySelectorAll("[role='cell']")).toHaveLength(7);
  expect(Array.from(row?.querySelectorAll("[data-label]") ?? []).map((cell) => cell.getAttribute("data-label"))).toEqual([
    "Time", "Token", "Side", "Net SOL", "Fees", "Impact", "Latency",
  ]);
});

test("keeps an empty Replay honest without inventing execution statistics", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Replay" }));
  expect(screen.getByText("No fills yet")).toBeInTheDocument();
  expect(screen.getByText("0 current-season receipts · newest first")).toBeInTheDocument();
  expect(screen.getByText("Visible fees").closest(".stat-card")).toHaveTextContent("—");
  expect(screen.getByText("Average impact").closest(".stat-card")).toHaveTextContent("—");
  expect(screen.getByText("Median latency").closest(".stat-card")).toHaveTextContent("—");
});

test("keeps USDC buy receipts signed correctly at the latest-30 boundary", async () => {
  const usdcBuy = {
    fill_id: "usdc-buy",
    order_id: "usdc-order",
    mint: "mint-with-a-very-long-symbol",
    symbol: "A-VERY-LONG-TOKEN-SYMBOL-THAT-MUST-WRAP",
    side: "buy",
    filled_at: "2026-08-30T10:18:35Z",
    token_units: 1_000,
    gross_sol_lamports: 1_200_000,
    protocol_fee_lamports: 40_000,
    network_fee_lamports: 10_000,
    net_sol_lamports: 1_250_000,
    price_impact_fraction: 0,
    latency_ms: 18_882,
    venue: "a-very-long-venue-name-that-must-wrap-without-overflow",
    assumptions: [],
    account_currency: "USDC",
    account_decimals: 6,
    account_gross_minor: 1_200_000,
    account_protocol_fee_minor: 40_000,
    account_network_fee_minor: 10_000,
    account_net_minor: 1_250_000,
    sol_usd_price: 150,
    exit_assessment: null,
    position_opened_at: null,
    entry_risk_mode: "balanced",
    peak_account_minor: 0,
    realized_return_fraction: null,
    peak_return_fraction: null,
  } satisfies Fill;
  const replaySnapshot: Snapshot = {
    ...snapshot,
    portfolio: { ...snapshot.portfolio, quote_currency: "USDC", quote_decimals: 6 },
    fills: Array.from({ length: 30 }, (_, index) => ({
      ...usdcBuy,
      fill_id: `usdc-buy-${index}`,
      order_id: `usdc-order-${index}`,
    })),
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => replaySnapshot }));
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Replay" }));
  expect(screen.getByText("Latest 30 current-season receipts · newest first")).toBeInTheDocument();
  expect(screen.getByText(/newest 30 receipts/)).toBeInTheDocument();
  expect(screen.getByText("Visible receipts").closest(".stat-card")).toHaveTextContent("30 buys · 0 sells · latest 30");
  expect(screen.getAllByText("−1.25 USDC")).toHaveLength(30);
  expect(screen.getAllByText("0.04 USDC protocol · 0.01 USDC network")).toHaveLength(30);
  expect(screen.getAllByText("19s")).toHaveLength(31);
  expect(screen.getAllByText("18,882ms exact")).toHaveLength(30);
  expect(screen.getAllByLabelText("Latency 19s, 18,882 milliseconds exact")).toHaveLength(30);
  expect(screen.getAllByText("A-VERY-LONG-TOKEN-SYMBOL-THAT-MUST-WRAP")).toHaveLength(30);
});

test("shows that stopped positions are preserved and offers resume", async () => {
  const stopped = {
    ...snapshot,
    running: false,
    portfolio: {
      ...snapshot.portfolio,
      cash_lamports: 8_000_000_000,
      available_cash_lamports: 8_000_000_000,
      invested_value_lamports: 1_500_000_000,
      equity_lamports: 9_500_000_000,
      unrealized_pnl_lamports: -500_000_000,
      positions: [{
        position_id: "position-aaa",
        mint: "mint-aaa",
        symbol: "AAA",
        token_units: 1_000,
        entry_cost_lamports: 2_000_000_000,
        book_value_lamports: 1_990_000_000,
        opened_at: new Date().toISOString(),
        last_mark_lamports: 1_500_000_000,
        unrealized_pnl_lamports: -500_000_000,
        last_marked_at: new Date().toISOString(),
        mark_age_seconds: 0,
        mark_is_stale: false,
        mark_is_executable: true,
        mark_blockers: [],
        market_status: "active",
        risk_mode_at_entry: "balanced",
        peak_mark_lamports: 1_500_000_000,
        peak_marked_at: new Date().toISOString(),
        exit_assessment: {
          policy_version: "adaptive-exit-v1",
          evaluated_at: new Date().toISOString(),
          action: "hold",
          reason: "adaptive_extension",
          support_score: 0.78,
          pnl_fraction: -0.25,
          peak_return_fraction: 0.1,
          drawdown_from_peak_fraction: 0.3,
          age_seconds: 700,
          soft_hold_seconds: 600,
          hard_hold_seconds: 1800,
          evidence: ["5m buy ratio 72%"],
        },
      }],
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => stopped }));
  render(<App />);

  expect(await screen.findByText("Paper engine stopped")).toBeInTheDocument();
  expect(screen.getByText("Positions are preserved and still marked from fresh data.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
  expect(screen.getByText("AAA")).toBeInTheDocument();
  expect(screen.getByText(/Adaptive extension · 78% support/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy AAA mint address" })).toHaveAttribute("title", "mint-aaa");
  expect(screen.getByRole("link", { name: "Open AAA on GMGN" })).toHaveAttribute("href", "https://gmgn.ai/sol/token/mint-aaa");
  expect(screen.getByRole("link", { name: "Open AAA on GMGN" })).toHaveAttribute("target", "_blank");
});

test("keeps dormant holdings compact and reports that they do not use active slots", async () => {
  const dormant = {
    ...snapshot,
    portfolio: {
      ...snapshot.portfolio,
      positions: [{
        position_id: "position-dormant",
        mint: "mint-dormant",
        symbol: "DORMANTCOIN",
        token_units: 1_000,
        entry_cost_lamports: 25_000_000,
        book_value_lamports: 24_000_000,
        opened_at: new Date().toISOString(),
        last_mark_lamports: 20_000_000,
        unrealized_pnl_lamports: -5_000_000,
        last_marked_at: new Date(Date.now() - 3_600_000).toISOString(),
        mark_age_seconds: 3_600,
        mark_is_stale: true,
        mark_is_executable: false,
        mark_blockers: ["stale_market_data"],
        market_status: "dormant",
        risk_mode_at_entry: "balanced",
        peak_mark_lamports: 24_000_000,
        peak_marked_at: new Date().toISOString(),
        exit_assessment: null,
      }],
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => dormant }));
  render(<App />);

  const toggle = await screen.findByRole("button", { name: "Show Dormant positions" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByText("0 using active slots · 0 orders waiting")).toBeInTheDocument();
  expect(screen.queryByText("DORMANTCOIN")).not.toBeInTheDocument();

  fireEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Hide Dormant positions" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("DORMANTCOIN")).toBeInTheDocument();
});

test("keeps Arena labels honest and links its decision preview to the full journal", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  expect(await screen.findByText("this season")).toBeInTheDocument();
  expect(screen.queryByText("all time")).not.toBeInTheDocument();
  expect(screen.getByText("Radar is warming up")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "View all decisions" }));
  expect(screen.getByText("Best signals first. Noise tucked away.")).toBeInTheDocument();
});

test("makes the Arena market radar compact by default on mobile and user-expandable", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  const toggle = await screen.findByRole("button", { name: "Show Market radar" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(document.getElementById("market-radar-grid")).toHaveAttribute("hidden");
  expect(screen.getByText("Radar is warming up")).not.toBeVisible();

  fireEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Hide Market radar" })).toHaveAttribute("aria-expanded", "true");
  expect(document.getElementById("market-radar-grid")).not.toHaveAttribute("hidden");
  expect(screen.getByText("Radar is warming up")).toBeVisible();
});

test("remembers Arena collapse choices in this browser across remounts", async () => {
  const personalized = {
    ...snapshot,
    portfolio: { ...snapshot.portfolio, positions: [activePosition] },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => personalized }));
  const first = render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Hide Active positions" }));
  fireEvent.click(screen.getByRole("button", { name: "Hide Market radar" }));
  expect(document.getElementById("market-radar-grid")).toHaveClass("is-collapsed");
  expect(document.getElementById("market-radar-grid")).toHaveAttribute("aria-hidden", "true");
  fireEvent.click(screen.getByRole("button", { name: "Show Market radar" }));
  expect(screen.getByRole("button", { name: "Hide Market radar" })).toHaveAttribute("aria-expanded", "true");
  expect(document.getElementById("market-radar-grid")).not.toHaveClass("is-collapsed");
  fireEvent.click(screen.getByRole("button", { name: "Hide Market radar" }));
  await waitFor(() => expect(JSON.parse(window.localStorage.getItem(arenaLayoutKey) ?? "null")).toMatchObject({
    version: 1,
    marketRadarCollapsed: true,
    collapsedPositionGroups: expect.arrayContaining(["active", "dormant"]),
  }));
  first.unmount();

  render(<App />);
  expect(await screen.findByRole("button", { name: "Show Active positions" })).toHaveAttribute("aria-expanded", "false");
  await waitFor(() => expect(screen.getByRole("button", { name: "Show Market radar" })).toHaveAttribute("aria-expanded", "false"));
  expect(screen.queryByText("PERSONALIZED")).not.toBeInTheDocument();
});

test("lets a saved desktop-style Arena layout override the mobile default", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
  window.localStorage.setItem(arenaLayoutKey, JSON.stringify({
    version: 1,
    marketRadarCollapsed: false,
    collapsedPositionGroups: [],
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  expect(await screen.findByRole("button", { name: "Hide Market radar" })).toHaveAttribute("aria-expanded", "true");
});

test("ignores corrupt and unknown Arena layout values", async () => {
  window.localStorage.setItem(arenaLayoutKey, "{not-json");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  const corrupt = render(<App />);
  expect(await screen.findByRole("button", { name: "Hide Market radar" })).toHaveAttribute("aria-expanded", "true");
  corrupt.unmount();

  window.localStorage.setItem(arenaLayoutKey, JSON.stringify({
    version: 1,
    marketRadarCollapsed: "not-a-boolean",
    collapsedPositionGroups: ["unknown", 42],
  }));
  render(<App />);
  expect(await screen.findByRole("button", { name: "Hide Market radar" })).toHaveAttribute("aria-expanded", "true");
});

test("falls back safely when Arena layout storage is unavailable", async () => {
  const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (key: string) {
    if (key === arenaLayoutKey) throw new DOMException("Storage unavailable", "SecurityError");
    return null;
  });
  const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (key: string) {
    if (key === arenaLayoutKey) throw new DOMException("Storage unavailable", "SecurityError");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  const toggle = await screen.findByRole("button", { name: "Hide Market radar" });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Show Market radar" })).toHaveAttribute("aria-expanded", "false");
  expect(getItem).toHaveBeenCalledWith(arenaLayoutKey);
  expect(setItem).toHaveBeenCalledWith(arenaLayoutKey, expect.any(String));
});

test("synchronizes Arena preferences changed in another browser tab", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);
  expect(await screen.findByRole("button", { name: "Hide Market radar" })).toBeInTheDocument();

  window.localStorage.setItem(arenaLayoutKey, JSON.stringify({
    version: 1,
    marketRadarCollapsed: true,
    collapsedPositionGroups: ["dormant"],
  }));
  fireEvent(window, new StorageEvent("storage", { key: arenaLayoutKey }));

  await waitFor(() => expect(screen.getByRole("button", { name: "Show Market radar" })).toHaveAttribute("aria-expanded", "false"));
});

test("explains that a stopped engine still lets the empty market radar observe", async () => {
  const stopped = { ...snapshot, running: false } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => stopped }));
  render(<App />);

  expect(await screen.findByText("Market observations continue while the paper engine is stopped; recent tokens will appear when enough evidence arrives.")).toBeInTheDocument();
});

test("explains the two Arena equity chart spacing modes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));
  render(<App />);

  const journey = await screen.findByRole("button", { name: "Journey" });
  const elapsed = screen.getByRole("button", { name: "Elapsed time" });
  expect(journey).toHaveAttribute("title", expect.stringContaining("collapses repetitive unchanged checkpoints"));
  expect(elapsed).toHaveAttribute("title", expect.stringContaining("real waiting time"));
  expect(screen.getByText(/unchanged waits collapsed/)).toBeInTheDocument();

  fireEvent.click(elapsed);
  expect(screen.getByText("True elapsed-time spacing · unchanged waits preserved")).toBeInTheDocument();
});

test("keeps connection failures in the compact status panel", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  render(<App />);

  const trigger = await screen.findByRole("button", { name: "System status: issue" });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();

  fireEvent.click(trigger);
  const statusDialog = screen.getByRole("dialog", { name: "System status details" });
  expect(statusDialog).toHaveAttribute("aria-modal", "true");
  expect(document.body).toContainElement(statusDialog);
  expect(screen.getByText("App server unavailable")).toBeInTheDocument();
  expect(
    screen.getByText(
      "The app server is temporarily unreachable. Signal Arcade will keep retrying quietly.",
    ),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "History · 1" }));
  expect(screen.getByText("Current", { selector: "span" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close system status" }));
  await waitFor(() => expect(trigger).toHaveFocus());
});

test("keeps the last screen and distinguishes a delayed dashboard from a healthy backend", async () => {
  const fetchMock = vi.fn().mockImplementation((path: string) => {
    if (path.includes("/api/v1/health")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ok: true,
          running: true,
          service_running: true,
          database_ok: true,
          degraded: false,
          degraded_reasons: [],
          paper_only: true,
          version: "1.4.4",
        }),
      });
    }
    return Promise.reject(new Error("snapshot timed out"));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  const trigger = await screen.findByRole("button", { name: "System status: issue" });
  fireEvent.click(trigger);
  expect(screen.getByText("Dashboard refresh delayed")).toBeInTheDocument();
  expect(
    screen.getByText(
      "The trading engine and paper ledger are responding. The last complete screen remains visible while the dashboard retries.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("App server unavailable")).not.toBeInTheDocument();
});

test("opens explanation feedback immediately while local AI is working", async () => {
  let finishExplanation!: (value: unknown) => void;
  const pendingExplanation = new Promise((resolve) => {
    finishExplanation = resolve;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string) => {
      if (path.includes("/explain")) return pendingExplanation;
      return Promise.resolve({
        ok: true,
        json: async () => ({ ...snapshot, decisions: [decision] }),
      });
    }),
  );
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Decisions" }));
  fireEvent.click(screen.getByRole("button", { name: "Explain AAA decision" }));

  expect(screen.getByRole("dialog", { name: "Why AAA" })).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("Preparing the explanation…")).toBeInTheDocument();

  await act(async () => {
    finishExplanation({
      ok: true,
      json: async () => ({ explanation: "AAA is being watched while evidence develops.", source: "deterministic" }),
    });
  });
  expect(await screen.findByText("AAA is being watched while evidence develops.")).toBeInTheDocument();
  expect(screen.getByText("Paper sizing receipt")).toBeInTheDocument();
  expect(screen.getByText("Baseline market integrity")).toBeInTheDocument();
  expect(screen.getByText("1.8%")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "AAA mint address" })).toHaveValue("mint-aaa");
  expect(screen.getAllByRole("link", { name: "Open AAA on GMGN" }).some((link) => link.getAttribute("href") === "https://gmgn.ai/sol/token/mint-aaa")).toBe(true);
});

test("closing a slow explanation cancels it and prevents a late drawer", async () => {
  let explanationSignal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes("/explain")) {
        explanationSignal = init?.signal ?? undefined;
        return new Promise(() => undefined);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ ...snapshot, decisions: [decision] }),
      });
    }),
  );
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Decisions" }));
  fireEvent.click(screen.getByRole("button", { name: "Explain AAA decision" }));
  expect(screen.getByRole("dialog", { name: "Why AAA" })).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(explanationSignal?.aborted).toBe(true);
  expect(screen.queryByRole("dialog", { name: "Why AAA" })).not.toBeInTheDocument();
});

test("shows a forward-only AI coach experiment without implying trading influence", async () => {
  const coached = {
    ...snapshot,
    ai_lab: { ...snapshot.ai_lab, mode: "shadow" as const },
    coach: {
      ...snapshot.coach,
      research_enabled: true,
      state: "testing" as const,
      outcomes_seen: 240,
      outcomes_until_review: 0,
      recent_hypotheses: [{
        hypothesis_id: "coach-hypothesis-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        cutoff_at: new Date().toISOString(),
        kind: "entry_veto" as const,
        skill: "entry" as const,
        state: "testing" as const,
        title: "Avoid weak one-minute momentum",
        rationale: "A bounded Shadow test of an observed weakness.",
        risk_mode: "balanced" as const,
        model_name: "qwen3.5:4b",
        feature_name: "momentum_1m",
        operator: "<=" as const,
        threshold: -0.05,
        hold_seconds: null,
        discovery_observed_count: 120,
        discovery_usable_count: 100,
        discovery_availability_fraction: 0.83,
        discovery_mean_uplift: 0.03,
        discovery_uplift_lower_bound: 0.012,
        forward_observed_count: 31,
        forward_usable_count: 24,
        forward_availability_fraction: 0.77,
        forward_season_count: 2,
        forward_mean_uplift: 0.018,
        forward_uplift_lower_bound: -0.004,
        forward_uplift_upper_bound: 0.04,
        minimum_forward_samples: 60,
        minimum_availability_fraction: 0.7,
        last_evaluated_at: new Date().toISOString(),
        contribution_state: "research_only" as const,
        influence_applied: false as const,
        context_active: true,
      }],
      research_lanes: [
        { skill: "entry" as const, label: "Entry", state: "testing" as const, current_title: "Avoid weak one-minute momentum", best_title: null, studies: 1, supported_studies: 0 },
        { skill: "manipulation" as const, label: "Manipulation", state: "observing" as const, current_title: null, best_title: null, studies: 0, supported_studies: 0 },
        { skill: "sizing" as const, label: "Sizing", state: "observing" as const, current_title: null, best_title: null, studies: 0, supported_studies: 0 },
        { skill: "exit" as const, label: "Exit", state: "observing" as const, current_title: null, best_title: null, studies: 0, supported_studies: 0 },
      ],
    },
  } satisfies Snapshot;
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => coached });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("tab", { name: "AI Coach" }));
  const coachCard = screen.getByText("Slow, allowlisted experiments for the fast engine · Shadow-only").closest("article");
  expect(coachCard).toHaveTextContent("InfluenceResearch only");
  expect(coachCard).toHaveTextContent("24 / 60 usable");
  expect(screen.getByRole("region", { name: "AI Coach research lanes" })).toHaveTextContent("Manipulation");
  expect(screen.getByRole("button", { name: "Show research notebook" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("progressbar", { name: "Coach forward-test progress" })).toHaveAttribute("aria-valuenow", "24");
  fireEvent.click(screen.getByRole("button", { name: "Pause research" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/coach-research",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false }) }),
  ));
});

test("announces a proved Coach idea and requires explicit tournament permission", async () => {
  const now = new Date().toISOString();
  const ready = {
    ...snapshot,
    ai_lab: { ...snapshot.ai_lab, mode: "shadow" as const },
    coach: {
      ...snapshot.coach,
      mode: "shadow" as const,
      research_enabled: true,
      state: "promising" as const,
      contribution_enabled: false,
      contribution_ready: true,
      recent_hypotheses: [{
        hypothesis_id: "coach-ready-entry",
        created_at: now,
        updated_at: now,
        cutoff_at: now,
        kind: "entry_veto" as const,
        skill: "entry" as const,
        state: "promising" as const,
        title: "Preserve cash during weak momentum",
        rationale: "Supported by independent forward evidence.",
        risk_mode: "balanced" as const,
        model_name: "qwen3.5:4b",
        feature_name: "momentum",
        operator: "<=" as const,
        threshold: 0,
        conditions: [{ feature_name: "momentum", operator: "<=" as const, threshold: 0 }],
        hold_seconds: null,
        discovery_observed_count: 100,
        discovery_usable_count: 90,
        discovery_availability_fraction: 0.9,
        discovery_mean_uplift: 0.05,
        discovery_uplift_lower_bound: 0.02,
        forward_observed_count: 80,
        forward_usable_count: 70,
        forward_availability_fraction: 0.875,
        forward_season_count: 2,
        forward_mean_uplift: 0.04,
        forward_uplift_lower_bound: 0.015,
        forward_uplift_upper_bound: 0.065,
        minimum_forward_samples: 60,
        minimum_availability_fraction: 0.7,
        last_evaluated_at: now,
        contribution_state: "ready" as const,
        influence_applied: false as const,
        context_active: true,
      }],
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 2,
    initialized: true,
    activeView: "coach",
    expandedSections: [],
    seenMilestoneIds: [],
  }));
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ready });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Learning" })).toHaveAttribute("title", "New learning milestone");
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  fireEvent.click(screen.getByRole("button", { name: "Show road to contribution" }));
  expect(screen.getByLabelText("Coach contribution path")).toHaveTextContent("Champion battle");
  const allow = screen.getByRole("button", { name: "Allow contribution" });
  expect(allow).toBeEnabled();
  fireEvent.click(allow);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/coach-contribution",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true }) }),
  ));
});

test("shows paused Coach research and keeps contribution revocation available", async () => {
  const paused = {
    ...snapshot,
    ai_lab: { ...snapshot.ai_lab, mode: "shadow" as const },
    coach: {
      ...snapshot.coach,
      mode: "off" as const,
      state: "off" as const,
      research_enabled: false,
      contribution_enabled: true,
    },
  } satisfies Snapshot;
  window.localStorage.setItem(learningUiKey, JSON.stringify({
    version: 2,
    initialized: true,
    activeView: "coach",
    expandedSections: ["coach_contribution"],
    seenMilestoneIds: [],
  }));
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => paused });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByText("Paused · Shadow")).toBeInTheDocument();
  expect(screen.getByText("Research can resume without losing evidence")).toBeInTheDocument();
  const revoke = screen.getByRole("button", { name: "Turn contribution off" });
  expect(revoke).toBeEnabled();
  fireEvent.click(revoke);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ai-lab/coach-contribution",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false }) }),
  ));
});
