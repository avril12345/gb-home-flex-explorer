"""Live public data fetchers for GB Home Flex Explorer.

Every fetcher either returns real, parsed data together with its source
metadata, or raises DataSourceError. There are deliberately NO fallback or
default numbers here: if a source cannot be fetched or parsed, the app stops
and says so.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

USER_AGENT = "GB-Home-Flex-Explorer/1.0 (public-data research tool)"
TIMEOUT = 45

OFGEM_CAP_URL = (
    "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/"
    "energy-price-cap-unit-rates-and-standing-charges"
)
# Ofgem letter confirming the 2026 Typical Domestic Consumption Values (TDCV).
OFGEM_TDCV_URL = (
    "https://www.ofgem.gov.uk/sites/default/files/2026-06/"
    "Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf"
)
ELEXON_MID_URL = "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index"
ELEXON_DOCS_URL = "https://bmrs.elexon.co.uk/api-documentation/endpoint/balancing/pricing/market-index"


class DataSourceError(RuntimeError):
    """Raised when a public source cannot be fetched or parsed."""


@dataclass
class Source:
    name: str
    url: str
    retrieved_utc: str
    detail: str = ""
    extra: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get(url: str, **kw) -> requests.Response:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise DataSourceError(f"Could not reach {url}: {e}") from e
    if r.status_code != 200:
        raise DataSourceError(f"{url} returned HTTP {r.status_code}: {r.text[:300]}")
    return r


# --------------------------------------------------------------------------
# Ofgem price cap
# --------------------------------------------------------------------------
def fetch_ofgem_price_cap() -> tuple[dict, Source]:
    """Parse the GB-average Direct Debit cap rates for the *current* cap period.

    The Ofgem page shows a table with the previous and current periods side by
    side. We locate the current period from the heading
    "Energy price cap from <start> to <end> <year>" and take the matching
    (last) column for electricity and gas.
    """
    html = _get(OFGEM_CAP_URL).text
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).replace(" ", " ")

    m = re.search(r"Energy price cap from (\d{1,2} \w+ to \d{1,2} \w+ \d{4})", text)
    if not m:
        raise DataSourceError("Ofgem page layout changed: current cap period heading not found.")
    period = m.group(1)

    m_cap = re.search(r"the price cap will be £([\d,]+) per year", text)

    def block(fuel_start: str, fuel_end: str | None) -> tuple[float, float]:
        i = text.find(f" {fuel_start} ", text.find("Average electricity and gas unit prices"))
        if i < 0:
            raise DataSourceError(f"Ofgem page layout changed: '{fuel_start}' block not found.")
        j = text.find(f" {fuel_end} ", i + 1) if fuel_end else text.find("Figures are rounded", i)
        seg = text[i:j if j > 0 else i + 600]
        units = re.findall(r"([\d.]+) pence per kWh", seg)
        scs = re.findall(r"([\d.]+) pence daily standing charge", seg)
        if not units or not scs:
            raise DataSourceError(f"Ofgem page layout changed: rates for {fuel_start} not parsed.")
        # Last column = current period.
        return float(units[-1]), float(scs[-1])

    e_unit, e_sc = block("Electricity", "Gas")
    g_unit, g_sc = block("Gas", None)

    vat_note = ""
    vm = re.search(r"(There is no VAT on electricity[^.]*\.)", text)
    if vm:
        vat_note = vm.group(1)
    rounding = re.search(r"(Figures are rounded[^.]*\.)", text)

    # Sanity bounds: reject obviously mis-parsed values rather than use them.
    if not (5 < e_unit < 100 and 10 < e_sc < 150 and 1 < g_unit < 30 and 5 < g_sc < 100):
        raise DataSourceError(
            f"Parsed Ofgem values look implausible (elec {e_unit}p/{e_sc}p, gas {g_unit}p/{g_sc}p)."
        )

    data = {
        "period": period,
        "elec_unit_p_kwh": e_unit,
        "elec_sc_p_day": e_sc,
        "gas_unit_p_kwh": g_unit,
        "gas_sc_p_day": g_sc,
        "annual_typical_bill_gbp": float(m_cap.group(1).replace(",", "")) if m_cap else None,
        "no_vat_on_electricity": bool(vm),
        "vat_note": vat_note,
        "rounding_note": rounding.group(1) if rounding else "",
    }
    src = Source(
        name=f"Ofgem — Energy price cap unit rates and standing charges ({period}), "
        "GB average, Direct Debit",
        url=OFGEM_CAP_URL,
        retrieved_utc=_now(),
        detail=" ".join(x for x in [data["rounding_note"], vat_note] if x),
    )
    return data, src


def fetch_ofgem_tdcv() -> tuple[dict, Source]:
    """Read the current medium Typical Domestic Consumption Values from Ofgem's letter."""
    import io

    import pypdf

    pdf = _get(OFGEM_TDCV_URL).content
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        text = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in reader.pages))
    except Exception as e:  # noqa: BLE001
        raise DataSourceError(f"Could not read Ofgem TDCV PDF: {e}") from e
    m = re.search(
        r"2026 TDCV of ([\d,]+) kwh of electricity, ([\d,]+) kWh of gas and ([\d,]+) kWh "
        r"for multi-register",
        text,
        flags=re.I,
    )
    if not m:
        raise DataSourceError("Ofgem TDCV letter layout changed: 2026 TDCV sentence not found.")
    to_i = lambda s: int(s.replace(",", ""))  # noqa: E731
    data = {
        "elec_kwh": to_i(m.group(1)),
        "gas_kwh": to_i(m.group(2)),
        "multi_register_kwh": to_i(m.group(3)),
    }
    src = Source(
        name="Ofgem — Energy price cap update from 1 July 2026 (revised TDCV letter): "
        "2026 medium Typical Domestic Consumption Values",
        url=OFGEM_TDCV_URL,
        retrieved_utc=_now(),
        detail=f'Quoted: "{m.group(0)}"',
    )
    return data, src


