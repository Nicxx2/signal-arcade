import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";
import type { Decision, Snapshot } from "./types";

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

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
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
  const toggle = screen.getByRole("switch", { name: "Disable automatic new seasons" });
  expect(toggle).toHaveAttribute("aria-checked", "true");
  fireEvent.click(toggle);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/season-automation",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false }) }),
  ));
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

test("keeps future AI influence stages visible but unavailable", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  expect(screen.getByText("AI Decision Lab")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Qualified Coach/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show AI Decision Lab details" }));
  expect(screen.getByRole("button", { name: /Qualified Coach/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Live Critic/ })).toBeDisabled();
  expect(screen.getByRole("tooltip", { name: /available only after Shadow earns enough forward/ })).toBeInTheDocument();
  expect(screen.getByRole("tooltip", { name: /considered only after Qualified Coach proves useful/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Shadow/ }));

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
  const evidenceToggle = screen.getByRole("button", { name: "Show learning evidence" });
  const boundariesToggle = screen.getByRole("button", { name: "Show permanent boundaries" });
  expect(evidenceToggle).toHaveAttribute("aria-expanded", "false");
  expect(boundariesToggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Forward test")).not.toBeInTheDocument();

  fireEvent.click(evidenceToggle);
  expect(screen.getByText("Forward test")).toBeInTheDocument();
  expect(screen.getByText("What it is noticing")).toBeInTheDocument();
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
  expect(screen.getByText("Qualified Coach (legacy)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show AI Decision Lab details" }));
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
  fireEvent.click(screen.getByRole("button", { name: "Show AI Decision Lab details" }));
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

test("shows ranked realized results with a link back to entry evidence", async () => {
  const fetchMock = vi.fn().mockImplementation(async (input: string) => {
    if (input.startsWith("/api/v1/leaderboard")) {
      return {
        ok: true,
        json: async () => ({
          sort: "profit",
          summary: { closed_trades: 1, wins: 1, losses: 0, total_realized_pnl_minor: 500_000_000, audited_exits: 1, winner_reversals: 0, average_peak_capture_fraction: 0.8 },
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
  expect(screen.getByText("+0.500 SOL")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Why it bought/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open WIN on GMGN" })).toHaveAttribute("href", "https://gmgn.ai/sol/token/mint-winner");
  fireEvent.click(screen.getByRole("button", { name: "Take profit" }));
  expect(screen.getByText("Why it sold")).toBeInTheDocument();
  expect(screen.getByText("5m buy ratio 41% · 1m momentum -4.0%")).toBeInTheDocument();
});

test("keeps trades as the default Results view and compares durable paper seasons", async () => {
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

  fireEvent.click(screen.getByRole("button", { name: "Seasons" }));
  expect(await screen.findByText("Is the strategy improving each season?")).toBeInTheDocument();
  expect(await screen.findByText("Season 2")).toBeInTheDocument();
  expect(screen.getByText("Ended 1.200 SOL")).toBeInTheDocument();
  expect(screen.getByText("Now 105.00 USDC")).toBeInTheDocument();
  expect(screen.getByText("Building the baseline")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Season 1: 67% win rate; Season 2: 50% win rate/ })).toBeInTheDocument();
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
    body: JSON.stringify({ quote_currency: "USDC", starting_amount: "1250" }),
  }));
  expect(fetchMock.mock.calls.some(([path]) => String(path).includes("/engine/start"))).toBe(false);
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
  expect(screen.getByText("Experience earns influence—slowly.")).toBeInTheDocument();
  expect(screen.getByText(/Switch to Solana mainnet when you want to collect/)).toBeInTheDocument();
  expect(screen.getByText("Demo experience stays separate")).toBeInTheDocument();
  expect(screen.getByText("0 / 80")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use qualified learner" })).toBeDisabled();

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
        policy_veto_count: 5,
        policy_winner_veto_count: 1,
        policy_mean_uplift: -0.01,
        policy_uplift_lower_bound: -0.02,
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
      filled_at: new Date().toISOString(),
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
  expect(screen.getByText("pump_curve · Stop loss")).toBeInTheDocument();
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
    coach: {
      ...snapshot.coach,
      state: "testing" as const,
      outcomes_seen: 240,
      outcomes_until_review: 0,
      recent_hypotheses: [{
        hypothesis_id: "coach-hypothesis-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        cutoff_at: new Date().toISOString(),
        kind: "entry_veto" as const,
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
        influence_applied: false as const,
        context_active: true,
      }],
    },
  } satisfies Snapshot;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => coached }));
  render(<App />);

  expect(await screen.findByText("Your strategy, playing forward.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Learning" }));
  const coachCard = await screen.findByText("AI Coach Room");
  expect(coachCard.closest("article")).toHaveTextContent("InfluenceNone");
  expect(coachCard.closest("article")).toHaveTextContent("24 / 60 usable");
  expect(screen.getByRole("progressbar", { name: "Coach forward-test progress" })).toHaveAttribute("aria-valuenow", "24");
});
