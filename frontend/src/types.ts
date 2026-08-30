export type RiskMode = "safe" | "balanced" | "aggressive";
export type ProfileTransitionStrategy = "finish_safely" | "end_now";
export type DecisionAction = "enter" | "watch" | "pass" | "abstain";
export type QuoteCurrency = "SOL" | "USDC";
export type LearningMode = "off" | "shadow" | "active";
export type AiDecisionMode = "off" | "shadow" | "guarded";

export type DrawdownPolicyKind = "default" | "custom" | "disabled";

export interface DrawdownPolicy {
  kind: DrawdownPolicyKind;
  custom_threshold_bps: number | null;
}

export interface SeasonProfile {
  schema_version: number;
  provenance: "exact";
  risk_mode: RiskMode;
  risk_policy_version: string;
  risk_limits: Record<string, number | string>;
  drawdown_policy: DrawdownPolicy;
  effective_drawdown_bps: number | null;
  profile_fingerprint: string;
  learning_fingerprint: string | null;
  locked_at: string | null;
}

export interface DataValue {
  value: number | string | boolean | null;
  unit: string;
  as_of: string;
  sources: string[];
  freshness_seconds: number;
  quality: number;
  missing_reason: string | null;
}

export interface FeatureSnapshot {
  mint: string;
  symbol: string;
  name: string;
  venue: string;
  computed_at: string;
  values: Record<string, DataValue>;
  data_confidence: number;
  hard_flags: string[];
}

export interface Decision {
  decision_id: string;
  mint: string;
  symbol: string;
  created_at: string;
  action: DecisionAction;
  risk_mode: RiskMode;
  score: {
    opportunity: number;
    danger: number;
    execution: number;
    confidence: number;
    net_edge_index: number;
    composite: number;
  };
  reasons: string[];
  blockers: string[];
  feature_snapshot: FeatureSnapshot;
  model_version: string;
  season_id: string | null;
  season_profile_fingerprint?: string | null;
  configuration_fingerprint: string | null;
  planned_order_size_sol: number | null;
  learning_assessment: {
    model_version: string;
    predicted_net_return: number;
    conservative_net_return: number;
    validation_rmse: number;
    applied: boolean;
    verdict: string;
  } | null;
}

export interface ExitAssessment {
  policy_version: string;
  evaluated_at: string;
  action: "hold" | "wait" | "exit";
  reason: string;
  support_score: number;
  pnl_fraction: number;
  peak_return_fraction: number;
  drawdown_from_peak_fraction: number;
  age_seconds: number;
  soft_hold_seconds: number;
  hard_hold_seconds: number;
  evidence: string[];
}

export interface Position {
  // Legacy field names: these use the portfolio's quote currency and decimals.
  position_id: string;
  mint: string;
  symbol: string;
  token_units: number;
  entry_cost_lamports: number;
  book_value_lamports: number;
  opened_at: string;
  last_mark_lamports: number;
  unrealized_pnl_lamports: number;
  last_marked_at: string | null;
  mark_age_seconds: number | null;
  mark_is_stale: boolean;
  mark_is_executable: boolean;
  mark_blockers: string[];
  market_status: "active" | "exit_blocked" | "dormant";
  risk_mode_at_entry: RiskMode | null;
  peak_mark_lamports: number;
  peak_marked_at: string | null;
  exit_assessment: ExitAssessment | null;
}

export interface Order {
  order_id: string;
  mint: string;
  symbol: string;
  side: "buy" | "sell";
  status: string;
  requested_sol_lamports: number;
  requested_token_units: number;
  reserved_account_minor: number;
  created_at: string;
  fill_after: string;
}

