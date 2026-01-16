# tests/trading_shared/utils/test_labelling.py

import time
import uuid

from trading_shared.utils.labelling import (
    generate_closing_label,
    generate_strategy_label,
    parse_label,
)


class TestGenerateStrategyLabel:
    """Tests for generate_strategy_label function."""

    def test_generates_label_without_cycle_id(self):
        strategy = "hedgingSpot"
        state = "open"
        label = generate_strategy_label(strategy, state)
        parts = label.split("-")
        assert len(parts) == 3
        assert parts[0] == strategy
        assert parts[1] == state
        assert parts[2].isdigit()

    def test_generates_label_with_cycle_id(self):
        strategy = "hedgingSpot"
        state = "open"
        cycle_id = uuid.uuid4()
        label = generate_strategy_label(strategy, state, cycle_id)
        parts = label.split("-")
        assert len(parts) == 4
        assert parts[0] == strategy
        assert parts[1] == state
        assert parts[2].isdigit()
        assert parts[3] == str(cycle_id)

    def test_timestamp_is_current(self):
        strategy = "test"
        state = "open"
        before_time = int(time.time() * 1000)
        label = generate_strategy_label(strategy, state)
        after_time = int(time.time() * 1000)
        parts = label.split("-")
        timestamp = int(parts[2])
        assert before_time <= timestamp <= after_time

    def test_different_calls_generate_different_timestamps(self):
        strategy = "test"
        state = "open"
        label1 = generate_strategy_label(strategy, state)
        time.sleep(0.01)
        label2 = generate_strategy_label(strategy, state)
        assert label1 != label2


class TestGenerateClosingLabel:
    """Tests for generate_closing_label function."""

    def test_converts_open_to_closed_without_cycle_id(self):
        opening_label = "hedgingSpot-open-1234567890"
        closing_label = generate_closing_label(opening_label)
        assert closing_label == "hedgingSpot-closed-1234567890"

    def test_converts_open_to_closed_with_cycle_id(self):
        cycle_id = str(uuid.uuid4())
        opening_label = f"hedgingSpot-open-1234567890-{cycle_id}"
        closing_label = generate_closing_label(opening_label)
        assert closing_label == f"hedgingSpot-closed-1234567890-{cycle_id}"

    def test_returns_none_for_non_open_label(self):
        label = "hedgingSpot-closed-1234567890"
        result = generate_closing_label(label)
        assert result is None

    def test_returns_none_for_invalid_format(self):
        label = "invalid-label"
        result = generate_closing_label(label)
        assert result is None

    def test_returns_none_for_empty_string(self):
        label = ""
        result = generate_closing_label(label)
        assert result is None

    def test_preserves_all_parts_except_state(self):
        opening_label = "strategy-open-9999999999-extra-parts"
        closing_label = generate_closing_label(opening_label)
        assert closing_label == "strategy-closed-9999999999-extra-parts"


class TestParseLabel:
    """Tests for parse_label function."""

    def test_parses_legacy_format(self):
        label = "hedgingSpot-open-1234567890"
        result = parse_label(label)
        assert result == ("hedgingSpot", "open", "1234567890", None)

    def test_parses_new_format_with_cycle_id(self):
        cycle_id = str(uuid.uuid4())
        label = f"hedgingSpot-open-1234567890-{cycle_id}"
        result = parse_label(label)
        assert result == ("hedgingSpot", "open", "1234567890", cycle_id)

    def test_returns_none_for_invalid_format(self):
        label = "invalid"
        result = parse_label(label)
        assert result is None

    def test_returns_none_for_two_part_label(self):
        label = "strategy-state"
        result = parse_label(label)
        assert result is None

    def test_returns_none_for_empty_string(self):
        label = ""
        result = parse_label(label)
        assert result is None

    def test_returns_none_for_none_input(self):
        label = None
        result = parse_label(label)
        assert result is None

    def test_parses_closed_state(self):
        label = "strategy-closed-1234567890"
        result = parse_label(label)
        assert result == ("strategy", "closed", "1234567890", None)

    def test_handles_five_part_label(self):
        label = "strategy-state-timestamp-cycle-extra"
        result = parse_label(label)
        assert result is None

    def test_extracts_all_components_correctly(self):
        strategy = "arbitrage"
        state = "pending"
        timestamp = "9876543210"
        cycle_id = str(uuid.uuid4())
        label = f"{strategy}-{state}-{timestamp}-{cycle_id}"
        result = parse_label(label)
        assert result[0] == strategy
        assert result[1] == state
        assert result[2] == timestamp
        assert result[3] == cycle_id
