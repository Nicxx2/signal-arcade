from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import PaperOrder, Side
from signal_arcade.paper.curve_math import quote_buy
from test_broker import make_broker, make_features
from test_learning import make_decision, make_state, policy_episode_for


@pytest.mark.parametrize(
    "observed,components,expected",
    [
        (0, (0, 0, 0), 0),
        (0, None, 125),
        (75, (25, 25, 25), 75),
        (75, None, 75),
    ],
)
def test_learning_and_execution_share_fee_assumptions(settings, observed, components, expected):
    database = Database(settings.database_path)
    now = datetime.now(UTC)
    state = make_state("fees")
    state.fee_bps = observed
    state.reserve_fee_components = components
    state.last_event_at = state.last_reserve_at = now
    try:
        learner = LearningEngine(database, settings)
        decision = make_decision(now, state.mint)
        assert learner.register(decision, state, live=True, evaluation_actionable=True)
        observation = learner.observations[state.mint]
        policy = policy_episode_for(learner, state.mint)
        assert observation.fee_bps == policy.fee_bps == expected
        network = settings.network_fee_lamports + settings.priority_fee_lamports
        for trial in observation.size_trials.values():
            assert trial.entry_cost_lamports
            quote = quote_buy(
                virtual_token_reserves=state.virtual_token_reserves,
                virtual_sol_reserves=state.virtual_quote_reserves,
                real_token_reserves=state.real_token_reserves,
                wallet_trade_budget_lamports=trial.budget_lamports,
                fee_bps=expected,
                network_fee_lamports=network,
            )
            assert trial.token_units == quote.token_units
        broker = make_broker(database, settings)
        for side in (Side.BUY, Side.SELL):
            order = PaperOrder(
                order_id=f"fee-{side}",
                decision_id=decision.decision_id,
                mint=state.mint,
                symbol=state.symbol,
                side=side,
                created_at=now,
                fill_after=now,
                requested_sol_lamports=int(decision.planned_order_size_sol * 1_000_000_000),
            )
            database.save_order(order)
            broker.pending[order.order_id] = order
            receipt = broker._fill(
                order,
                state,
                make_features(now, state.mint),
                f"event-{side}",
                now + timedelta(milliseconds=1),
                None,
            )
            assert receipt is not None
            assert f"protocol_fee_bps={expected}" in receipt.assumptions
            source = (
                "observed_event" if components is not None or observed else "configured_fallback"
            )
            assert f"fee_source={source}" in receipt.assumptions
            if side == Side.BUY:
                assert receipt.token_units == observation.token_units
        # Persisted observations retain their original assumptions across restart.
        assert database.recent_learning_observations(1)[0].fee_bps == expected
    finally:
        database.close()
