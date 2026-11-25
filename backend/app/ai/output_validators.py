"""
ai/output_validators.py - check the LLM's text against the data it was given (owner: Piyush, M2).

O1 weather grounding: every number with a unit (C, %, mm, km/h) must equal a value from this
   turn's or this session's weather tool results (tolerance 0.5), and condition / packing words
   (rain, snow, fog, storm, strong wind, warm layers, sun protection ...) must match the data.
O2 policy citations: every [POL-x.y] / [GUIDE-n] / [FAQ-n] must be one of the retrieved ref ids,
   and every INR amount must appear in the retrieved chunks.
Pure functions: they only report problems. chat_service decides to regenerate once or fall
back to a template (see guardrails O1/O2 in the spec).
"""
import re
from dataclasses import dataclass, field

from app.schemas import RetrievedChunk, WeatherForecastResult

TOLERANCE = 0.5
COLD_MAX_C, HOT_MIN_C, STRONG_WIND_KMH = 15, 32, 40   # same cut-offs as the advice table in the spec
# umbrella / raincoat advice only for a real rain risk (team change: the spec said any chance > 0, which
# produced "umbrella - rain chance 2%"); mentioning a small chance of rain is still allowed
RAIN_GEAR_MIN_PCT = 20

RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | set(range(95, 100))
SNOW_CODES, FOG_CODES, STORM_CODES = set(range(71, 78)), {45, 48}, set(range(95, 100))

# number + unit, e.g. "28 °C", "70%", "4.2 mm", "35 km/h". (?<![\d.]) stops "19-28" being read as -28.
NUMBER_WITH_UNIT = re.compile(
    r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(°\s*c\b|°|degrees?(?:\s*c(?:elsius)?)?\b|c\b|%|percent\b|mm\b|"
    r"km\s*/\s*h\b|kmh\b|kph\b|kmph\b)", re.IGNORECASE)

# word groups that claim a weather condition -> the fact that must be true in the data
CONDITION_WORDS = {
    "rain": re.compile(r"\b(rain\w*|showers?|drizzl\w*)\b", re.I),
    "rain_gear": re.compile(r"\b(umbrellas?|raincoats?|rain ?jackets?|waterproofs?)\b", re.I),
    "storm": re.compile(r"\b(thunder\w*|storms?|stormy|lightning)\b", re.I),
    "snow": re.compile(r"\b(snow\w*|sleet|blizzards?)\b", re.I),
    "fog": re.compile(r"\b(fog\w*|mist\w*)\b", re.I),
    "wind": re.compile(r"\b(windy|strong winds?|gusts?|gusty|gales?|secure loose items)\b", re.I),
    "cold": re.compile(r"\b(warm layers?|jackets?|sweaters?|thermals?|coats?|woollens?|cold)\b", re.I),
    "hot": re.compile(r"\b(sunscreen|sun protection|heat\w*|hot)\b", re.I),
}
# a negation just before the word ("no rain expected", "0% chance of rain") is not a claim
NEGATION = re.compile(r"\b(no|not|without|unlikely|none|zero)\b|\b0\s*%|\b0(?:\.0)?\s*mm", re.I)

GEAR_NEGATION = re.compile(r"\b(no|not|without|none|don't|do not|won't need)\b", re.I)

CITATION = re.compile(r"\[((?:POL|GUIDE|FAQ)-\d+(?:\.\d+)?)\]")
INR_AMOUNT = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:INR|rupees)", re.I)


@dataclass
class WeatherFacts:
    """Everything a weather answer is allowed to claim, collected from tool results."""
    temps: set = field(default_factory=set)
    pcts: set = field(default_factory=set)
    mms: set = field(default_factory=set)
    winds: set = field(default_factory=set)
    flags: set = field(default_factory=set)       # rain / storm / snow / fog / wind / cold / hot

    @property
    def has_values(self) -> bool:
        return bool(self.temps or self.pcts or self.mms or self.winds)


