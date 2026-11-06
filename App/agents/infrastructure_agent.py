"""Agent entry point for infrastructure site-health polling.

The infrastructure workflow and its business rules remain in the existing
service layer. This agent is a small orchestration facade so callers can use
the same agent-oriented interface as Identity and Patch without duplicating
or changing the established infrastructure behavior.
"""

from __future__ import annotations

from typing import Any

from App.services.infrastructure.processor import process_infrastructure_sites


class InfrastructureAgent:
    """Delegate infrastructure poll requests to the existing processor."""

    @staticmethod
    def execute(*, trigger_type: str = "manual") -> dict[str, Any]:
        """Run one infrastructure poll using the existing service workflow."""
        return process_infrastructure_sites(trigger_type=trigger_type)