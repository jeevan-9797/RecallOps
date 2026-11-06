"""
RecallOps Agent Tool Dispatcher and Concrete Handlers.
Implements the 6 tool contracts using Database and Hindsight backends:
1. recall_similar_incidents (Hindsight)
2. recall_failed_fixes (Hindsight)
3. get_recent_deploys (PostgreSQL)
4. get_logs (PostgreSQL)
5. get_service_owner (PostgreSQL)
6. post_to_band_room (Band Adapter)
"""

import logging
from typing import Any, Dict, Optional
from pydantic import ValidationError

from backend.app.db.repository import DatabaseRepositoryInterface
from backend.app.schemas.agent_tools import (
    GetLogsInput,
    GetRecentDeploysInput,
    GetServiceOwnerInput,
    PostToBandRoomInput,
    RecallFailedFixesInput,
    RecallSimilarIncidentsInput,
)
from backend.app.services.band_adapter import BandAdapterInterface, band_adapter
from backend.app.services.hindsight_service import HindsightService, hindsight_service

logger = logging.getLogger("recallops.tools")


class AgentToolDispatcher:
    """Dispatches tool calls requested by Groq models to concrete backend services."""

    def __init__(
        self,
        db_repo: DatabaseRepositoryInterface,
        hindsight: Optional[HindsightService] = None,
        band: Optional[BandAdapterInterface] = None,
    ):
        self.db_repo = db_repo
        self.hindsight = hindsight or hindsight_service
        self.band = band or band_adapter

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        memory_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Validates arguments against the AI/ML Pydantic schema and invokes the backing service.
        Returns a structured result dict or an error dict if validation fails.
        """
        try:
            if tool_name == "recall_similar_incidents":
                if not memory_enabled:
                    return {
                        "tool": tool_name,
                        "status": "disabled",
                        "count": 0,
                        "similar_incidents": [],
                        "error": "Hindsight memory is disabled by query parameter (?memory=off)",
                    }
                parsed = RecallSimilarIncidentsInput.model_validate(arguments)
                try:
                    memories = await self.hindsight.recall_similar(
                        service_name=parsed.service_name,
                        symptom=parsed.symptom,
                        limit=parsed.limit,
                    )
                    return {
                        "tool": tool_name,
                        "service_name": parsed.service_name,
                        "count": len(memories),
                        "similar_incidents": memories,
                        "status": "success",
                    }
                except Exception as e:
                    logger.error(f"Hindsight recall_similar error: {e}")
                    return {
                        "tool": tool_name,
                        "status": "unavailable",
                        "count": 0,
                        "similar_incidents": [],
                        "error": f"Hindsight memory service unavailable: {str(e)}",
                    }

            elif tool_name == "recall_failed_fixes":
                if not memory_enabled:
                    return {
                        "tool": tool_name,
                        "status": "disabled",
                        "count": 0,
                        "failed_fixes": [],
                        "error": "Hindsight memory is disabled by query parameter (?memory=off)",
                    }
                parsed = RecallFailedFixesInput.model_validate(arguments)
                try:
                    failed_fixes = await self.hindsight.recall_failed_fixes(
                        service_name=parsed.service_name,
                        incident_signature=parsed.incident_signature,
                    )
                    return {
                        "tool": tool_name,
                        "service_name": parsed.service_name,
                        "count": len(failed_fixes),
                        "failed_fixes": failed_fixes,
                        "status": "success",
                    }
                except Exception as e:
                    logger.error(f"Hindsight recall_failed_fixes error: {e}")
                    return {
                        "tool": tool_name,
                        "status": "unavailable",
                        "count": 0,
                        "failed_fixes": [],
                        "error": f"Hindsight memory service unavailable: {str(e)}",
                    }

            elif tool_name == "get_recent_deploys":
                parsed = GetRecentDeploysInput.model_validate(arguments)
                try:
                    deploys = await self.db_repo.get_recent_deploys(
                        service_name=parsed.service_name,
                        lookback_hours=parsed.lookback_hours,
                    )
                    return {
                        "tool": tool_name,
                        "service_name": parsed.service_name,
                        "lookback_hours": parsed.lookback_hours,
                        "count": len(deploys),
                        "deploys": deploys,
                        "status": "success",
                    }
                except Exception as e:
                    logger.error(f"Database error in get_recent_deploys: {e}")
                    return {
                        "tool": tool_name,
                        "status": "database_error",
                        "error": f"Database query failed: {type(e).__name__}: {str(e)}",
                    }

            elif tool_name == "get_logs":
                parsed = GetLogsInput.model_validate(arguments)
                try:
                    logs = await self.db_repo.get_logs(
                        service_name=parsed.service_name,
                        incident_id=parsed.incident_id,
                        limit=parsed.limit,
                    )
                    return {
                        "tool": tool_name,
                        "service_name": parsed.service_name,
                        "incident_id": parsed.incident_id,
                        "count": len(logs),
                        "logs": logs,
                        "status": "success",
                    }
                except Exception as e:
                    logger.error(f"Database error in get_logs: {e}")
                    return {
                        "tool": tool_name,
                        "status": "database_error",
                        "error": f"Database query failed: {type(e).__name__}: {str(e)}",
                    }

            elif tool_name == "get_service_owner":
                parsed = GetServiceOwnerInput.model_validate(arguments)
                try:
                    owner = await self.db_repo.get_service_owner(service_name=parsed.service_name)
                    return {
                        "tool": tool_name,
                        "service_name": parsed.service_name,
                        "owner": owner or f"{parsed.service_name}-squad",
                        "status": "success",
                    }
                except Exception as e:
                    logger.error(f"Database error in get_service_owner: {e}")
                    return {
                        "tool": tool_name,
                        "status": "database_error",
                        "error": f"Database query failed: {type(e).__name__}: {str(e)}",
                    }

            elif tool_name == "post_to_band_room":
                parsed = PostToBandRoomInput.model_validate(arguments)
                try:
                    posted = await self.band.post_incident_update(
                        incident_id=parsed.incident_id,
                        message=parsed.message,
                        sender=parsed.sender,
                    )
                    from backend.app.services.band_adapter import MockBandAdapter
                    is_mock = isinstance(self.band, MockBandAdapter)
                    return {
                        "tool": tool_name,
                        "incident_id": parsed.incident_id,
                        "delivered": posted,
                        "status": "delivered_to_mock_adapter" if is_mock else "delivered",
                        "adapter": type(self.band).__name__,
                        "sender": parsed.sender,
                    }
                except Exception as e:
                    logger.warning(f"Band communication failure (non-fatal): {e}")
                    return {
                        "tool": tool_name,
                        "incident_id": parsed.incident_id,
                        "delivered": False,
                        "non_fatal": True,
                        "error": f"Band communication failure: {str(e)}",
                    }

            else:
                return {
                    "tool": tool_name,
                    "error": f"Unknown tool '{tool_name}'. Available tools: recall_similar_incidents, recall_failed_fixes, get_recent_deploys, get_logs, get_service_owner, post_to_band_room",
                }

        except ValidationError as e:
            logger.warning(f"Tool argument validation failed for '{tool_name}': {e}")
            return {
                "tool": tool_name,
                "status": "validation_error",
                "error": "Validation error in arguments. Please correct and retry.",
                "details": e.errors(),
            }
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return {
                "tool": tool_name,
                "error": f"Tool execution failed: {type(e).__name__}: {str(e)}",
            }
