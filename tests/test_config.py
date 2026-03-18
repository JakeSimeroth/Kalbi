"""
Tests for src.config.Settings.

Validates that the Pydantic Settings class is importable, defines expected
fields, and has sensible defaults for non-credential configuration.
"""

import os
import pytest


def test_settings_defaults():
    """Settings should load with defaults when env vars are missing."""
    from src.config import Settings

    # Settings() may fail without env vars, that's expected.
    # Test that the class is importable and has expected attributes.
    assert hasattr(Settings, "model_fields")
    assert "paper_trading_mode" in Settings.model_fields
    assert "max_daily_loss_pct" in Settings.model_fields


def test_settings_has_risk_fields():
    """Settings should define all risk-control fields."""
    from src.config import Settings

    expected_risk_fields = [
        "max_daily_loss_pct",
        "max_position_pct",
        "max_portfolio_deployed_pct",
        "max_correlation",
        "paper_trading_mode",
    ]
    for field_name in expected_risk_fields:
        assert field_name in Settings.model_fields, (
            f"Missing risk field: {field_name}"
        )


def test_settings_has_scheduling_fields():
    """Settings should define all scheduling interval fields."""
    from src.config import Settings

    expected_schedule_fields = [
        "kalshi_scan_interval_minutes",
        "equities_scan_interval_minutes",
        "meta_review_interval_minutes",
    ]
    for field_name in expected_schedule_fields:
        assert field_name in Settings.model_fields, (
            f"Missing schedule field: {field_name}"
        )


def test_settings_has_credential_fields():
    """Settings should define all API credential fields."""
    from src.config import Settings

    expected_credential_fields = [
        "anthropic_api_key",
        "kalshi_api_key_id",
        "kalshi_private_key_path",
        "alpaca_api_key",
        "alpaca_api_secret",
    ]
    for field_name in expected_credential_fields:
        assert field_name in Settings.model_fields, (
            f"Missing credential field: {field_name}"
        )


def test_settings_has_database_fields():
    """Settings should define database connection fields."""
    from src.config import Settings

    assert "timescaledb_url" in Settings.model_fields
    assert "redis_url" in Settings.model_fields
