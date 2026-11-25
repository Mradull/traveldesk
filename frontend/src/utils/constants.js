// =====================================================================
// TravelDesk frontend constants (one place for every fixed value)
// Rules mirror backend/app/schemas.py and the Agile Spec v2.0.
// =====================================================================

// ---------- Environment (frontend/.env) ----------
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

// ---------- Auth ----------
export const ROLES = { EMPLOYEE: "EMPLOYEE", MANAGER: "MANAGER" };
export const STORAGE_KEYS = { TOKEN: "td_token", USER: "td_user" };

/** Employees land on the Dashboard, managers on Approvals */
export const homePathFor = (user) => (user?.role === ROLES.MANAGER ? "/manager/approvals" : "/dashboard");

// ---------- Status badges (spec "Status badges" table) ----------
export const STATUS_STYLES = {
  "In Progress": "badge--blue",
  Rejected: "badge--red",
  "Approved - Active": "badge--green",
  "Approved - Completed": "badge--grey",
  PENDING: "badge--amber",
  AUTO_APPROVED: "badge--teal",
  APPROVED: "badge--green",
  REJECTED: "badge--red",
};

export const TICKET_STATUS_LABELS = {
  PENDING: "Pending",
  AUTO_APPROVED: "Auto-approved",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

// ---------- Trips ----------
export const MAX_DAYS_IN_ADVANCE = 365;      // start date at most today + 365
export const MAX_TRIP_DAYS = 30;             // start and end date both count
export const MIN_PURPOSE_CHARS = 10;
export const MAX_PURPOSE_CHARS = 500;
export const TRIP_AUTO_COMPLETE_DAYS = 90;   // trips complete automatically at start date + 90 days
// letters (incl. accented), spaces and . , ' ( ) -   e.g. "St. John's", "Kochi (Cochin)"
export const DESTINATION_PATTERN = /^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .,'()\-]{1,99}$/;

export const TRIP_FILTERS = [
  { value: "upcoming", label: "Upcoming" },
  { value: "past", label: "Past" },
  { value: "all", label: "All" },
];

// ---------- Decisions ----------
export const MIN_REVIEW_COMMENT_CHARS = 10;  // required to reject a trip or a ticket

export const REJECTION_REASONS = [
  { value: "MISSING_EVIDENCE", label: "Missing evidence" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Insufficient evidence" },
  { value: "INCORRECT_EVIDENCE", label: "Incorrect evidence" },
  { value: "UNCLEAR_PURPOSE", label: "Unclear purpose" },
  { value: "POLICY_CONCERN", label: "Policy concern" },
  { value: "OTHER", label: "Other" },
];

// ---------- Expenses and tickets ----------
export const EXPENSE_CATEGORIES = [
  { value: "AIRFARE", label: "Airfare" },
  { value: "LODGING", label: "Lodging" },
  { value: "MEALS", label: "Meals" },
  { value: "GROUND_TRANSPORT", label: "Ground transport" },
  { value: "INCIDENTALS", label: "Incidentals" },
];

// Review thresholds [POL-6.2]; the live values come from GET /policy/rules
export const POLICY_THRESHOLDS = {
  AIRFARE: 20000,
  LODGING: 7500,
  MEALS: 1500,
  GROUND_TRANSPORT: 3000,
  INCIDENTALS: 1000,
};

export const FLAG_LABELS = {
  OVER_THRESHOLD: "Over threshold",
  DUPLICATE_RECEIPT: "Duplicate receipt",
  RECEIPT_MISMATCH: "Receipt mismatch",
  RECEIPT_NOT_VERIFIED: "Receipt not verified",
};

// Labels for every rejection reason, including the one only the receipt check uses.
// (REJECTION_REASONS above is the manager's dropdown and must NOT include AI_RECEIPT_INVALID.)
export const REJECTION_REASON_LABELS = {
  ...Object.fromEntries(REJECTION_REASONS.map((r) => [r.value, r.label])),
  AI_RECEIPT_INVALID: "Receipt failed the automated check",
};

// Receipt check (Spec v2.1)
export const RECEIPT_CHECK_LABELS = {
  AMOUNT: "Amount",
  DATE: "Date",
  PLACE: "Place",
  AUTHENTICITY: "Authenticity",
};
export const RECEIPT_VERIFY_DEBOUNCE_MS = 600;

export const MAX_LINES_PER_TICKET = 20;
export const MAX_LINE_AMOUNT_INR = 200000;
export const MIN_DESCRIPTION_CHARS = 3;
export const MAX_DESCRIPTION_CHARS = 300;
export const EVIDENCE_MAX_BYTES = 5 * 1024 * 1024;
export const EVIDENCE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const INVOICE_PATTERN = /^[A-Z0-9][A-Z0-9\-_/]{2,49}$/;

// ---------- Vera ----------
export const MAX_CHAT_MESSAGE_CHARS = 1000;

// ---------- Friendly text for backend error codes ----------
export const ERROR_MESSAGES = {
  NETWORK_ERROR: "Can't reach the server. Check that the backend is running.",
  INVALID_CREDENTIALS: "Email or password is incorrect.",
  TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
  INVALID_TOKEN: "Your session is no longer valid. Please sign in again.",
  UNAUTHENTICATED: "Please sign in to continue.",
  FORBIDDEN: "You don't have access to this.",
  NOT_FOUND: "We couldn't find that record.",
  VALIDATION_ERROR: "Some fields need attention.",
  TRIP_NOT_EDITABLE: "This trip has already been decided and can't be edited.",
  TRIP_NOT_ACTIVE: "Expenses can only be claimed on an Approved - Active trip.",
  TRIP_NOT_FINISHED: "This trip hasn't ended yet, so it can't be completed.",
  TRIP_APPROVAL_WINDOW_PASSED: "This trip can no longer be decided (start date + 90 days has passed).",
  ALREADY_DECIDED: "This was already decided. Refresh to see the result.",
  SELF_APPROVAL: "You can't decide on your own request.",
  EVIDENCE_NOT_FOUND: "That receipt photo wasn't found. Upload it again.",
  EVIDENCE_ALREADY_USED: "That photo is already attached to another expense line.",
  EVIDENCE_INVALID_FILE: "Only JPEG, PNG or WEBP photos are accepted.",
  EVIDENCE_TOO_LARGE: "The photo is larger than 5 MB.",
  EXPENSE_DATE_BEFORE_TRIP_CREATED: "Expense date is before this trip was created.",
  REPLACEMENT_NOT_ALLOWED: "A new ticket can't be created for this rejected ticket.",
  RECEIPT_UNREADABLE: "A receipt photo couldn't be read. Upload a clearer photo of the whole receipt.",
  TICKET_READ_ONLY: "This ticket has been decided and is read-only.",
  SESSION_EXPIRED: "The chat ended. Starting a new one.",
  SESSION_CLOSED: "The chat ended. Starting a new one.",
  CHAT_RATE_LIMITED: "You're sending messages too quickly. Wait a moment and try again.",
  AI_UNAVAILABLE: "Vera is unavailable right now. Everything else in TravelDesk works.",
  AI_RATE_LIMITED: "Vera is busy. Try again in a minute.",
  AI_AUTH_ERROR: "Vera is unavailable right now. Everything else in TravelDesk works.",
  DATABASE_UNAVAILABLE: "The database is unavailable. Try again shortly.",
  INTERNAL_ERROR: "Something went wrong on our side.",
};
