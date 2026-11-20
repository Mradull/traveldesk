"""
Pure functions: OVER_THRESHOLD and DUPLICATE_RECEIPT (photo sha256 or invoice number, ignoring REJECTED tickets).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

"Pure" means: no database, no AI, no clock. The same line with the same inputs always gives the
same flags (spec goal "Deterministic, auditable approvals"). The caller (TicketService) supplies
the employee's already-claimed photo hashes and invoice numbers from non-rejected tickets.
Flags never block a submission; they only route the ticket to the manager [POL-9.1].
"""

from dataclasses import dataclass
from decimal import Decimal

from app.schemas import ExpenseCategory, PolicyFlag, PolicyRuleCode, TicketRouting, TicketStatus

OVER_THRESHOLD_REF = "[POL-6.2]"
DUPLICATE_RECEIPT_REF = "[POL-7.4]"


@dataclass(frozen=True)
class PolicyConfig:
    """Review thresholds per category (INR) and the rules version stamped on every flag."""

    thresholds: dict[ExpenseCategory, Decimal]
    rules_version: str

    @classmethod
    def from_settings(cls, settings) -> "PolicyConfig":
        """Build the config from the POLICY_* values in .env (core/config.py)."""
        return cls(
            thresholds={
                ExpenseCategory.AIRFARE: Decimal(settings.policy_threshold_airfare),
                ExpenseCategory.LODGING: Decimal(settings.policy_threshold_lodging),
                ExpenseCategory.MEALS: Decimal(settings.policy_threshold_meals),
                ExpenseCategory.GROUND_TRANSPORT: Decimal(settings.policy_threshold_ground_transport),
                ExpenseCategory.INCIDENTALS: Decimal(settings.policy_threshold_incidentals),
            },
            rules_version=settings.policy_rules_version,
        )


@dataclass(frozen=True)
class PolicyLine:
    """The facts of one expense line the rules look at."""

    expense_type: ExpenseCategory
    amount: Decimal
    sha256: str                      # fingerprint of the receipt photo
    invoice_number: str | None       # already upper-case (schemas.ExpenseLineCreate)


def _inr(amount: Decimal) -> str:
    """1800 -> '1,800.00' (format used in flag messages)."""
    return f"{amount:,.2f}"


def evaluate_line(
    line: PolicyLine,
    config: PolicyConfig,
    existing_hashes: set[str],
    existing_invoices: set[str],
) -> list[PolicyFlag]:
    """Return the flags for one line.

    OVER_THRESHOLD: amount strictly above the category threshold (equal is fine) [POL-6.2].
      e.g. MEALS 1,500.00 -> no flag; MEALS 1,800.00 -> flag.
    DUPLICATE_RECEIPT: same photo hash, or same invoice number, already claimed on another line of
      the same employee whose ticket is not REJECTED [POL-7.4].
    """
    flags: list[PolicyFlag] = []

    threshold = config.thresholds[ExpenseCategory(line.expense_type)]
    if line.amount > threshold:
        flags.append(
            PolicyFlag(
                rule_code=PolicyRuleCode.OVER_THRESHOLD,
                message=(
                    f"{ExpenseCategory(line.expense_type).value} amount {_inr(line.amount)} "
                    f"is above the {_inr(threshold)} review threshold"
                ),
                policy_ref=OVER_THRESHOLD_REF,
                threshold_amount=threshold,
            )
        )

    same_photo = line.sha256 in existing_hashes
    same_invoice = bool(line.invoice_number) and line.invoice_number.upper() in existing_invoices
    if same_photo or same_invoice:
        reason = "receipt photo" if same_photo else f"invoice number {line.invoice_number}"
        flags.append(
            PolicyFlag(
                rule_code=PolicyRuleCode.DUPLICATE_RECEIPT,
                message=f"The same {reason} was already claimed on another expense line",
                policy_ref=DUPLICATE_RECEIPT_REF,
            )
        )
    return flags


def route(total_flags: int) -> tuple[TicketStatus, TicketRouting]:
    """Zero flags on every line -> AUTO_APPROVED by SYSTEM; any flag -> PENDING for the manager."""
    if total_flags == 0:
        return TicketStatus.AUTO_APPROVED, TicketRouting.AUTO
    return TicketStatus.PENDING, TicketRouting.MANAGER
