# tests/unit/shared/test_labelling.py
"""
Unit tests for labelling utilities.

Tests cover:
- Strategy label generation
- Closing label generation
- Label parsing for both legacy and new formats
- Edge cases and invalid inputs
"""

import time
import uuid

import pytest

from trading_shared.utils.labelling import (
    generate_closing_label,
    generate_strategy_label,
    parse_label,
)


class TestGenerateStrategyLabel:
    """Tests for generate_strategy_label function."""

    def test_generates_label_without_cycle_id(self):
        # Arrange
        strategy = "hedgingSpot"
        state = "open"

        # Act
        label = generate_strategy_label(strategy, state)

        # Assert
        parts = label.split("-")
        assert len(parts) == 3
        assert parts[0] == strategy
        assert parts[1] == state
        assert parts[2].isdigit()

    def test_generates_label_with_cycle_id(self):
        # Arrange
        strategy = "hedgingSpot"
        state = "open"
        cycle_id = uuid.uuid4()

        # Act
        label = generate_strategy_label(strategy, state, cycle_id)

        # Assert
        parts = label.split("-")
        assert len(parts) == 4
        assert parts[0] == strategy
        assert parts[1] == state
        assert parts[2].isdigit()
        assert parts[3] == str(cycle_id)

    def test_timestamp_is_current(self):
        # Arrange
        strategy = "test"
        state = "open"
        before_time = int(time.time() * 1000)

        # Act
        label = generate_strategy_label(strategy, state)

        # Assert
        after_time = int(time.time() * 1000)
        parts = label.split("-")
        timestamp = int(parts[2])
        assert before_time <= timestamp <= after_time

    def test_different_calls_generate_different_timestamps(self):
        # Arrange
        strategy = "test"
        state = "open"

        # Act
        label1 = generate_strategy_label(strategy, state)
        time.sleep(0.01)  # Small delay to ensure different timestamp
        label2 = generate_strategy_label(strategy, state)

        # Assert
        assert label1 != label2


class TestGenerateClosingLabel:
    """Tests for generate_closing_label function."""

    def test_converts_open_to_closed_without_cycle_id(self):
        # Arrange
        opening_label = "hedgingSpot-open-1234567890"

        # Act
        closing_label = generate_closing_label(opening_label)

        # Assert
        assert closing_label == "hedgingSpot-closed-1234567890"

    def test_converts_open_to_closed_with_cycle_id(self):
        # Arrange
        cycle_id = str(uuid.uuid4())
        opening_label = f"hedgingSpot-open-1234567890-{cycle_id}"

        # Act
        closing_label = generate_closing_label(opening_label)

        # Assert
        assert closing_label == f"hedgingSpot-closed-1234567890-{cycle_id}"

    def test_returns_none_for_non_open_label(self):
        # Arrange
        label = "hedgingSpot-closed-1234567890"

        # Act
        result = generate_closing_label(label)

        # Assert
        assert result is None

    def test_returns_none_for_invalid_format(self):
        # Arrange
        label = "invalid-label"

        # Act
        result = generate_closing_label(label)

        # Assert
        assert result is None

    def test_returns_none_for_empty_string(self):
        # Arrange
        label = ""

        # Act
        result = generate_closing_label(label)

        # Assert
        assert result is None

    def test_preserves_all_parts_except_state(self):
        # Arrange
        opening_label = "strategy-open-9999999999-extra-parts"

        # Act
        closing_label = generate_closing_label(opening_label)

        # Assert
        # Should only change 'open' to 'closed', preserving extra parts
        assert closing_label == "strategy-closed-9999999999-extra-parts"


class TestParseLabel:
    """Tests for parse_label function."""

    def test_parses_legacy_format(self):
        # Arrange
        label = "hedgingSpot-open-1234567890"

        # Act
        result = parse_label(label)

        # Assert
        assert result == ("hedgingSpot", "open", "1234567890", None)

    def test_parses_new_format_with_cycle_id(self):
        # Arrange
        cycle_id = str(uuid.uuid4())
        label = f"hedgingSpot-open-1234567890-{cycle_id}"

        # Act
        result = parse_label(label)

        # Assert
        assert result == ("hedgingSpot", "open", "1234567890", cycle_id)

    def test_returns_none_for_invalid_format(self):
        # Arrange
        label = "invalid"

        # Act
        result = parse_label(label)

        # Assert
        assert result is None

    def test_returns_none_for_two_part_label(self):
        # Arrange
        label = "strategy-state"

        # Act
        result = parse_label(label)

        # Assert
        assert result is None

    def test_returns_none_for_empty_string(self):
        # Arrange
        label = ""

        # Act
        result = parse_label(label)

        # Assert
        assert result is None

    def test_returns_none_for_none_input(self):
        # Arrange
        label = None

        # Act
        result = parse_label(label)

        # Assert
        assert result is None

    def test_parses_closed_state(self):
        # Arrange
        label = "strategy-closed-1234567890"

        # Act
        result = parse_label(label)

        # Assert
        assert result == ("strategy", "closed", "1234567890", None)

    def test_handles_five_part_label(self):
        # Arrange - More than 4 parts should return None
        label = "strategy-state-timestamp-cycle-extra"

        # Act
        result = parse_label(label)

        # Assert
        assert result is None

    def test_extracts_all_components_correctly(self):
        # Arrange
        strategy = "arbitrage"
        state = "pending"
        timestamp = "9876543210"
        cycle_id = str(uuid.uuid4())
        label = f"{strategy}-{state}-{timestamp}-{cycle_id}"

        # Act
        result = parse_label(label)

        # Assert
        assert result[0] == strategy
        assert result[1] == state
        assert result[2] == timestamp
        assert result[3] == cycle_id
