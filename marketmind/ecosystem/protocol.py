"""Messages between the agents of different enterprises, in the spirit of the Agent2Agent (A2A) protocol.

Every enterprise publishes an **Agent Card** (who it is, which skills its agents offer, where to send messages) and
exchanges **messages** with a small set of performatives borrowed from FIPA ACL: a request for proposals, a proposal,
a counter-proposal, acceptance or rejection, a plain request, agreement or refusal, and information. The JSON contract
follows the course brief's example (``message_id``, ``sender``, ``receiver``, ``message_type``, ``task``, ``payload``,
``reply_required``) and adds what a conversation needs: ``conversation_id``, ``in_reply_to`` and the simulated week.

This is a simulation contract, not the full A2A wire protocol (no JSON-RPC envelope, tasks or streaming): the point is
that agents of independent enterprises talk only through these messages, each over its own server.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MessageType = Literal[
    "REQUEST_PROPOSAL",   # call for proposals (Contract Net), or opens a negotiation
    "PROPOSE",            # an offer
    "COUNTER_PROPOSAL",   # a counter-offer in an alternating-offers negotiation
    "ACCEPT_PROPOSAL",    # closes a negotiation with an agreement
    "REJECT_PROPOSAL",    # closes it without one, or refuses a plan, with the reason (and a constraint) in the payload
    "REQUEST",            # asks for an action or for information
    "AGREE",              # will do (possibly in part: the payload says how much)
    "REFUSE",             # will not, with the reason
    "INFORM",             # a fact: a delivery, a forecast, a risk, a fulfilment report
    "CONFIRM",            # a plan or a contract everyone accepted
    "FAILURE",            # tried and could not
]
PERFORMATIVES: tuple[str, ...] = MessageType.__args__  # type: ignore[attr-defined]


class Message(BaseModel):
    """One message on the ecosystem bus. Addresses are ``enterprise.agent`` (for example ``kirana.procurement``)."""

    message_id: str
    conversation_id: str
    sender: str
    receiver: str
    message_type: MessageType
    task: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reply_required: bool = False
    in_reply_to: str | None = None
    week: int = 0

    @field_validator("sender", "receiver")
    @classmethod
    def _address(cls, v: str) -> str:
        if "." not in v or v.startswith(".") or v.endswith("."):
            raise ValueError(f"an address is enterprise.agent, got {v!r}")
        return v

    @property
    def sender_enterprise(self) -> str:
        return enterprise_of(self.sender)

    @property
    def receiver_enterprise(self) -> str:
        return enterprise_of(self.receiver)


def enterprise_of(address: str) -> str:
    return address.split(".", 1)[0]


class MessageFactory:
    """Numbers an enterprise's outgoing messages (``KIR-0001``...), so a run is reproducible message for message."""

    def __init__(self, prefix: str):
        self.prefix = prefix.upper()[:3]
        self.n = 0

    def _next(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n:04d}"

    def new(self, sender: str, receiver: str, message_type: str, task: str, payload: dict | None = None, *,
            week: int, reply_required: bool = False, conversation_id: str | None = None) -> Message:
        mid = self._next()
        return Message(message_id=mid, conversation_id=conversation_id or mid, sender=sender, receiver=receiver,
                       message_type=message_type, task=task, payload=payload or {}, reply_required=reply_required,
                       week=week)

    def reply(self, to: Message, sender: str, message_type: str, payload: dict | None = None, *,
              reply_required: bool = False, task: str | None = None) -> Message:
        mid = self._next()
        return Message(message_id=mid, conversation_id=to.conversation_id, sender=sender, receiver=to.sender,
                       message_type=message_type, task=task or to.task, payload=payload or {},
                       reply_required=reply_required, in_reply_to=to.message_id, week=to.week)


def agent_card(enterprise, base_url: str = "") -> dict:
    """The enterprise's A2A Agent Card: identity, endpoint, capabilities and the skills its agents offer.

    Field names follow the A2A Agent Card (name, description, url, version, capabilities, skills, default input and
    output modes); ``x-enterprise`` carries the enterprise model E = (U, M, D, A, P, G) the course asks for."""
    skills = [{"id": f"{enterprise.key}.{a.name}", "name": a.title, "description": a.description,
               "tags": [a.kind] + ([a.model] if a.model else [])} for a in enterprise.agents.values()]
    return {
        "name": enterprise.name,
        "description": enterprise.description,
        "url": f"{base_url.rstrip('/')}/api/a2a/messages" if base_url else "/api/a2a/messages",
        "version": "1.0",
        "protocolVersion": "marketmind-a2a-sim/1",
        "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": True},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": skills,
        "x-enterprise": enterprise.spec(),
    }