export interface Fill {
  fill_id: string;
  order_id: string;
  mint: string;
  symbol: string;
  side: "buy" | "sell";
  filled_at: string;
  token_units: number;
  gross_sol_lamports: number;
  protocol_fee_lamports: number;
  network_fee_lamports: number;
  net_sol_lamports: number;
  price_impact_fraction: number;
  latency_ms: number;
  venue: string;
  assumptions: string[];
  account_currency: QuoteCurrency;
  account_decimals: number;
  account_gross_minor: number;
  account_protocol_fee_minor: number;
  account_network_fee_minor: number;
  account_net_minor: number;
  sol_usd_price: number | null;
  exit_assessment: ExitAssessment | null;
  position_opened_at: string | null;
  entry_risk_mode: RiskMode | null;
  peak_account_minor: number;
  realized_return_fraction: number | null;
  peak_return_fraction: number | null;
}

export interface Portfolio {
  // Legacy *_lamports values are minor units: lamports for SOL, micro-USDC for USDC.
  initialized: boolean;
  quote_currency: QuoteCurrency;
  quote_decimals: number;
  cash_lamports: number;
  reserved_cash_lamports: number;
  available_cash_lamports: number;
  invested_value_lamports: number;
  last_known_invested_value_lamports: number;
  stale_invested_value_lamports: number;
  stale_position_count: number;
  route_blocked_invested_value_lamports: number;
  route_blocked_position_count: number;
  excluded_invested_value_lamports: number;
  excluded_position_count: number;
  starting_lamports: number;
  equity_lamports: number;
  last_known_equity_lamports: number;
  realized_pnl_lamports: number;
  unrealized_pnl_lamports: number;
  drawdown_fraction: number;
  risk_halted: boolean;
  risk_halt_reason: string | null;
  positions: Position[];
  pending_orders: Order[];
}

export interface EquityPoint {
  recorded_at: string;
  equity_lamports: number;
  cash_lamports: number;
}

export interface ProviderQuota {
  calls_this_month: number;
  projected_monthly_calls: number;
  monthly_limit: number | null;
  requests_per_minute: number;
  effective_requests_per_minute: number;
  reserve_fraction: number;
  monthly_pacing: boolean;
  billable: boolean;
  billable_allowed: boolean;
}

export interface ProviderPolicy {
  label: string;
  requests_per_minute: number;
  monthly_limit: number | null;
  reserve_fraction: number;
  paid_mode: boolean;
}

export interface ProviderPreset {
  id: string;
  label: string;
  requests_per_minute: number;
  monthly_limit: number | null;
  paid_mode: boolean;
}

export interface ProviderView {
  active: boolean;
  endpoint: string;
  stream_endpoint?: string;
  custom_endpoint?: boolean;
  api_key_configured?: boolean;
  model?: string;
  policy: ProviderPolicy;
}

export interface ProviderSettings {
  providers: Record<"solana" | "dexscreener" | "jupiter" | "ollama", ProviderView>;
  presets: Record<string, ProviderPreset[]>;
  secret_store_error: string | null;
  notes: Record<string, string>;
}

export interface ProviderConfiguration {
  solana: ProviderPolicy;
  dexscreener: ProviderPolicy;
  jupiter: ProviderPolicy;
  ollama: ProviderPolicy;
}

export interface ProviderSettingsUpdate {
  configuration: ProviderConfiguration;
  secrets: {
    solana_http?: string;
    solana_ws?: string;
    jupiter_base?: string;
    jupiter_api_key?: string;
    ollama_url?: string;
    ollama_model?: string;
    clear: string[];
  };
}

export interface LearningModelSummary {
  version: string;
  created_at: string;
  outcomes_seen: number;
  risk_mode: RiskMode | null;
  configuration_fingerprint: string | null;
  sample_count: number;
  resolved_count: number;
  outcome_availability_fraction: number;
  training_count: number;
  validation_count: number;
  embargoed_count: number;
  validation_rmse: number;
  naive_rmse: number;
  learner_correlation: number;
  baseline_correlation: number;
  learner_top_mean_return: number;
  baseline_top_mean_return: number;
  overall_mean_return: number;
  validation_in_distribution_fraction: number;
  policy_validation_count: number;
  policy_veto_count: number;
  policy_winner_veto_count: number;
  policy_mean_uplift: number | null;
  policy_uplift_lower_bound: number | null;
  qualified: boolean;
}

