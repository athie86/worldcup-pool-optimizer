export interface Team {
  id: string;
  name: string;
  short_name?: string;
  flag_emoji?: string;
  group_label?: string;
  fifa_code?: string;
}

export interface Match {
  id: string;
  match_number?: number;
  stage: string;
  group_label?: string;
  home_team_id?: string;
  away_team_id?: string;
  home_team?: string;
  away_team?: string;
  home_placeholder?: string;
  away_placeholder?: string;
  kickoff_at?: string;
  venue?: string;
  city?: string;
  country?: string;
  status: string;
  scoring_basis: string;
  is_manual: boolean;
  is_complete_for_optimization: boolean;
  provider_event_id?: string;
  fit_status?: string;
  has_overrides?: boolean;
  has_odds?: boolean;
}

export interface ScoringRule {
  id: string;
  code: string;
  label: string;
  description?: string;
  points: number;
  enabled: boolean;
  display_specificity_rank: number;
  phase: string;
  example?: string;
  config?: Record<string, unknown> | null;
}

export type CombineMode = 'best' | 'additive';

export type KnockoutScoringBasis =
  | 'ninety_minutes'
  | 'ninety_minutes_extra_time'
  | 'ninety_minutes_extra_time_penalties';

export interface PoolConfig {
  id: string;
  name: string;
  description?: string;
  default_top_n: number;
  candidate_max_goals: number;
  ranking_metric: string;
  margin_removal_method: string;
  group_combine_mode: CombineMode;
  knockout_combine_mode: CombineMode;
  group_cap?: number | null;
  knockout_cap?: number | null;
  knockout_scoring_basis: KnockoutScoringBasis;
  pick_lock_minutes_before?: number | null;
  active: boolean;
  scoring_rules?: ScoringRule[];
}

export interface OddsSnapshot {
  id: string;
  provider: string;
  fetched_at: string;
  status: string;
  requested_markets: string[];
}

export interface OddsRefreshResult {
  snapshot_id: string;
  status: string;
  events_count: number;
  message?: string;
}

export interface ImportSummary {
  message: string;
  created: number;
  updated: number;
  teams_created: number;
  skipped: number;
  errors: string[];
}

export interface MarketOdds {
  market_key: string;
  line?: number;
  outcomes: {
    outcome_type: string;
    price_decimal: number;
    normalized_probability?: number;
  }[];
  bookmaker_key?: string;
}

export interface ManualOverride {
  id: string;
  market_key: string;
  line?: number;
  outcome_type: string;
  price_decimal: number;
  enabled: boolean;
  reason?: string;
}

export interface MatchOdds {
  match_id: string;
  bookmaker_markets: MarketOdds[];
  consensus_probabilities: {
    home_win?: number;
    draw?: number;
    away_win?: number;
    over_1_5?: number;
    under_1_5?: number;
    over_2_5?: number;
    under_2_5?: number;
    over_3_5?: number;
    under_3_5?: number;
  };
  overrides: ManualOverride[];
}

export interface Recommendation {
  rank: number;
  predicted_home_goals: number;
  predicted_away_goals: number;
  penalties_winner?: string;
  expected_points: number;
  variance_points: number;
  zero_point_probability: number;
  score_probability: number;
  scoring_breakdown: Record<string, number>;
  // Horizon model additive fields (undefined for group / legacy runs)
  scoring_basis?: string;
  score_horizon?: string;
  outcome_horizon?: string;
  predicted_penalty_winner?: string;
  predicted_advancer?: string;
  prob_home_advances?: number;
  prob_away_advances?: number;
  prob_goes_to_penalties?: number;
}

export interface MatchRecommendation {
  match_id: string;
  stage?: string;
  scoring_basis?: string;
  home_team: string;
  away_team: string;
  kickoff_at?: string;
  lambda_home?: number;
  lambda_away?: number;
  fit_status: string;
  // V2 additive fields (undefined for legacy v1 runs)
  model_version?: string;
  fit_tier?: string;
  final_home_xg?: number;
  final_away_xg?: number;
  market_coverage_score?: number;
  used_markets?: string[];
  missing_markets?: string[];
  warnings?: string[];
  knockout_extras?: Record<string, number>;
  recommendations: Recommendation[];
}

export interface ModelRun {
  id: string;
  pool_config_id: string;
  status: string;
  run_type: string;
  started_at: string;
  completed_at?: string;
  parameters: Record<string, unknown>;
  summary?: {
    matches_total: number;
    optimized: number;
    incomplete: number;
    warnings: number;
  };
}

export interface DiagnosticsRow {
  target: string;
  market: number;
  prior?: number;    // DC prior implied probability
  model: number;     // entropy-calibrated implied probability
  error: number;     // calibrated − market
}

export interface ConstraintDetail {
  market_key: string;
  market_family: string;
  constraint_type: string;
  side?: string | null;
  line?: number | null;
  target_value: number;
  fitted_value: number;
  error: number;
  weight: number;
  bookmaker_count: number;
  quality_label?: string;
  devig_method?: string;
}

export interface Diagnostics {
  match_id: string;
  lambda_home: number;
  lambda_away: number;
  rho?: number;
  total_expected_goals: number;
  rmse: number;                          // calibrated RMSE
  prior_rmse?: number;                   // DC prior RMSE
  max_single_market_error?: number;
  kl_divergence_from_prior?: number;
  tail_mass_before_normalization?: number;
  fit_status: string;
  rows: DiagnosticsRow[];
  warnings: string[];
  score_matrix: number[][];              // calibrated matrix (v1: 6×6, v2: 13×13)
  prior_matrix?: number[][];             // prior matrix (same shape as score_matrix)
  expected_points_matrix?: number[][];
  // V2 additive fields (undefined for legacy v1 runs)
  model_type?: string;
  model_version?: string;
  fit_tier?: string;
  actual_score_max?: number;
  candidate_score_max?: number;
  market_coverage_score?: number;
  used_markets?: string[];
  missing_markets?: string[];
  final_home_xg?: number;
  final_away_xg?: number;
  final_total_xg?: number;
  constraint_count?: number;
  max_constraint_error?: number;
  constraint_details?: ConstraintDetail[];
}

export interface DashboardStats {
  latest_odds_refresh?: string;
  matches_ready: number;
  matches_incomplete: number;
  matches_with_overrides: number;
  latest_model_run?: ModelRun;
  avg_fit_quality?: string;
}

export interface ExportRecord {
  id: string;
  created_at: string;
  format: 'csv' | 'xlsx' | 'excel';
  filename?: string;
  model_run_id?: string;
  download_url: string;
  size_bytes?: number;
}

export interface AppSettings {
  odds_sport_key: string;
  odds_regions: string[];
  odds_bookmakers: string[];
  refresh_hour_utc: number;
  refresh_timezone: string;
  auto_run_optimizer: boolean;
  odds_api_key_configured: boolean;
}
