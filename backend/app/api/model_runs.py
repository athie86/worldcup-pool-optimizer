from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import models
from ..db.session import get_db
from ..schemas.model_runs import (
    ModelRunOut,
    ModelRunCreate,
    ModelRunWithFits,
    ScoreRecommendationOut,
    MatchRecommendationOut,
    RecommendationItem,
    DiagnosticsOut,
    DiagnosticsRow,
)
from ..services.scoring import ScoringRule as SvcScoringRule
from ..services.score_model import MarketProbabilities
from ..services.optimizer import compute_expected_points
from ..services.odds_normalization import compute_consensus, BookmakerMarket, RawOutcome
from ..services import model_registry
from ..services.knockout_model import KnockoutExtras
from ..services.fundamental_prior import FundamentalInputs
from ..core.config import settings
from ..core.logging import logger
from .deps import get_current_user

# Map app stage labels to the fundamental-prior stage vocabulary.
_STAGE_MAP = {
    "group": "group", "group_stage": "group",
    "round_of_32": "round_of_32", "r32": "round_of_32",
    "round_of_16": "round_of_16", "r16": "round_of_16",
    "quarter_final": "quarter_final", "quarterfinal": "quarter_final", "qf": "quarter_final",
    "semi_final": "semi_final", "semifinal": "semi_final", "sf": "semi_final",
    "final": "final", "third_place": "semi_final",
}

router = APIRouter()


def _build_bookmaker_markets(events_for_match: list) -> list[BookmakerMarket]:
    """Build the per-bookmaker market list from pre-loaded ORM objects."""
    bk_markets: list[BookmakerMarket] = []
    for evt in events_for_match:
        for bm in evt.bookmaker_markets:
            outcomes = [
                RawOutcome(
                    outcome_type=mo.outcome_type,
                    price_decimal=float(mo.price_decimal),
                    line=float(bm.line) if bm.line else None,
                )
                for mo in bm.market_outcomes
            ]
            bk_markets.append(
                BookmakerMarket(
                    bookmaker_key=bm.bookmaker_key,
                    market_key=bm.market_key,
                    line=float(bm.line) if bm.line else None,
                    outcomes=outcomes,
                    last_update=bm.last_update,
                )
            )
    return bk_markets


def _build_market_probs_from_data(
    events_for_match: list,
    overrides_for_match: list,
) -> tuple[MarketProbabilities, list[BookmakerMarket]]:
    """Build (MarketProbabilities consensus, bookmaker markets) from ORM objects.

    The bookmaker markets are returned so the V2 model can build richer
    constraints; the consensus drives v1 and v2's market seed/fallback.
    """
    bk_markets = _build_bookmaker_markets(events_for_match)

    overrides = [
        RawOutcome(
            outcome_type=ov.outcome_type,
            price_decimal=float(ov.price_decimal),
            line=float(ov.line) if ov.line else None,
        )
        for ov in overrides_for_match
        if ov.enabled
    ]

    mp = compute_consensus(bk_markets, overrides if overrides else None)
    return mp, bk_markets


