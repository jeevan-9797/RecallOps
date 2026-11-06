"""
Band Multi-Agent Communication Adapter Interface and Local Mock Implementation.
Approved Decision: Provides an adapter abstraction so backend is never blocked waiting
for the Research Lead to confirm real Band desktop/cloud protocol specs.
"""

import abc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("recallops.band")


class BandAdapterInterface(abc.ABC):
    """Abstract interface for broadcasting triage updates to Band incident rooms."""

    @abc.abstractmethod
    async def post_incident_update(
        self,
        incident_id: str,
        message: str,
        sender: str = "Triage Agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Broadcasts an operational message to the specified incident room.
        Returns True on delivery success, False otherwise.
        """
        pass


class MockBandAdapter(BandAdapterInterface):
    """
    Local development and offline mock adapter.
    Logs incident updates to stdout/logging without making external network calls
    or inventing arbitrary endpoints.
    """

    def __init__(self, room_prefix: str = "kartly-war-room"):
        self.room_prefix = room_prefix
        self.messages_posted: list[Dict[str, Any]] = []

    async def post_incident_update(
        self,
        incident_id: str,
        message: str,
        sender: str = "Triage Agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        entry = {
            "incident_id": incident_id,
            "sender": sender,
            "message": message,
            "metadata": metadata or {},
        }
        self.messages_posted.append(entry)
        logger.info(
            f"[BAND MOCK ROOM: {self.room_prefix}/{incident_id}] {sender}: {message[:100]}..."
        )
        return True


# Default instance for P0/P1 development
band_adapter: BandAdapterInterface = MockBandAdapter()