export interface ReadinessGate {
  id: string;
  label: string;
  current: number | boolean | null;
  target: number | boolean;
  comparison: ">=" | "<=" | ">" | "=";
  state: "passed" | "collecting" | "not_met";
  unit: "count" | "fraction" | "number" | "boolean" | "milliseconds";
  detail: string;
}

export interface LearningStatus {
  mode: LearningMode;
  state: "paused" | "collecting" | "challenger_testing" | "ready" | "active";
  demo_excluded: boolean;
  collecting_from_current_source: boolean;
  live_only: boolean;
  observation_count: number;
  usable_outcome_count: number;
  pending_count: number;
  unavailable_outcome_count: number;
  minimum_training_samples: number;
  retained_observation_limit: number;
  retained_model_limit: number;
  model_window_observations: number;
  entry_outcome_availability: {
    observed_count: number;
    available_count: number;
    availability_fraction: number;
    minimum_fraction: number;
    qualified: boolean;
  };
  outcomes_until_next_training: number;
  challenger_interval_outcomes: number;
  horizons_seconds: number[];
  horizon_performance: Array<{
    horizon_seconds: number;
    observed_count: number;
    available_count: number;
    availability_fraction: number;
    mean_net_return: number | null;
    conservative_utility: number | null;
  }>;
  recommended_hold_seconds: Record<RiskMode, number>;
  hold_timing_validation: Record<RiskMode, {
    qualified: boolean;
    selected_horizon_seconds: number;
    baseline_horizon_seconds: number;
    sample_count: number;
    training_count: number;
    validation_count: number;
    embargoed_count: number;
    selected_training_utility: number | null;
    baseline_training_utility: number | null;
    selected_validation_utility: number | null;
    baseline_validation_utility: number | null;
    validation_uplift_lower_bound: number | null;
    validation_availability_fraction: number;
  }>;
  adaptive_hold_applied: boolean;
  latest_model: LearningModelSummary | null;
  active_model: LearningModelSummary | null;
  active_model_health: {
    state: "inactive" | "collecting" | "healthy" | "degraded" | "unverifiable" | "suspended";
    model_version: string | null;
    observed_count: number;
    usable_count: number;
    minimum_samples: number;
    availability_fraction: number;
    baseline_mean_return: number | null;
    learner_mean_return: number | null;
    estimated_uplift: number | null;
    uplift_upper_bound: number | null;
    supported_count: number;
    vetoed_count: number;
    winner_vetoed_count: number;
    suspension_reason?: "degraded" | "unverifiable";
    suspended_at?: string;
  };
  activation_available: boolean;
  qualification_gates?: ReadinessGate[];
  qualification_passed?: number;
  qualification_total?: number;
  lessons: Array<{
    feature: string;
    label: string;
    effect: "helped" | "hurt";
    coefficient: number;
  }>;
  guardrails: string[];
}

export interface AiModelCatalogEntry {
  name: string;
  label: string;
  download_bytes: number;
  recommended_ram_gb: number;
  role: string;
  installed: boolean;
  installed_bytes: number | null;
  digest: string | null;
  fits_recommended_ram: boolean;
}

export interface AiModelDownload {
  model: string;
  status: "queued" | "downloading" | "ready" | "error";
  completed_bytes: number;
  total_bytes: number;
  progress_fraction: number;
  message: string;
  error: string | null;
}

export interface AiQualification {
  qualified: boolean;
  curated_model: boolean;
  model_digest: string | null;
  configuration_fingerprint: string;
  assessments: number;
  resolved: number;
  minimum_resolved: number;
  veto_outcomes: number;
  minimum_veto_outcomes: number;
  valid_fraction: number;
  minimum_valid_fraction: number;
  mean_counterfactual_uplift: number | null;
  uplift_lower_bound: number | null;
  p95_latency_ms: number | null;
  maximum_p95_latency_ms: number;
  gates?: ReadinessGate[];
  passed?: number;
  total?: number;
}

