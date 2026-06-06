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
}

export interface PoolConfig {
  id: string;
  name: string;
  description?: string;
  default_top_n: number;
  candidate_max_goals: number;
  ranking_metric: string;
  margin_removal_method: string;
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
  expected_points: number;
  variance_points: number;
  zero_point_probability: number;
  score_probability: number;
  scoring_breakdown: Record<string, number>;
}

export interface MatchRecommendation {
  match_id: string;
  home_team: string;
  away_team: string;
  kickoff_at?: string;
  lambda_home?: number;
  lambda_away?: number;
  fit_status: string;
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
  score_matrix: number[][];              // calibrated 6×6
  prior_matrix?: number[][];             // DC prior 6×6
  expected_points_matrix?: number[][];
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
  format: 'csv' | 'xlsx';
  filename: string;
  model_run_id?: string;
  pool_config_id?: string;
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
}
