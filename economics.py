"""Equipment cost, payback and NPV for flexibility investments."""
from __future__ import annotations

import pandas as pd

# Sources for default cost assumptions (cited in the app and README).
COST_SOURCES = {
    "battery_cost": (
        "Switch Together, 'Solar battery storage cost & ROI' — indicative UK installed cost for a 10 kWh "
        "home battery £4,500–£7,000 (default = midpoint £5,750); also cites MCS data: average battery "
        "installation in 2024 ≈ £8,035 (all sizes)",
        "https://switchtogether.co.uk/resource-hub/blog/solar-battery-storage-cost-roi",
    ),
    "battery_vat": (
        "HMRC VAT Notice 708/6, s.2.19 — home batteries (incl. standalone, grid-charged) zero-rated "
        "from 1 Feb 2024 to 31 Mar 2027",
        "https://www.gov.uk/guidance/vat-on-energy-saving-materials-and-heating-equipment-notice-7086",
    ),
    "smart_charger": (
        "The Electric Vehicles (Smart Charge Points) Regulations 2021 — private charge points sold in GB "
        "must have smart functionality from 30 June 2022, so smart charging needs no extra hardware",
        "https://www.gov.uk/guidance/regulations-electric-vehicle-smart-charge-points",
    ),
    "discount_rate": (
        "HM Treasury, Green Book Discount Rate Review — Findings and Recommendations (2026): real discount "
        "rate of 3% for maturities up to 30 years",
        "https://assets.publishing.service.gov.uk/media/6a43915e7ac6fd9c6a94abbe/Findings_and_Recommendations_-_Green_Book_Discount_Rate_Review.pdf",
    ),
}

DEFAULT_BATTERY_COST_GBP = 5750.0     # midpoint of £4,500–£7,000 for 10 kWh (Switch Together)
DEFAULT_BATTERY_REF_KWH = 10.0
DEFAULT_BATTERY_LIFE_YEARS = 10       # ASSUMPTION — not sourced
DEFAULT_SMART_CHARGER_EXTRA_GBP = 0.0  # smart functionality mandatory since 30 Jun 2022
DEFAULT_DISCOUNT_RATE = 0.03          # Green Book review 2026 (real)


def appraise(cost: float, saving_y1: float, life: int, discount: float, growth: float, horizon: int) -> dict:
    """Payback and NPV for an upfront cost and a stream of annual savings.

    Savings arrive at the end of each year, change by `growth` per year (real),
    and stop after `life` years. Returns simple/discounted payback (fractional
    years, None if never within life), NPV over life, and a cumulative series.
    """
    years = list(range(0, horizon + 1))
    cum, cum_disc = [-cost], [-cost]
    simple_pb = disc_pb = None if cost > 0 else 0.0
    for y in years[1:]:
        s = saving_y1 * (1 + growth) ** (y - 1) if y <= life else 0.0
        d = s / (1 + discount) ** y
        prev, prev_d = cum[-1], cum_disc[-1]
        cum.append(prev + s)
        cum_disc.append(prev_d + d)
        if simple_pb is None and s > 0 and cum[-1] >= 0:
            simple_pb = (y - 1) + (-prev / s)
        if disc_pb is None and d > 0 and cum_disc[-1] >= 0:
            disc_pb = (y - 1) + (-prev_d / d)
    npv = cum_disc[min(life, horizon)]
    lifetime_savings = sum(saving_y1 * (1 + growth) ** (y - 1) for y in range(1, life + 1))
    return {
        "cost": cost,
        "saving_y1": saving_y1,
        "simple_payback": simple_pb,
        "discounted_payback": disc_pb,
        "npv": npv,
        "lifetime_savings": lifetime_savings,
        "pays_back": disc_pb is not None,
        "series": pd.DataFrame({"year": years, "cumulative": cum, "cumulative_discounted": cum_disc}),
    }


def fmt_years(v: float | None, life: int) -> str:
    if v is None:
        return f"Not within {life} yrs"
    if v == 0:
        return "Immediate"
    return f"{v:.1f} yrs"


def break_even_cost(saving_y1: float, life: int, discount: float, growth: float) -> float:
    """Upfront cost at which NPV over life is exactly zero."""
    return sum(saving_y1 * (1 + growth) ** (y - 1) / (1 + discount) ** y for y in range(1, life + 1))

