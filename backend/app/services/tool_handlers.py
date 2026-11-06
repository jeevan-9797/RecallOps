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

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates arguments against the AI/ML Pydantic schema and invokes the backing service.
        Returns a structured result dict or an error dict if validation fails.
        """
        try:
            if tool_name == "recall_similar_incidents":
                parsed = RecallSimilarIncidentsInput.model_validate(arguments)
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
                }

            elif tool_name == "recall_failed_fixes":
                parsed = RecallFailedFixesInput.model_validate(arguments)
                failed_fixes = await self.hindsight.recall_failed_fixes(
                    service_name=parsed.service_name,
                    incident_signature=parsed.incident_signature,
                )
                return {
                    "tool": tool_name,
                    "service_name": parsed.service_name,
                    "count": len(failed_fixes),
                    "failed_fixes": failed_fixes,
                }

            elif tool_name == "get_recent_deploys":
                parsed = GetRecentDeploysInput.model_validate(arguments)
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
                }

            elif tool_name == "get_logs":
                parsed = GetLogsInput.model_validate(arguments)
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
                }

            elif tool_name == "get_service_owner":
                parsed = GetServiceOwnerInput.model_validate(arguments)
                owner = await self.db_repo.get_service_owner(service_name=parsed.service_name)
                return {
                    "tool": tool_name,
                    "service_name": parsed.service_name,
                    "owner": owner or f"{parsed.service_name}-squad",
                }

            elif tool_name == "post_to_band_room":
                parsed = PostToBandRoomInput.model_validate(arguments)
                posted = await self.band.post_incident_update(
                    incident_id=parsed.incident_id,
                    message=parsed.message,
                    sender=parsed.sender,
                )
                return {
                    "tool": tool_name,
                    "incident_id": parsed.incident_id,
                    "delivered": posted,
                    "sender": parsed.sender,
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
                "error": "Validation error in arguments",
                "details": e.errors(),
            }
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return {
                "tool": tool_name,
                "error": f"Tool execution failed: {type(e).__name__}: {str(e)}",
            }
