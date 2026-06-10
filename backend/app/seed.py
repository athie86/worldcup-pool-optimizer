"""Seed script: python -m app.seed"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .db.session import AsyncSessionLocal
from .db import models
from .services.scoring import ScoringRule as SvcScoringRule
from .services.score_model import fit_score_model, MarketProbabilities
from .services.optimizer import compute_expected_points
from .services.odds_normalization import compute_consensus, BookmakerMarket, RawOutcome
from .core.logging import logger
from .core.defaults import DEFAULT_SCORING_RULES


SCORING_RULES_SEED = DEFAULT_SCORING_RULES

TEAMS_SEED = [
    {"fifa_code": "ESP", "name": "Spain", "short_name": "ESP", "flag_emoji": "🇪🇸", "group_label": "A"},
    {"fifa_code": "JPN", "name": "Japan", "short_name": "JPN", "flag_emoji": "🇯🇵", "group_label": "A"},
    {"fifa_code": "GER", "name": "Germany", "short_name": "GER", "flag_emoji": "🇩🇪", "group_label": "B"},
    {"fifa_code": "MEX", "name": "Mexico", "short_name": "MEX", "flag_emoji": "🇲🇽", "group_label": "B"},
    {"fifa_code": "ARG", "name": "Argentina", "short_name": "ARG", "flag_emoji": "🇦🇷", "group_label": "C"},
    {"fifa_code": "USA", "name": "USA", "short_name": "USA", "flag_emoji": "🇺🇸", "group_label": "C"},
    {"fifa_code": "BRA", "name": "Brazil", "short_name": "BRA", "flag_emoji": "🇧🇷", "group_label": "D"},
    {"fifa_code": "MAR", "name": "Morocco", "short_name": "MAR", "flag_emoji": "🇲🇦", "group_label": "D"},
]

# Sample odds data (Spain vs Japan as anchor, others generated)
SAMPLE_ODDS = [
    # (home_team, away_team, h2h_home_win, h2h_draw, h2h_away_win, over_2_5, under_2_5)
    ("Spain", "Japan", 1.50, 4.20, 7.00, 1.90, 1.90),
    ("Germany", "Mexico", 1.65, 3.80, 5.50, 1.75, 2.05),
    ("Argentina", "USA", 1.40, 4.50, 8.00, 2.10, 1.72),
    ("Brazil", "Morocco", 1.55, 4.00, 6.00, 1.85, 1.95),
    ("Spain", "Germany", 2.10, 3.50, 3.40, 1.70, 2.10),
    ("Japan", "Mexico", 2.80, 3.20, 2.60, 2.20, 1.65),
    ("Argentina", "Brazil", 2.30, 3.30, 3.00, 1.80, 2.00),
    ("USA", "Morocco", 2.00, 3.40, 3.80, 2.05, 1.78),
    # Knockout stubs
    ("Spain", "Argentina", 2.20, 3.40, 3.30, 1.75, 2.05),
    ("Brazil", "Germany", 2.40, 3.30, 2.90, 1.80, 2.00),
    ("Japan", "USA", 2.60, 3.20, 2.70, 2.15, 1.70),
    ("Mexico", "Morocco", 2.30, 3.40, 3.10, 2.00, 1.85),
]


def dt(year: int, month: int, day: int, hour: int = 15) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


MATCHES_SEED = [
    # Group stage
    (1, "group", "A", "Spain", "Japan", dt(2026, 6, 11), "SoFi Stadium", "Inglewood", "USA"),
    (2, "group", "B", "Germany", "Mexico", dt(2026, 6, 12), "AT&T Stadium", "Arlington", "USA"),
    (3, "group", "C", "Argentina", "USA", dt(2026, 6, 12), "MetLife Stadium", "East Rutherford", "USA"),
    (4, "group", "D", "Brazil", "Morocco", dt(2026, 6, 13), "Levi's Stadium", "Santa Clara", "USA"),
    (5, "group", "A", "Spain", "Germany", dt(2026, 6, 17), "Rose Bowl", "Pasadena", "USA"),
    (6, "group", "A", "Japan", "Mexico", dt(2026, 6, 18), "NRG Stadium", "Houston", "USA"),
    (7, "group", "C", "Argentina", "Brazil", dt(2026, 6, 19), "Azteca", "Mexico City", "Mexico"),
    (8, "group", "C", "USA", "Morocco", dt(2026, 6, 19), "Estadio BBVA", "Monterrey", "Mexico"),
    # Knockout
    (9, "round_of_16", None, "Spain", "Argentina", dt(2026, 6, 29), "SoFi Stadium", "Inglewood", "USA"),
    (10, "round_of_16", None, "Brazil", "Germany", dt(2026, 6, 30), "MetLife Stadium", "East Rutherford", "USA"),
    (11, "round_of_16", None, "Japan", "USA", dt(2026, 7, 1), "AT&T Stadium", "Arlington", "USA"),
    (12, "round_of_16", None, "Mexico", "Morocco", dt(2026, 7, 2), "Azteca", "Mexico City", "Mexico"),
]


async def seed():
    async with AsyncSessionLocal() as db:
        # 1. Teams
        team_map: dict[str, models.Team] = {}
        for t in TEAMS_SEED:
            result = await db.execute(select(models.Team).where(models.Team.name == t["name"]))
            existing = result.scalar_one_or_none()
            if not existing:
                team = models.Team(**t)
                db.add(team)
                await db.flush()
                team_map[t["name"]] = team
                print(f"Created team: {t['name']}")
            else:
                team_map[t["name"]] = existing

        await db.flush()

        # 3. Pool config + scoring rules
        pc_result = await db.execute(
            select(models.PoolConfig).where(models.PoolConfig.name == "World Cup 2026")
        )
        pool_config = pc_result.scalar_one_or_none()
        if not pool_config:
            pool_config = models.PoolConfig(
                name="World Cup 2026",
                description="Default pool configuration for FIFA World Cup 2026",
                default_top_n=3,
                candidate_max_goals=5,
                ranking_metric="expected_points",
                margin_removal_method="proportional",
                active=True,
            )
            db.add(pool_config)
            await db.flush()
            print(f"Created pool config: {pool_config.name}")

            for rule_data in SCORING_RULES_SEED:
                rule = models.ScoringRule(pool_config_id=pool_config.id, **rule_data)
                db.add(rule)
            print("Created scoring rules")

        await db.flush()

        # 4. Matches
        match_map: dict[int, models.Match] = {}
        for (num, stage, group, home_name, away_name, kickoff, venue, city, country) in MATCHES_SEED:
            result = await db.execute(
                select(models.Match).where(models.Match.match_number == num)
            )
            existing = result.scalar_one_or_none()
            if not existing:
                home_team = team_map.get(home_name)
                away_team = team_map.get(away_name)
                match = models.Match(
                    match_number=num,
                    stage=stage,
                    group_label=group,
                    home_team_id=home_team.id if home_team else None,
                    away_team_id=away_team.id if away_team else None,
                    kickoff_at=kickoff,
                    venue=venue,
                    city=city,
                    country=country,
                    status="scheduled",
                    is_complete_for_optimization=True,
                )
                db.add(match)
                await db.flush()
                match_map[num] = match
                print(f"Created match #{num}: {home_name} vs {away_name}")
            else:
                match_map[num] = existing

        await db.flush()

        # 5. Sample odds snapshot (group stage only)
        snap_result = await db.execute(
            select(models.OddsSnapshot).where(models.OddsSnapshot.provider == "seed_data")
        )
        existing_snap = snap_result.scalar_one_or_none()
        if not existing_snap:
            snapshot = models.OddsSnapshot(
                provider="seed_data",
                requested_markets=["h2h", "totals"],
                requested_regions=["eu"],
                requested_bookmakers=[],
                fetched_at=datetime.now(timezone.utc),
                status="success",
                request_url="seed://local",
                raw_response={"source": "seed"},
            )
            db.add(snapshot)
            await db.flush()
            print("Created odds snapshot")

            bookmakers = [
                ("bet365", "Bet365"),
                ("pinnacle", "Pinnacle"),
                ("betfair", "Betfair"),
            ]

            for i, (home_name, away_name, hw, d, aw, o25, u25) in enumerate(SAMPLE_ODDS, 1):
                match = match_map.get(i)
                if not match:
                    continue

                odds_event = models.OddsEvent(
                    odds_snapshot_id=snapshot.id,
                    match_id=match.id,
                    provider_event_id=f"seed_{i:03d}",
                    sport_key="soccer_fifa_world_cup",
                    home_team=home_name,
                    away_team=away_name,
                    commence_time=match.kickoff_at,
                )
                db.add(odds_event)
                await db.flush()

                for bk_key, bk_title in bookmakers:
                    # H2H market
                    bm_h2h = models.BookmakerMarket(
                        odds_event_id=odds_event.id,
                        bookmaker_key=bk_key,
                        bookmaker_title=bk_title,
                        market_key="h2h",
                        last_update=datetime.now(timezone.utc),
                        line=None,
                    )
                    db.add(bm_h2h)
                    await db.flush()

                    # Add small random spread per bookmaker
                    import random
                    spread = random.uniform(-0.05, 0.05)
                    for outcome_type, price in [
                        ("home_win", hw + spread),
                        ("draw", d + spread),
                        ("away_win", aw + spread),
                    ]:
                        price = max(1.01, price)
                        implied = 1.0 / price
                        mo = models.MarketOutcome(
                            bookmaker_market_id=bm_h2h.id,
                            outcome_name=outcome_type,
                            outcome_type=outcome_type,
                            price_decimal=price,
                            implied_probability=implied,
                        )
                        db.add(mo)

                    # Totals 2.5
                    bm_tot = models.BookmakerMarket(
                        odds_event_id=odds_event.id,
                        bookmaker_key=bk_key,
                        bookmaker_title=bk_title,
                        market_key="totals",
                        last_update=datetime.now(timezone.utc),
                        line=2.5,
                    )
                    db.add(bm_tot)
                    await db.flush()

                    for outcome_type, price in [("over", o25), ("under", u25)]:
                        price = max(1.01, price)
                        implied = 1.0 / price
                        mo = models.MarketOutcome(
                            bookmaker_market_id=bm_tot.id,
                            outcome_name=outcome_type,
                            outcome_type=outcome_type,
                            price_decimal=price,
                            implied_probability=implied,
                        )
                        db.add(mo)

            await db.flush()

            # 6. Manual override for Spain vs Japan (match #1)
            spain_japan = match_map.get(1)
            if spain_japan:
                ov = models.ManualOddsOverride(
                    match_id=spain_japan.id,
                    market_key="h2h",
                    line=None,
                    outcome_type="home_win",
                    price_decimal=1.45,
                    enabled=True,
                    reason="Manual adjustment based on injury news",
                )
                db.add(ov)
                print("Created manual override for Spain vs Japan")

            await db.commit()
            print("Seed data committed")

        # 7. Run optimizer
        print("\nRunning optimizer...")

        # Reload pool config with rules
        pc_result = await db.execute(
            select(models.PoolConfig)
            .options(selectinload(models.PoolConfig.scoring_rules))
            .where(models.PoolConfig.name == "World Cup 2026")
        )
        pool_config = pc_result.scalar_one_or_none()

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

        # Get the snapshot
        snap_result = await db.execute(
            select(models.OddsSnapshot).where(models.OddsSnapshot.provider == "seed_data")
        )
        snapshot = snap_result.scalar_one_or_none()

        # Get matches
        match_result = await db.execute(
            select(models.Match)
            .options(
                selectinload(models.Match.manual_overrides),
            )
            .where(models.Match.is_complete_for_optimization == True)
        )
        matches_to_run = match_result.scalars().all()

        run = models.ModelRun(
            pool_config_id=pool_config.id,
            odds_snapshot_id=snapshot.id if snapshot else None,
            run_type="seed",
            status="running",
            parameters={"candidate_max_goals": pool_config.candidate_max_goals},
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        processed = 0
        for match in matches_to_run:
            # Build market probs from odds events
            q = (
                select(models.OddsEvent)
                .options(
                    selectinload(models.OddsEvent.bookmaker_markets).selectinload(
                        models.BookmakerMarket.market_outcomes
                    )
                )
                .where(
                    models.OddsEvent.match_id == match.id,
                )
            )
            if snapshot:
                q = q.where(models.OddsEvent.odds_snapshot_id == snapshot.id)

            ev_result = await db.execute(q)
            events = ev_result.scalars().all()

            bk_markets = []
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
                        )
                    )

            overrides = [
                RawOutcome(
                    outcome_type=ov.outcome_type,
                    price_decimal=float(ov.price_decimal),
                    line=float(ov.line) if ov.line else None,
                )
                for ov in match.manual_overrides
                if ov.enabled
            ]

            market_probs = compute_consensus(bk_markets, overrides if overrides else None)

            if market_probs.home_win is None:
                print(f"  Match #{match.match_number}: no odds, skipping")
                continue

            fit = fit_score_model(market_probs)

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

            recs = compute_expected_points(
                fit,
                rules,
                pool_config.candidate_max_goals,
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

            processed += 1
            print(f"  Fit match #{match.match_number}: λH={fit.lambda_home:.3f} λA={fit.lambda_away:.3f} status={fit.fit_status}")

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        print(f"\nOptimizer run complete: {processed} matches processed")
        print(f"Model run ID: {run.id}")


if __name__ == "__main__":
    asyncio.run(seed())
