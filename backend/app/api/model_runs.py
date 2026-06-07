from __future__ import annotations
import uuid
from datetime import datetime
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
from ..services.score_model import fit_score_model, MarketProbabilities
from ..services.optimizer import compute_expected_points
from ..services.odds_normalization import compute_consensus, BookmakerMarket, RawOutcome
from ..core.logging import logger
from .deps import get_current_user

router = APIRouter()


async def _build_market_probs(
    db: AsyncSession,
    match: models.Match,
    odds_snapshot_id: Optional[uuid.UUID],
) -> MarketProbabilities:
    """Build MarketProbabilities from latest odds for a match."""
    # Get odds events for this match
    q = (
        select(models.OddsEvent)
        .options(
            selectinload(models.OddsEvent.bookmaker_markets).selectinload(
                models.BookmakerMarket.market_outcomes
            )
        )
        .where(models.OddsEvent.match_id == match.id)
    )
    if odds_snapshot_id:
        q = q.where(models.OddsEvent.odds_snapshot_id == odds_snapshot_id)
    else:
        # Use most recent snapshot
        q = q.order_by(models.OddsEvent.created_at.desc())

    result = await db.execute(q)
    events = result.scalars().all()

    # Build bookmaker markets list
    bk_markets: list[BookmakerMarket] = []
    for evt in events:
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

    # Get manual overrides
    ov_result = await db.execute(
        select(models.ManualOddsOverride).where(
            models.ManualOddsOverride.match_id == match.id,
            models.ManualOddsOverride.enabled == True,
        )
    )
    overrides_db = ov_result.scalars().all()
    overrides = [
        RawOutcome(
            outcome_type=ov.outcome_type,
            price_decimal=float(ov.price_decimal),
            line=float(ov.line) if ov.line else None,
        )
        for ov in overrides_db
    ]

    return compute_consensus(bk_markets, overrides if overrides else None)


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

    # Build scoring rules
    rules = [
        SvcScoringRule(
            code=r.code,
            label=r.label,
            points=float(r.points),
            enabled=r.enabled,
            display_specificity_rank=r.display_specificity_rank,
        )
        for r in pool_config.scoring_rules
    ]

    # Create model run
    run = models.ModelRun(
        pool_config_id=body.pool_config_id,
        odds_snapshot_id=body.odds_snapshot_id,
        run_type=body.run_type,
        status="running",
        parameters=body.parameters or {},
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.flush()

    # Get matches to optimize
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
        run.completed_at = datetime.utcnow()
        run.error_message = "No matches marked complete_for_optimization"
        await db.commit()
        return run

    candidate_max = pool_config.candidate_max_goals

    errors = []
    skipped_no_odds = 0
    for match in matches:
        try:
            market_probs = await _build_market_probs(db, match, body.odds_snapshot_id)

            # Without at least a 1X2 market there is nothing to fit. Skip the
            # match rather than attempting a fit on empty inputs (which only
            # produces a confusing failure).
            if market_probs.home_win is None:
                skipped_no_odds += 1
                continue

            fit = fit_score_model(market_probs)

            # Store model fit
            model_fit = models.MatchModelFit(
                model_run_id=run.id,
                match_id=match.id,
                lambda_home=fit.lambda_home,
                lambda_away=fit.lambda_away,
                fitted_home_win_prob=fit.fitted_home_win,
                fitted_draw_prob=fit.fitted_draw,
                fitted_away_win_prob=fit.fitted_away_win,
                market_home_win_prob=market_probs.home_win,
                market_draw_prob=market_probs.draw,
                market_away_win_prob=market_probs.away_win,
                fit_error=fit.loss,
                fit_status=fit.fit_status,
                diagnostics=fit.diagnostics,
                score_matrix=fit.score_matrix.tolist(),
            )
            db.add(model_fit)
            await db.flush()

            # Compute recommendations
            recs = compute_expected_points(
                fit,
                rules,
                candidate_max,
                scoring_mode=pool_config.scoring_mode,
                binary_result_points=float(pool_config.binary_result_points),
                binary_total_goals_points=float(pool_config.binary_total_goals_points),
            )
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
                )
                db.add(sr)

        except Exception as exc:
            logger.error("model_run: match failed", match_id=str(match.id), error=str(exc))
            errors.append(str(exc))

    run.status = "completed" if not errors else "partial"
    run.completed_at = datetime.utcnow()
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
        grouped.append(
            MatchRecommendationOut(
                match_id=fit.match_id,
                home_team=home,
                away_team=away,
                kickoff_at=match.kickoff_at if match else None,
                lambda_home=float(fit.lambda_home) if fit.lambda_home is not None else None,
                lambda_away=float(fit.lambda_away) if fit.lambda_away is not None else None,
                fit_status=fit.fit_status,
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
        prior_matrix=diag.get("prior_matrix"),
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
