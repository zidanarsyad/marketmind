"""Governance G_i of an enterprise: what it shares, with whom, who may see what inside it, and its decision policies.

Nothing leaves an enterprise except through its own API, and its API only hands out what the governance allows:

* **Shared view.** Each enterprise keeps a *view* of facts it could share (a capacity, a forecast, a risk). In the
  ``local`` mode it shares only the public keys (a campaign calendar, a price list); in the ``ecosystem`` mode it also
  shares the keys it agreed to give its partners and the Global Control Center. Raw records (maintenance logs, QC
  measurements, other clients' orders, consumer reviews) are never in the view at all.
* **Roles.** The users U_i of an enterprise see the datasets their role needs; some fields (prices, costs) are hidden
  from roles that have no business with them, and only some roles may approve.
* **Policies.** The numbers its agents must respect: a minimum margin, a utilisation ceiling, a service-level target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AUDIENCES = ("partner", "control")


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    datasets: tuple[str, ...] = ("*",)          # "*" opens every dataset of the enterprise
    hidden_fields: tuple[str, ...] = ()
    can_approve: bool = False

    def may_open(self, dataset: str) -> bool:
        return "*" in self.datasets or dataset in self.datasets


@dataclass
class Governance:
    public: tuple[str, ...] = ()                # shared in both modes, with anyone
    partner: tuple[str, ...] = ()               # shared with partner enterprises in the ecosystem mode
    control: tuple[str, ...] = ()               # shared with the Global Control Center in the ecosystem mode
    private: tuple[str, ...] = ()               # datasets that never leave the enterprise (documented, enforced)
    policies: dict[str, Any] = field(default_factory=dict)
    approval_threshold_idr: float | None = None

    def share(self, view: dict, audience: str, mode: str) -> dict:
        """The part of ``view`` this enterprise lets ``audience`` read in ``mode``."""
        if audience not in AUDIENCES:
            raise ValueError(f"unknown audience {audience!r}")
        allowed = set(self.public)
        if mode == "ecosystem":
            allowed |= set(self.partner if audience == "partner" else self.control)
        return {k: v for k, v in view.items() if k in allowed}

    def describe(self) -> dict:
        return {"public": list(self.public), "shared_with_partners": list(self.partner),
                "shared_with_control_center": list(self.control), "private_datasets": list(self.private),
                "policies": self.policies, "approval_threshold_idr": self.approval_threshold_idr}


def visible_row(row: dict, role: Role) -> dict:
    """A record as ``role`` may see it: hidden fields are masked, not dropped, so the table keeps its shape."""
    return {k: ("hidden for this role" if k in role.hidden_fields else v) for k, v in row.items()}