# --------------------------------------------------------------------------
# Elexon BMRS Market Index Data (half-hourly wholesale price)
# --------------------------------------------------------------------------
def _fetch_mid_chunk(start: datetime, end: datetime) -> list[dict]:
    params = {
        "from": start.strftime("%Y-%m-%dT%H:%MZ"),
        "to": end.strftime("%Y-%m-%dT%H:%MZ"),
        "dataProviders": "APXMIDP",
        "format": "json",
    }
    last_err = None
    for _ in range(3):
        try:
            r = requests.get(
                ELEXON_MID_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            )
            if r.status_code == 200:
                return r.json().get("data", [])
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_err = str(e)
    raise DataSourceError(f"Elexon MID request {params['from']}→{params['to']} failed: {last_err}")


def fetch_elexon_mid_year(days: int = 365) -> tuple[pd.DataFrame, Source]:
    """Fetch the most recent `days` complete days of APX Market Index prices.

    Returns a DataFrame indexed by UTC start time with columns
    price_gbp_mwh, volume_mwh, settlement_date, settlement_period.
    """
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    # API limit: max 7 days per request (inclusive), so use 6-day windows.
    windows = []
    t = start
    while t < end:
        u = min(t + timedelta(days=6), end)
        windows.append((t, u))
        t = u
    with ThreadPoolExecutor(max_workers=6) as ex:
        chunks = list(ex.map(lambda w: _fetch_mid_chunk(*w), windows))
    rows = [r for c in chunks for r in c]
    if not rows:
        raise DataSourceError("Elexon MID returned no data for the requested year.")
    df = pd.DataFrame(rows)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = (
        df[df["dataProvider"] == "APXMIDP"]
        .drop_duplicates("startTime")
        .set_index("startTime")
        .sort_index()
    )
    df = df[(df.index >= start) & (df.index < end)]
    df = df.rename(
        columns={
            "price": "price_gbp_mwh",
            "volume": "volume_mwh",
            "settlementDate": "settlement_date",
            "settlementPeriod": "settlement_period",
        }
    )[["price_gbp_mwh", "volume_mwh", "settlement_date", "settlement_period"]]

    full = pd.date_range(start, end, freq="30min", inclusive="left", tz="UTC")
    expected = len(full)
    # Periods with zero traded volume are reported with price 0 — treat as missing.
    zero_vol = int((df["volume_mwh"] <= 0).sum())
    df.loc[df["volume_mwh"] <= 0, "price_gbp_mwh"] = float("nan")
    df = df.reindex(full)
    missing = int(df["price_gbp_mwh"].isna().sum())
    if missing > 0.05 * expected:
        raise DataSourceError(
            f"Elexon MID data has {missing} of {expected} half-hours missing (>5%); "
            "refusing to model on an incomplete year."
        )
    # Small gaps: linear interpolation in time (documented assumption).
    df["price_gbp_mwh"] = df["price_gbp_mwh"].interpolate(limit_direction="both")
    df.index.name = "start_utc"

    src = Source(
        name="Elexon BMRS — Market Index Data (MID), provider APXMIDP, half-hourly",
        url=ELEXON_DOCS_URL,
        retrieved_utc=_now(),
        detail=(
            f"{start:%Y-%m-%d} to {(end - timedelta(days=1)):%Y-%m-%d} (UTC). "
            f"{expected} half-hours expected; {missing} missing/zero-volume "
            f"({zero_vol} zero-volume) filled by linear interpolation."
        ),
        extra={"missing": missing, "expected": expected, "api": ELEXON_MID_URL},
    )
    return df, src