def _compute_all_fits(
    match_inputs_by_id: dict[uuid.UUID, dict],
    rules: list[SvcScoringRule],
    candidate_max: int,
    group_combine_mode: str,
    knockout_combine_mode: str,
    group_cap: Optional[float],
    knockout_cap: Optional[float],
    model_version: str,
) -> tuple[dict[uuid.UUID, tuple], dict[uuid.UUID, str]]:
    """CPU-bound: fit all models and compute recommendations. Runs in a thread.

    Uses the model registry, which selects v1/v2 and falls back safely so a
    single match can never abort the run. For knockout matches the registry also
    computes supplementary ET/penalty probabilities used by the optimizer.
    """
    results: dict[uuid.UUID, tuple] = {}
    errors: dict[uuid.UUID, str] = {}
    for match_id, inp in match_inputs_by_id.items():
        try:
            scoring_basis = inp.get("scoring_basis", "ninety_minutes")
            phase = inp.get("phase", "group")
            fit, extras = model_registry.fit_with_knockout_extras(
                model_version,
                inp["market_probs"],
                inp["bookmaker_markets"],
                fundamental_inputs=inp["fundamental"],
                scoring_basis=scoring_basis,
                actual_score_max=settings.ACTUAL_SCORE_MAX,
                candidate_score_max=candidate_max,
                devig_method=settings.V2_DEVIG_METHOD,
                default_auto_devig=settings.V2_DEFAULT_AUTO_DEVIG,
                enable_fundamental=settings.ENABLE_FUNDAMENTAL_PRIOR,
                enable_asian_lines=settings.ENABLE_ASIAN_LINE_SUPPORT,
                v1_fallback_enabled=settings.V1_FALLBACK_ENABLED,
            )
            combine_mode = knockout_combine_mode if phase == "knockout" else group_combine_mode
            cap = knockout_cap if phase == "knockout" else group_cap
            recs = compute_expected_points(
                fit,
                rules,
                candidate_max,
                combine_mode=combine_mode,
                cap=cap,
                phase=phase,
                knockout_extras=extras,
            )
            results[match_id] = (fit, recs, extras)
        except Exception as exc:
            errors[match_id] = str(exc)
    return results, errors


