"""Household tariff and flexibility model for GB Home Flex Explorer.

All quantities are per half-hour (HH). Energy in kWh, prices in pence/kWh.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

LOCAL_TZ = "Europe/London"

# Stylised GB domestic daily load shape (relative weight per local clock hour).
# ASSUMPTION — not a sourced dataset. Shape follows the familiar domestic
# pattern (overnight trough, morning shoulder, 17:00–20:00 evening peak).
# Editable in the app.
DEFAULT_HOURLY_SHAPE = [
    0.55, 0.45, 0.40, 0.38, 0.38, 0.42,   # 00–05
    0.60, 0.85, 0.90, 0.80, 0.75, 0.75,   # 06–11
    0.80, 0.78, 0.75, 0.80, 0.95, 1.30,   # 12–17
    1.50, 1.45, 1.30, 1.15, 0.95, 0.75,   # 18–23
]
# ASSUMPTION — relative monthly consumption (winter higher: lighting, appliances).
DEFAULT_MONTHLY_FACTOR = [1.20, 1.12, 1.05, 0.95, 0.88, 0.83, 0.83, 0.85, 0.92, 1.02, 1.12, 1.23]


@dataclass
class Assumptions:
    # Household
    annual_kwh: float
    hourly_shape: list
    monthly_factor: list
    # Price cap
    cap_unit_p: float
    cap_sc_p_day: float
    # ToU tariff
    tou_type: str                 # "wholesale" or "static"
    tou_sc_p_day: float
    tou_pass_through: float       # share of wholesale deviation passed through
    tou_vat: float                # VAT applied to the wholesale deviation (fraction)
    tou_floor_p: float | None     # minimum unit rate, None = no floor
    tou_cap_p: float | None       # maximum unit rate, None = no cap
    static_bands: dict | None     # {"offpeak": (start_h, end_h, rate), ...}
    # EV
    ev_on: bool
    ev_kwh_day: float
    ev_charger_kw: float
    ev_plugin_hour: float         # local clock, e.g. 18.0
    ev_depart_hour: float         # local clock next morning, e.g. 7.0
    # Battery
    bat_on: bool
    bat_kwh: float
    bat_kw: float
    bat_rte: float                # round-trip efficiency (0-1)
    bat_allow_export: bool
    bat_export_share: float       # export price as fraction of import ToU price
    bat_degradation_p: float      # p per kWh discharged


# --------------------------------------------------------------------------
# Load profile
# --------------------------------------------------------------------------
def household_profile(index_utc: pd.DatetimeIndex, a: Assumptions) -> np.ndarray:
    """Spread annual_kwh over the HH index using the hourly shape and monthly factors."""
    local = index_utc.tz_convert(LOCAL_TZ)
    w = np.asarray(a.hourly_shape)[local.hour] * np.asarray(a.monthly_factor)[local.month - 1]
    # Scale so the modelled year sums exactly to annual_kwh (scaled to 365 days).
    days = len(index_utc) / 48
    return w / w.sum() * a.annual_kwh * (days / 365.0)


# --------------------------------------------------------------------------
# Tariffs
# --------------------------------------------------------------------------
def wholesale_p_kwh(prices: pd.DataFrame) -> np.ndarray:
    return prices["price_gbp_mwh"].to_numpy() / 10.0  # £/MWh -> p/kWh


def tou_rates(prices: pd.DataFrame, house_kwh: np.ndarray, a: Assumptions) -> np.ndarray:
    """Half-hourly ToU unit rate (p/kWh)."""
    w = wholesale_p_kwh(prices)
    if a.tou_type == "wholesale":
        # Revenue-neutral wholesale-tracking tariff: base = cap unit rate, plus the
        # deviation of each HH wholesale price from the household's
        # consumption-weighted average wholesale price. A household with the
        # baseline profile therefore pays the same as on the cap (before
        # floors/caps), and any saving comes from shifting load.
        w_bar = float(np.sum(w * house_kwh) / np.sum(house_kwh))
        r = a.cap_unit_p + a.tou_pass_through * (w - w_bar) * (1 + a.tou_vat)
        if a.tou_floor_p is not None:
            r = np.maximum(r, a.tou_floor_p)
        if a.tou_cap_p is not None:
            r = np.minimum(r, a.tou_cap_p)
        return r
    # Static banded ToU.
    local = prices.index.tz_convert(LOCAL_TZ)
    h = local.hour + local.minute / 60.0
    r = np.full(len(h), a.static_bands["day"][2], dtype=float)
    for band in ("offpeak", "peak"):
        s, e, rate = a.static_bands[band]
        mask = (h >= s) & (h < e) if s < e else ((h >= s) | (h < e))
        r[mask] = rate
    return r


def static_band_defaults(prices: pd.DataFrame, house_kwh: np.ndarray, a: Assumptions) -> dict:
    """Derive default static-band rates from the wholesale-tracking tariff so they
    are grounded in the fetched data rather than invented."""
    tmp = Assumptions(**{**a.__dict__, "tou_type": "wholesale", "tou_floor_p": None, "tou_cap_p": None})
    r = tou_rates(prices, house_kwh, tmp)
    local = prices.index.tz_convert(LOCAL_TZ)
    h = local.hour + local.minute / 60.0
    bands = {"offpeak": (0.0, 7.0), "peak": (16.0, 19.0)}
    out = {}
    masks = {}
    for k, (s, e) in bands.items():
        masks[k] = (h >= s) & (h < e)
    masks["day"] = ~(masks["offpeak"] | masks["peak"])
    for k, m in masks.items():
        avg = float(np.sum(r[m] * house_kwh[m]) / np.sum(house_kwh[m]))
        s, e = bands.get(k, (7.0, 16.0))
        out[k] = (s, e, round(avg, 2))
    return out


# --------------------------------------------------------------------------
# EV charging
# --------------------------------------------------------------------------
def _sessions(index_utc: pd.DatetimeIndex, a: Assumptions) -> list[np.ndarray]:
    """Index arrays for each overnight plug-in session (plug-in day d -> depart d+1)."""
    local = index_utc.tz_convert(LOCAL_TZ)
    h = (local.hour + local.minute / 60.0).to_numpy()
    # Integer local calendar-day number (wall-clock date), avoiding tz arithmetic
    # pitfalls on DST-change days.
    day = (local.tz_localize(None).normalize() - pd.Timestamp("2000-01-01")).days.to_numpy()
    # Hours >= plug-in belong to today's session; hours < departure belong to
    # yesterday's session; everything else is unplugged (-1).
    sess_day = np.where(h >= a.ev_plugin_hour, day, np.where(h < a.ev_depart_hour, day - 1, -1))
    codes, uniq = pd.factorize(sess_day)
    unplugged = np.flatnonzero(uniq == -1)
    if len(unplugged):
        codes = np.where(codes == unplugged[0], -1, codes)
    out = []
    for c in range(len(uniq)):
        idx = np.flatnonzero(codes == c)
        if len(idx) >= 2:
            out.append(idx)
    # The window starts mid-session (early hours of day 1 belong to the evening
    # before the window) and ends mid-session (last evening). Treat the year as
    # cyclic: join the last evening and the first morning into one session, so
    # a 365-day window has exactly 365 sessions. Unmanaged charging starts with
    # the evening part.
    if len(out) >= 2 and h[0] < a.ev_depart_hour and h[-1] >= a.ev_plugin_hour:
        first, last = out[0], out[-1]
        out = out[1:-1] + [np.concatenate([last, first])]
    return out


def ev_profile(index_utc: pd.DatetimeIndex, rates: np.ndarray, a: Assumptions, smart: bool) -> np.ndarray:
    ev = np.zeros(len(index_utc))
    if not a.ev_on or a.ev_kwh_day <= 0:
        return ev
    per_hh = a.ev_charger_kw * 0.5
    for idx in _sessions(index_utc, a):
        need = min(a.ev_kwh_day, per_hh * len(idx))
        order = idx[np.argsort(rates[idx], kind="stable")] if smart else idx  # idx is chronological
        for i in order:
            if need <= 1e-9:
                break
            take = min(per_hh, need)
            ev[i] += take
            need -= take
    return ev


# --------------------------------------------------------------------------
# Home battery — per-day linear programme (day-ahead perfect foresight)
# --------------------------------------------------------------------------
def battery_dispatch_full(index_utc, load, rates, a: Assumptions):
    """Per-day linear programme with day-ahead foresight.

    Returns (grid charge kWh, discharge-to-home kWh, export kWh) per HH. Each local
    calendar day: minimise import cost of charging minus avoided import cost of
    discharging (minus export revenue) plus degradation, subject to SoC limits,
    a shared power limit, end-of-day SoC equal to start-of-day SoC, and discharge
    to the home never exceeding that HH's load.
    """
    n = len(index_utc)
    ch = np.zeros(n); dis = np.zeros(n); exp = np.zeros(n)
    if not a.bat_on or a.bat_kwh <= 0 or a.bat_kw <= 0:
        return ch, dis, exp
    eta = np.sqrt(a.bat_rte)
    pmax = a.bat_kw * 0.5
    local = index_utc.tz_convert(LOCAL_TZ)
    codes, _ = pd.factorize(local.normalize())
    for d in np.unique(codes):
        idx = np.flatnonzero(codes == d)
        T = len(idx)
        r = rates[idx]
        L = load[idx]
        exp_ub = pmax if a.bat_allow_export else 0.0
        cost = np.concatenate([r, -r + a.bat_degradation_p, -a.bat_export_share * r + a.bat_degradation_p, [0.0]])
        tri = np.tril(np.ones((T, T)))
        A_soc = np.hstack([eta * tri, -tri / eta, -tri / eta, np.ones((T, 1))])
        A_pow = np.hstack([np.eye(T), np.eye(T), np.eye(T), np.zeros((T, 1))])
        A_ub = np.vstack([A_soc, -A_soc, A_pow])
        b_ub = np.concatenate([np.full(T, a.bat_kwh), np.zeros(T), np.full(T, pmax)])
        A_eq = np.concatenate([np.full(T, eta), np.full(T, -1 / eta), np.full(T, -1 / eta), [0.0]])[None, :]
        bounds = ([(0, pmax)] * T + [(0, float(v)) for v in np.clip(L, 0, pmax)]
                  + [(0, exp_ub)] * T + [(0, a.bat_kwh)])
        res = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=[0.0], bounds=bounds, method="highs")
        if res.status != 0:
            continue
        v = res.x
        ch[idx] = v[:T]; dis[idx] = v[T:2 * T]; exp[idx] = v[2 * T:3 * T]
    return ch, dis, exp


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
def run_scenarios(prices: pd.DataFrame, a: Assumptions) -> tuple[pd.DataFrame, dict]:
    idx = prices.index
    days = len(idx) / 48
    house = household_profile(idx, a)
    rates = tou_rates(prices, house, a)
    cap = np.full(len(idx), a.cap_unit_p)

    ev_dumb = ev_profile(idx, rates, a, smart=False)
    ev_smart = ev_profile(idx, rates, a, smart=True)
    load_smart = house + ev_smart
    ch, dis, exp = battery_dispatch_full(idx, load_smart, rates, a)

    def bill(load, unit, sc, export=None, discharge=None):
        energy = float(np.sum(load * unit)) / 100
        exp_rev = 0.0 if export is None else float(np.sum(export * unit * a.bat_export_share)) / 100
        degr = 0.0 if discharge is None else float(np.sum(discharge) * a.bat_degradation_p) / 100
        standing = sc * days / 100
        return {
            "kwh_import": float(np.sum(load)),
            "energy_gbp": energy,
            "standing_gbp": standing,
            "export_gbp": -exp_rev,
            "degradation_gbp": degr,
            "total_gbp": energy + standing - exp_rev + degr,
        }

    rows = {}
    rows["1. Price cap — household only"] = bill(house, cap, a.cap_sc_p_day)
    if a.ev_on:
        rows["2. Price cap — household + EV"] = bill(house + ev_dumb, cap, a.cap_sc_p_day)
    rows["3. ToU — household only"] = bill(house, rates, a.tou_sc_p_day)
    if a.ev_on:
        rows["4. ToU — household + EV, unmanaged charging"] = bill(house + ev_dumb, rates, a.tou_sc_p_day)
        rows["5. ToU — household + EV, smart charging"] = bill(load_smart, rates, a.tou_sc_p_day)
    if a.bat_on:
        net = load_smart - dis + ch
        rows[f"6. ToU — household{' + smart EV' if a.ev_on else ''} + battery"] = bill(
            net, rates, a.tou_sc_p_day, export=exp, discharge=dis + exp
        )
    df = pd.DataFrame(rows).T
    # Annualise to 365 days (data window may be 365 days already).
    df[["energy_gbp", "standing_gbp", "export_gbp", "degradation_gbp", "total_gbp", "kwh_import"]] *= 365.0 / days

    series = pd.DataFrame(
        {
            "wholesale_p": wholesale_p_kwh(prices),
            "tou_p": rates,
            "cap_p": cap,
            "house_kwh": house,
            "ev_dumb_kwh": ev_dumb,
            "ev_smart_kwh": ev_smart,
            "bat_charge_kwh": ch,
            "bat_discharge_kwh": dis,
            "bat_export_kwh": exp,
        },
        index=idx.tz_convert(LOCAL_TZ),
    )
    return df, {"series": series, "days": days}


def flexibility_values(df: pd.DataFrame) -> list[tuple[str, float, str]]:
    """Pairwise differences that isolate the value of each flexibility step."""
    t = df["total_gbp"]
    get = lambda prefix: next((t[k] for k in t.index if k.startswith(prefix)), None)  # noqa: E731
    out = []
    c1, c2, c3, c4, c5, c6 = (get(f"{i}.") for i in range(1, 7))
    if c1 is not None and c3 is not None:
        out.append(("Switch cap → ToU (no behaviour change)", c1 - c3, "1 − 3"))
    if c4 is not None and c5 is not None:
        out.append(("Smart EV charging (vs unmanaged, on ToU)", c4 - c5, "4 − 5"))
    if c6 is not None:
        base = c5 if c5 is not None else c3
        out.append(("Home battery (on top of smart EV)" if c5 is not None else "Home battery", base - c6,
                    "5 − 6" if c5 is not None else "3 − 6"))
    best = c6 if c6 is not None else (c5 if c5 is not None else c3)
    ref = c2 if c2 is not None else c1
    if best is not None and ref is not None:
        out.append(("Total value of flexibility vs. price cap", ref - best, f"{'2' if c2 is not None else '1'} − best"))
    return out