export interface AiCriticAssessment {
  assessment_id: string;
  decision_id: string;
  mint: string;
  symbol: string;
  created_at: string;
  mode: AiDecisionMode;
  applied: boolean;
  model_name: string;
  input_sha256: string;
  input_payload: Record<string, unknown>;
  latency_ms: number;
  valid: boolean;
  invalid_reason: string | null;
  verdict: "support" | "veto" | "insufficient_evidence" | null;
  confidence: string | null;
  evidence_refs: string[];
  risk_flags: string[];
  summary: string;
  outcome_net_return: number | null;
  counterfactual_uplift: number | null;
  outcome_missing_reason: string | null;
  resolved_at: string | null;
  season_profile_fingerprint?: string | null;
}

export interface AiLabStatus {
  mode: AiDecisionMode;
  selected_model: string;
  selected_model_installed: boolean;
  ollama_available: boolean;
  ollama_reachable: boolean;
  ollama_version: string | null;
  deployment: "bundled" | "external";
  configured_accelerator: "cpu" | "nvidia" | "amd" | "external";
  runtime_compute: "unavailable" | "unknown" | "idle" | "cpu" | "gpu" | "hybrid";
  loaded_model_count: number;
  loaded_model_bytes: number;
  loaded_vram_bytes: number;
  last_checked_at: string | null;
  system_memory_bytes: number | null;
  catalog: AiModelCatalogEntry[];
  downloads: AiModelDownload[];
  queue_depth: number;
  queue_capacity: number;
  queue_drops: number;
  inference_busy: boolean;
  qualification: AiQualification;
  recent_assessments: AiCriticAssessment[];
  model_storage: "ollama_external";
  model_storage_counts_toward_app_limit: false;
}

export interface CoachReview {
  review_id: string;
  created_at: string;
  outcomes_seen: number;
  risk_mode: RiskMode;
  model_name: string;
  candidate_count: number;
  latency_ms: number;
  valid: boolean;
  selected_candidate_id: string | null;
  summary: string;
  failure_reason: string | null;
}

export interface CoachHypothesis {
  hypothesis_id: string;
  created_at: string;
  updated_at: string;
  cutoff_at: string;
  kind: "entry_veto" | "earlier_review";
  state: "testing" | "promising" | "inconclusive" | "not_supported";
  title: string;
  rationale: string;
  risk_mode: RiskMode;
  model_name: string;
  feature_name: string | null;
  operator: "<=" | ">=" | null;
  threshold: number | null;
  hold_seconds: number | null;
  discovery_observed_count: number;
  discovery_usable_count: number;
  discovery_availability_fraction: number;
  discovery_mean_uplift: number | null;
  discovery_uplift_lower_bound: number | null;
  forward_observed_count: number;
  forward_usable_count: number;
  forward_availability_fraction: number;
  forward_season_count: number;
  forward_mean_uplift: number | null;
  forward_uplift_lower_bound: number | null;
  forward_uplift_upper_bound: number | null;
  minimum_forward_samples: number;
  minimum_availability_fraction: number;
  last_evaluated_at: string | null;
  influence_applied: false;
  context_active: boolean;
}

export interface CoachStatus {
  mode: "off" | "shadow";
  state: "off" | "waiting" | "reviewing" | "testing" | "promising" | "inconclusive" | "not_supported";
  influence: "none";
  worker_running: boolean;
  busy: boolean;
  paused_reason: string | null;
  last_error: string | null;
  last_attempt_at: string | null;
  review_interval_outcomes: number;
  outcomes_seen: number;
  outcomes_until_review: number;
  minimum_forward_samples: number;
  minimum_forward_seasons: number;
  qualification_gates?: ReadinessGate[];
  qualification_passed?: number;
  qualification_total?: number;
  recent_hypotheses: CoachHypothesis[];
  recent_reviews: CoachReview[];
  guardrails: string[];
}