def weather_facts(results: list[WeatherForecastResult]) -> WeatherFacts:
    """Collect the allowed numbers and true conditions from all given forecasts."""
    f = WeatherFacts()
    for r in results:
        for d in r.days:
            f.temps |= {v for v in (d.temp_min_c, d.temp_max_c) if v is not None}
            f.pcts |= {v for v in (d.precipitation_probability_max_pct,) if v is not None}
            f.mms |= {v for v in (d.precipitation_sum_mm,) if v is not None}
            f.winds |= {v for v in (d.wind_speed_max_kmh,) if v is not None}
            code = d.weather_code
            if (d.precipitation_probability_max_pct or 0) > 0 or (d.precipitation_sum_mm or 0) > 0 or code in RAIN_CODES:
                f.flags.add("rain")
            if ((d.precipitation_probability_max_pct or 0) >= RAIN_GEAR_MIN_PCT or (d.precipitation_sum_mm or 0) > 0
                    or code in RAIN_CODES):
                f.flags.add("rain_gear")
            for name, codes in (("storm", STORM_CODES), ("snow", SNOW_CODES), ("fog", FOG_CODES)):
                if code in codes:
                    f.flags.add(name)
            if (d.wind_speed_max_kmh or 0) >= STRONG_WIND_KMH:
                f.flags.add("wind")
            if d.temp_min_c is not None and d.temp_min_c <= COLD_MAX_C:
                f.flags.add("cold")
            if d.temp_max_c is not None and d.temp_max_c >= HOT_MIN_C:
                f.flags.add("hot")
    return f


def _unit_values(unit: str, facts: WeatherFacts) -> set:
    u = unit.lower().replace(" ", "")
    if u.startswith("%") or u.startswith("percent"):
        return facts.pcts
    if u.startswith("mm"):
        return facts.mms
    if u.startswith("km") or u in ("kph", "kmph"):
        return facts.winds
    return facts.temps                                   # °C / degrees / C


def check_weather_grounding(text: str, facts: WeatherFacts) -> list[str]:
    """O1: return a list of problems (empty list = grounded)."""
    problems = []
    for m in NUMBER_WITH_UNIT.finditer(text):
        value, unit = float(m.group(1)), m.group(2)
        if not any(abs(value - allowed) <= TOLERANCE for allowed in _unit_values(unit, facts)):
            problems.append(f"number {m.group(0).strip()} not in forecast")
    for name, pattern in CONDITION_WORDS.items():
        for m in pattern.finditer(text):
            sentence_start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
            before = text[max(sentence_start, m.start() - 40):m.start()]
            sentence = text[sentence_start:text.find(".", m.end()) if "." in text[m.end():] else len(text)]
            # "no rain", "0% chance of rain" are honest; but rain GEAR advice is only excused by a negation
            # right before it ("no umbrella needed"), never by a "0%" elsewhere in the sentence
            if name == "rain_gear":
                if GEAR_NEGATION.search(before):       # "no umbrella needed", "don't need a raincoat"
                    continue
            elif NEGATION.search(before) or (name == "rain" and NEGATION.search(sentence)):
                continue                                 # "no rain", "0% chance of rain"
            if name not in facts.flags:
                problems.append(f"'{m.group(0)}' not supported by forecast")
    return problems


@dataclass
class CitationCheck:
    valid: list[str]          # cited ids that were retrieved (in order of appearance, no duplicates)
    invalid: list[str]        # cited ids that were NOT retrieved
    bad_amounts: list[str]    # INR amounts not found in the retrieved text

    @property
    def ok(self) -> bool:
        return bool(self.valid) and not self.invalid and not self.bad_amounts


def check_citations(text: str, chunks: list[RetrievedChunk]) -> CitationCheck:
    """O2: citations must come from the retrieved chunks; INR amounts must be in their text."""
    retrieved = {c.ref_id for c in chunks}
    cited = list(dict.fromkeys(CITATION.findall(text)))
    corpus = " ".join(c.content for c in chunks).replace(",", "")
    bad_amounts = []
    for m in INR_AMOUNT.finditer(text):
        amount = (m.group(1) or m.group(2)).replace(",", "").rstrip(".")
        amount = amount[:-3] if amount.endswith(".00") else amount
        if not re.search(rf"(?<!\d){re.escape(amount)}(?!\d)", corpus):
            bad_amounts.append(m.group(0).strip())
    return CitationCheck(valid=[c for c in cited if c in retrieved],
                         invalid=[c for c in cited if c not in retrieved], bad_amounts=bad_amounts)


def remove_citations(text: str, ids: list[str]) -> str:
    """Delete the given [ID] markers from the text."""
    for ref in ids:
        text = text.replace(f"[{ref}]", "")
    return re.sub(r"\s+([.,;])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip()
