from __future__ import annotations

from typing import Protocol

from ..types import FlowName, FlowResponse, InboundUpdate


class FlowHandler(Protocol):
    flow: FlowName
    implemented: bool
    activates_session_on_start: bool

    def on_start(self, update: InboundUpdate) -> str | FlowResponse:
        ...

    def on_repeat_start(self, update: InboundUpdate) -> str | FlowResponse:
        ...

    def on_message(self, update: InboundUpdate) -> str | FlowResponse:
        ...

    def on_cancel(self, update: InboundUpdate) -> str | FlowResponse | None:
        ...