export interface OperationalIncident {
  incident_id: string;
  scope: string;
  severity: string;
  title: string;
  detail: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrences: number;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}

export interface StorageStatus {
  market_events: number;
  decisions: number;
  paper_orders: number;
  fills: number;
  positions: number;
  equity_points: number;
  equity_rollups: number;
  learning_observations: number;
  learning_models: number;
  ai_critic_assessments: number;
  coach_reviews: number;
  coach_hypotheses: number;
  operational_incidents: number;
  database_bytes: number;
  live_bytes: number;
  reclaimable_bytes: number;
  wal_bytes: number;
  total_disk_bytes: number;
  max_database_bytes: number;
  raw_trade_retention_hours: number;
  maintenance_interval_seconds: number;
  model_storage_included: false;
}

export interface LeaderboardRow {
  mint: string;
  symbol: string;
  status: "open" | "closed";
  pnl_minor: number;
  last_known_pnl_minor: number;
  return_fraction: number;
  fees_minor: number;
  opened_at: string;
  closed_at: string | null;
  hold_seconds: number;
  exit_reason: string | null;
  exit_assessment: ExitAssessment | null;
  peak_return_fraction: number | null;
  peak_capture_fraction: number | null;
  entry_risk_mode: RiskMode | null;
  entry_decision_id: string | null;
  mark_is_stale: boolean;
  market_status: "active" | "exit_blocked" | "dormant" | "closed";
  mark_is_executable: boolean;
  quote_currency: QuoteCurrency;
  quote_decimals: number;
}

export interface Leaderboard {
  sort: "profit" | "loss" | "recent";
  rows: LeaderboardRow[];
  available_rows: number;
  summary: {
    closed_trades: number;
    open_trades: number;
    wins: number;
    losses: number;
    total_realized_pnl_minor: number;
    audited_exits: number;
    winner_reversals: number;
    average_peak_capture_fraction: number | null;
    total_fees_minor: number;
    quote_currency: QuoteCurrency;
    quote_decimals: number;
  };
}

export interface PaperSeason {
  season_id: string;
  season_number: number;
  started_at: string;
  ended_at: string | null;
  quote_currency: QuoteCurrency;
  quote_decimals: number;
  starting_minor: number;
  ending_equity_minor: number | null;
  last_known_ending_equity_minor: number | null;
  peak_equity_minor: number;
  realized_pnl_minor: number;
  net_pnl_minor: number;
  total_fees_minor: number;
  closed_trades: number;
  wins: number;
  losses: number;
  break_even: number;
  ending_drawdown_fraction: number;
  open_positions: number;
  status: "current" | "completed";
  win_rate: number | null;
  net_return_fraction: number | null;
  duration_seconds: number;
  risk_mode: RiskMode | null;
  profile_fingerprint: string | null;
  profile: SeasonProfile | null;
  profile_provenance: "exact" | "legacy_unknown";
  profile_locked_at: string | null;
  terminal_reason: string | null;
  result_quality?: "complete" | "unresolved";
  comparable?: boolean;
  unresolved_inventory?: Array<{
    position_id: string;
    mint: string;
    symbol: string;
    token_units: number;
    entry_cost_minor: number;
    book_value_minor: number;
    last_known_mark_minor: number;
    last_marked_at: string | null;
    market_status: "active" | "exit_blocked" | "dormant";
    mark_blockers: string[];
    quote_currency: QuoteCurrency;
    quote_decimals: number;
    retirement_reason: string;
    retired_at: string;
    was_executed: false;
  }>;
}