@router.post("/model-runs", response_model=ModelRunOut, status_code=201)
async def create_model_run(
    body: ModelRunCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Load pool config with scoring rules
    pc_result = await db.execute(
        select(models.PoolConfig)
        .options(selectinload(models.PoolConfig.scoring_rules))
        .where(models.PoolConfig.id == body.pool_config_id)
    )
    pool_config = pc_result.scalar_one_or_none()
    if not pool_config:
        raise HTTPException(status_code=404, detail="Pool config not found")

    # Build scoring rules (pure Python, no DB) — include phase so the scoring
    # engine can filter correctly for group vs knockout matches.
    rules = [
        SvcScoringRule(
            code=r.code,
            label=r.label,
            points=float(r.points),
            enabled=r.enabled,
            display_specificity_rank=r.display_specificity_rank,
            phase=getattr(r, "phase", "group"),
            config=r.config,
        )
        for r in pool_config.scoring_rules
    ]

    # Resolve snapshot: always pin to a single snapshot so consensus only uses
    # current prices, never an average of historical refreshes.
    snapshot_id = body.odds_snapshot_id
    if snapshot_id is None:
        snap_result = await db.execute(
            select(models.OddsSnapshot.id)
            .where(models.OddsSnapshot.status == "success")
            .order_by(models.OddsSnapshot.fetched_at.desc())
            .limit(1)
        )
        row = snap_result.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=400,
                detail="No successful odds snapshot found. Refresh odds first.",
            )
        snapshot_id = row

    # Create model run record
    run = models.ModelRun(
        pool_config_id=body.pool_config_id,
        odds_snapshot_id=snapshot_id,
        run_type=body.run_type,
        status="running",
        parameters=body.parameters or {},
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # Load matches to optimize
    match_q = (
        select(models.Match)
        .options(
            selectinload(models.Match.home_team),
            selectinload(models.Match.away_team),
            selectinload(models.Match.manual_overrides),
        )
        .where(models.Match.is_complete_for_optimization == True)
    )
    match_result = await db.execute(match_q)
    matches = match_result.scalars().all()

    if not matches:
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = "No matches marked complete_for_optimization"
        await db.commit()
        return run

    match_ids = [m.id for m in matches]

    # Batch load all OddsEvents for these matches in the pinned snapshot — one query
    events_result = await db.execute(
        select(models.OddsEvent)
        .options(
            selectinload(models.OddsEvent.bookmaker_markets).selectinload(
                models.BookmakerMarket.market_outcomes
            )
        )
        .where(
            models.OddsEvent.match_id.in_(match_ids),
            models.OddsEvent.odds_snapshot_id == snapshot_id,
        )
    )
    all_events = events_result.scalars().all()

    # Group events by match_id
    events_by_match: dict[uuid.UUID, list] = {m_id: [] for m_id in match_ids}
    for evt in all_events:
        if evt.match_id in events_by_match:
            events_by_match[evt.match_id].append(evt)

    # Resolve model version: per-run override → global setting (default v1).
    params = body.parameters or {}
    model_version = str(params.get("model_version") or settings.PREDICTION_MODEL_VERSION or "v1").lower()

    # Build per-match inputs (pure Python, no additional DB queries)
    match_inputs_by_id: dict[uuid.UUID, dict] = {}
    skipped_no_odds = 0
    for match in matches:
        # Manual overrides are already loaded via selectinload above
        mp, bk_markets = _build_market_probs_from_data(
            events_by_match.get(match.id, []),
            match.manual_overrides,
        )
        if mp.home_win is None:
            skipped_no_odds += 1
            continue
        home_name = match.home_team.name if match.home_team else (match.home_placeholder or "")
        away_name = match.away_team.name if match.away_team else (match.away_placeholder or "")
        fundamental = FundamentalInputs(
            home_team=home_name,
            away_team=away_name,
            neutral_venue=True,  # World Cup matches are on neutral ground by default
            stage=_STAGE_MAP.get((match.stage or "group").lower(), "group"),
        )
        stage = (match.stage or "group").lower()
        phase = "group" if stage == "group" else "knockout"
        # The pool's rules define the knockout time scope; the group phase is
        # always scored at 90 minutes.
        scoring_basis = (
            pool_config.knockout_scoring_basis if phase == "knockout" else "ninety_minutes"
        )
        match_inputs_by_id[match.id] = {
            "market_probs": mp,
            "bookmaker_markets": bk_markets,
            "fundamental": fundamental,
            "scoring_basis": scoring_basis,
            "phase": phase,
        }

    if not match_inputs_by_id:
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = f"{skipped_no_odds} match(es) skipped: no odds available"
        await db.commit()
        return run

    # Run all CPU-bound fits in a thread so the event loop stays free
    candidate_max = pool_config.candidate_max_goals
    fit_results, fit_errors = await asyncio.to_thread(
        _compute_all_fits,
        match_inputs_by_id,
        rules,
        candidate_max,
        pool_config.group_combine_mode,
        pool_config.knockout_combine_mode,
        float(pool_config.group_cap) if pool_config.group_cap is not None else None,
        float(pool_config.knockout_cap) if pool_config.knockout_cap is not None else None,
        model_version,
    )

    # Write results to DB
    errors = list(fit_errors.values())
    store_constraints = settings.ENABLE_MARKET_CONSTRAINT_STORAGE
    for match in matches:
        if match.id not in fit_results:
            continue
        mp = match_inputs_by_id[match.id]["market_probs"]
        fit, recs, extras = fit_results[match.id]
        try:
            # Merge knockout extras into diagnostics before persisting.
            diagnostics = dict(fit.diagnostics or {})
            if extras is not None:
                diagnostics["knockout_extras"] = {
                    "p_draw_90": extras.p_draw_90,
                    "p_home_wins_et": extras.p_home_wins_et,
                    "p_away_wins_et": extras.p_away_wins_et,
                    "p_still_draw_after_et": extras.p_still_draw_after_et,
                    "p_home_wins_penalties": extras.p_home_wins_penalties,
                    "p_away_wins_penalties": extras.p_away_wins_penalties,
                    "p_goes_to_penalties": extras.p_goes_to_penalties,
                    "optimal_penalties_winner": extras.optimal_penalties_winner,
                }
            constraint_details = diagnostics.get("constraint_details")
            model_fit = models.MatchModelFit(
                model_run_id=run.id,
                match_id=match.id,
                lambda_home=fit.lambda_home,
                lambda_away=fit.lambda_away,
                fitted_home_win_prob=fit.fitted_home_win,
                fitted_draw_prob=fit.fitted_draw,
                fitted_away_win_prob=fit.fitted_away_win,
                market_home_win_prob=mp.home_win,
                market_draw_prob=mp.draw,
                market_away_win_prob=mp.away_win,
                fit_error=fit.loss,
                fit_status=fit.fit_status,
                diagnostics=diagnostics,
                score_matrix=fit.score_matrix.tolist(),
                # ── V2 additive fields (None for v1 runs) ───────────────────
                model_type=fit.model_type,
                model_version=getattr(fit, "model_version", None),
                fit_tier=getattr(fit, "fit_tier", None),
                final_home_xg=getattr(fit, "final_home_xg", None),
                final_away_xg=getattr(fit, "final_away_xg", None),
                final_total_xg=getattr(fit, "final_total_xg", None),
                prior_error=getattr(fit, "prior_error", None),
                calibrated_error=getattr(fit, "calibrated_error", None),
                max_constraint_error=getattr(fit, "max_constraint_error", None),
                constraint_count=getattr(fit, "constraint_count", None),
                market_coverage_score=getattr(fit, "market_coverage_score", None),
                actual_score_max=getattr(fit, "actual_score_max", None),
                candidate_score_max=getattr(fit, "candidate_score_max", None),
                tail_mass=float(fit.tail_mass) if fit.tail_mass is not None else None,
                used_markets=getattr(fit, "used_markets", None) or None,
                market_constraints_json=constraint_details,
                prior_score_matrix=(
                    fit.prior_matrix.tolist() if fit.prior_matrix is not None else None
                ),
                calibration_parameters=diagnostics.get("calibration", {}).get("parameters"),
            )
            db.add(model_fit)
            await db.flush()

            # Persist consensus constraints (spec §12.3) for the rich UI/backtests.
            if store_constraints and constraint_details:
                for cd in constraint_details:
                    db.add(models.MarketConstraint(
                        odds_snapshot_id=snapshot_id,
                        match_id=match.id,
                        market_key=cd.get("market_key", ""),
                        market_family=cd.get("market_family", ""),
                        constraint_type=cd.get("constraint_type", ""),
                        side=cd.get("side"),
                        line=cd.get("line"),
                        target_type="probability",
                        target_value=cd.get("target_value", 0.0),
                        weight=cd.get("weight", 0.0),
                        devig_method=cd.get("devig_method", ""),
                        consensus_method="weighted_average",
                        bookmaker_count=cd.get("bookmaker_count", 0),
                        quality_score=None,
                        source_details={"quality_label": cd.get("quality_label")},
                    ))

            for rec in recs:
                sr = models.ScoreRecommendation(
                    match_model_fit_id=model_fit.id,
                    predicted_home_goals=rec.predicted_home,
                    predicted_away_goals=rec.predicted_away,
                    rank=rec.rank,
                    expected_points=rec.expected_points,
                    variance_points=rec.variance,
                    zero_point_probability=rec.zero_point_probability,
                    score_probability=rec.score_probability,
                    scoring_breakdown=rec.scoring_breakdown,
                    penalties_winner=rec.penalties_winner,
                )
                db.add(sr)

        except Exception as exc:
            logger.error("model_run: write failed", match_id=str(match.id), error=str(exc))
            errors.append(str(exc))

    run.status = "completed" if not errors else "partial"
    run.completed_at = datetime.now(timezone.utc)
    messages = list(errors[:3])
    if skipped_no_odds:
        messages.append(f"{skipped_no_odds} match(es) skipped: no odds available")
    if messages:
        run.error_message = "; ".join(messages)

    await db.commit()
    await db.refresh(run)
    return run


@router.get("/model-runs", response_model=list[ModelRunOut])
async def list_model_runs(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.ModelRun)
        .order_by(models.ModelRun.started_at.desc().nullslast())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/model-runs/{run_id}", response_model=ModelRunWithFits)
async def get_model_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(models.ModelRun)
        .options(
            selectinload(models.ModelRun.match_model_fits).selectinload(
                models.MatchModelFit.score_recommendations
            )
        )
        .where(models.ModelRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Model run not found")
    return run


@router.get("/model-runs/{run_id}/recommendations", response_model=list[MatchRecommendationOut])
async def get_recommendations(
    run_id: uuid.UUID,
    top_n: int = 3,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    # Verify run exists
    run_result = await db.execute(
        select(models.ModelRun).where(models.ModelRun.id == run_id)
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Model run not found")

    # Load each fit with its match (and teams) and recommendations so we can
    # group the results per match — the shape the Optimizer page expects.
    result = await db.execute(
        select(models.MatchModelFit)
        .options(
            selectinload(models.MatchModelFit.score_recommendations),
            selectinload(models.MatchModelFit.match).selectinload(models.Match.home_team),
            selectinload(models.MatchModelFit.match).selectinload(models.Match.away_team),
        )
        .where(models.MatchModelFit.model_run_id == run_id)
    )
    fits = result.scalars().all()

    grouped: list[MatchRecommendationOut] = []
    for fit in fits:
        match = fit.match
        home = (match.home_team.name if match and match.home_team else None) or (
            match.home_placeholder if match else None
        )
        away = (match.away_team.name if match and match.away_team else None) or (
            match.away_placeholder if match else None
        )
        recs = sorted(
            (r for r in fit.score_recommendations if r.rank <= top_n),
            key=lambda r: r.rank,
        )
        diag = fit.diagnostics or {}
        grouped.append(
            MatchRecommendationOut(
                match_id=fit.match_id,
                home_team=home,
                away_team=away,
                kickoff_at=match.kickoff_at if match else None,
                stage=match.stage if match else None,
                scoring_basis=match.scoring_basis if match else None,
                lambda_home=float(fit.lambda_home) if fit.lambda_home is not None else None,
                lambda_away=float(fit.lambda_away) if fit.lambda_away is not None else None,
                fit_status=fit.fit_status,
                model_version=fit.model_version or diag.get("model_version"),
                fit_tier=fit.fit_tier or diag.get("fit_tier"),
                final_home_xg=float(fit.final_home_xg) if fit.final_home_xg is not None else None,
                final_away_xg=float(fit.final_away_xg) if fit.final_away_xg is not None else None,
                market_coverage_score=(
                    float(fit.market_coverage_score) if fit.market_coverage_score is not None else None
                ),
                used_markets=fit.used_markets or diag.get("used_markets"),
                missing_markets=diag.get("missing_markets"),
                warnings=diag.get("warnings"),
                knockout_extras=diag.get("knockout_extras"),
                recommendations=[
                    RecommendationItem(
                        rank=r.rank,
                        predicted_home_goals=r.predicted_home_goals,
                        predicted_away_goals=r.predicted_away_goals,
                        expected_points=float(r.expected_points) if r.expected_points is not None else None,
                        variance_points=float(r.variance_points) if r.variance_points is not None else None,
                        zero_point_probability=float(r.zero_point_probability) if r.zero_point_probability is not None else None,
                        score_probability=float(r.score_probability) if r.score_probability is not None else None,
                        scoring_breakdown=r.scoring_breakdown,
                        penalties_winner=r.penalties_winner,
                    )
                    for r in recs
                ],
            )
        )

    # Sort by kickoff so the table reads chronologically.
    grouped.sort(key=lambda g: (g.kickoff_at is None, g.kickoff_at))
    return grouped


async def _build_diagnostics(
    db: AsyncSession,
    match_id: uuid.UUID,
    run_id: Optional[uuid.UUID],
) -> DiagnosticsOut:
    q = (
        select(models.MatchModelFit)
        .where(models.MatchModelFit.match_id == match_id)
        .order_by(models.MatchModelFit.created_at.desc())
    )
    if run_id:
        q = q.where(models.MatchModelFit.model_run_id == run_id)

    result = await db.execute(q)
    fit = result.scalar_one_or_none()
    if not fit:
        raise HTTPException(status_code=404, detail="No model fit found for this match")

    diag = fit.diagnostics or {}
    rows = []
    targets     = diag.get("market_targets", {})
    cal_probs   = diag.get("fitted_probabilities", {})
    prior_probs = diag.get("prior_probabilities", {})

    target_map = {
        "home_win":  "Home Win",
        "draw":      "Draw",
        "away_win":  "Away Win",
        "over_1_5":  "Over 1.5",
        "under_1_5": "Under 1.5",
        "over_2_5":  "Over 2.5",
        "under_2_5": "Under 2.5",
        "over_3_5":  "Over 3.5",
        "under_3_5": "Under 3.5",
    }

    for key, label in target_map.items():
        market_val = targets.get(key)
        cal_val    = cal_probs.get(key)
        prior_val  = prior_probs.get(key) if prior_probs else None
        if market_val is not None and cal_val is not None:
            rows.append(DiagnosticsRow(
                target=label,
                market=market_val,
                prior=prior_val,
                model=cal_val,
                error=cal_val - market_val,
            ))

    rmse = float(diag.get("rmse", 0))
    if rmse <= 0.02:
        status = "good"
    elif rmse <= 0.04:
        status = "acceptable"
    else:
        status = "weak"

    lh = float(fit.lambda_home or 0)
    la = float(fit.lambda_away or 0)

    final = diag.get("final", {})
    return DiagnosticsOut(
        match_id=match_id,
        lambda_home=lh,
        lambda_away=la,
        rho=float(diag.get("rho", 0.0)),
        total_expected_goals=lh + la,
        rmse=rmse,
        prior_rmse=float(diag.get("prior_rmse", rmse)),
        max_single_market_error=float(diag.get("max_single_market_error", 0.0)),
        kl_divergence_from_prior=float(diag.get("kl_divergence_from_prior", 0.0)),
        tail_mass_before_normalization=float(diag.get("tail_mass_before_normalization", 0.0)),
        fit_status=status,
        rows=rows,
        warnings=diag.get("warnings", []),
        score_matrix=fit.score_matrix or [],
        prior_matrix=diag.get("prior_matrix") or fit.prior_score_matrix,
        # ── V2 additive fields ──────────────────────────────────────────────
        model_type=fit.model_type or diag.get("model_type"),
        model_version=fit.model_version or diag.get("model_version"),
        fit_tier=fit.fit_tier or diag.get("fit_tier"),
        actual_score_max=fit.actual_score_max,
        candidate_score_max=fit.candidate_score_max,
        market_coverage_score=(
            float(fit.market_coverage_score) if fit.market_coverage_score is not None
            else diag.get("market_coverage_score")
        ),
        used_markets=(fit.used_markets if fit.used_markets is not None
                      else diag.get("used_markets")),
        missing_markets=diag.get("missing_markets"),
        final_home_xg=float(fit.final_home_xg) if fit.final_home_xg is not None else final.get("home_xg"),
        final_away_xg=float(fit.final_away_xg) if fit.final_away_xg is not None else final.get("away_xg"),
        final_total_xg=float(fit.final_total_xg) if fit.final_total_xg is not None else final.get("total_xg"),
        constraint_count=fit.constraint_count,
        max_constraint_error=(
            float(fit.max_constraint_error) if fit.max_constraint_error is not None else None
        ),
        constraint_details=diag.get("constraint_details"),
    )


@router.get("/matches/{match_id}/diagnostics", response_model=DiagnosticsOut)
async def get_match_diagnostics(
    match_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await _build_diagnostics(db, match_id, run_id)


@router.get("/model-runs/{run_id}/diagnostics/{match_id}", response_model=DiagnosticsOut)
async def get_run_match_diagnostics(
    run_id: uuid.UUID,
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await _build_diagnostics(db, match_id, run_id)