export interface Seasons {
  generated_at: string;
  seasons: PaperSeason[];
  current_profile_fingerprint: string | null;
  profiles: Array<{
    profile_fingerprint: string;
    risk_mode: RiskMode;
    drawdown_policy: DrawdownPolicy;
    effective_drawdown_bps: number | null;
    season_count: number;
  }>;
  summary: {
    season_count: number;
    completed_seasons: number;
    comparable_seasons?: number;
    profitable_seasons: number;
    losing_seasons: number;
    average_win_rate: number | null;
    best_return_fraction: number | null;
  };
}

export interface SeasonAutomation {
  enabled: boolean;
  state: "off" | "maintenance" | "no_bankroll" | "engine_stopped" | "monitoring" | "pending_orders" | "managing_positions" | "waiting_for_data" | "operation_pending" | "confirming" | "countdown" | "paused" | "due";
  detail: string;
  grace_seconds: number;
  eligible_since: string | null;
  paused_since?: string | null;
  verified_seconds?: number | null;
  rollover_at: string | null;
  remaining_seconds: number | null;
  last_rollover_at: string | null;
}

export interface SeasonOperation {
  operation_id: string;
  kind: "reset" | "setup" | "start" | "profile_transition";
  state: "running" | "completed" | "failed";
  stage: string;
  detail: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  target_risk_mode?: RiskMode;
  target_profile_fingerprint?: string;
  previous_running?: boolean;
  transition_strategy?: ProfileTransitionStrategy;
  manual_settlement_started_at?: string | null;
  manual_settlement_deadline?: string | null;
  unresolved_positions?: number;
}

export interface MaintenanceOperation {
  operation_id: string;
  kind: "upgrade";
  state: "running" | "ready" | "completed" | "cancelled" | "failed";
  stage: string;
  detail: string;
  started_at: string;
  updated_at: string;
  ready_at: string | null;
  completed_at: string | null;
  prepared_version: string;
  restarted_version: string | null;
  previous_running: boolean;
  auto_season_remaining_seconds: number | null;
  cancelled_pending_orders: number;
  interrupted_ai_downloads: number;
}

export interface Snapshot {
  version: string;
  running: boolean;
  service_running: boolean;
  started_at: string | null;
  server_time: string;
  snapshot_generated_at?: string;
  snapshot_age_seconds?: number;
  demo_mode: boolean;
  paper_only: boolean;
  risk_mode: RiskMode;
  season_profile: SeasonProfile | null;
  season_profile_provenance: "exact" | "legacy_unknown";
  season_profile_catalog: SeasonProfile[];
  candidate_window_minutes: number;
  stale_market_seconds: number;
  provider_health: Record<string, unknown>;
  database_ok: boolean;
  events: Record<string, number>;
  event_pipeline: {
    queue_depth: number;
    queue_capacity: number;
    enqueued: number;
    processed: number;
    persisted: number;
    ephemeral: number;
    critical_processed: number;
    dropped: number;
    expired_candidate_events?: number;
    queue_utilization: number;
    last_processed_at: string | null;
    last_source_event_at: string | null;
    processing_lag_seconds: number;
    degraded: boolean;
    degraded_reasons: string[];
  };
  portfolio: Portfolio;
  season_automation: SeasonAutomation;
  season_operation: SeasonOperation | null;
  maintenance_operation: MaintenanceOperation | null;
  tokens: FeatureSnapshot[];
  decisions: Decision[];
  fills: Fill[];
  equity_history: EquityPoint[];
  quotas: Record<string, ProviderQuota>;
  provider_settings: ProviderSettings;
  learning: LearningStatus;
  ai_lab: AiLabStatus;
  coach: CoachStatus;
  operational_incidents: OperationalIncident[];
  storage: StorageStatus;
}

export interface HealthStatus {
  ok: boolean;
  running: boolean;
  service_running: boolean;
  database_ok: boolean;
  degraded: boolean;
  degraded_reasons: string[];
  paper_only: boolean;
  version: string;
}
