"""Country flexibility scorecard: NL, DE, FR, IE, ES.

Every populated cell carries a source. Where no sourced figure could be found
the value is None and the cell carries a note explaining what was looked for.
Researched November 2026. Figures are NOT fetched live: they come from
published reports (PDFs / press releases) that were read and transcribed.
"""
from __future__ import annotations

import pandas as pd

COUNTRIES = ["Netherlands", "Germany", "France", "Ireland", "Spain"]

METRICS = [
    "EV stock (plug-in cars)",
    "Heat pump stock",
    "Home battery stock",
    "Smart meter rollout",
    "Household access to flexibility / balancing markets",
]

SOURCES = {
    "ACEA26": (
        "ACEA, 'Vehicles on European roads', January 2026 edition (2024 data): "
        "cars by power source (% share, p.15) and car fleet size (p.5)",
        "https://www.acea.auto/files/ACEA_Report-%E2%80%93-Vehicles_on_European_roads_2026.pdf",
    ),
    "KBA26": (
        "KBA vehicle stock at 1 Jan 2026, as reported by electrive.net (27 Feb 2026)",
        "https://www.electrive.net/2026/02/27/endlich-ueber-zwei-millionen-elektroautos-auf-deutschen-strassen/",
    ),
    "EHPA25": (
        "EHPA, European Heat Pump Market Report 2025, executive summary, Figure 4 "
        "'Stock of heat pumps in 2024, by country'",
        "https://www.ehpa.org/wp-content/uploads/2025/07/EHPA-Market-Report-2025-executive-summary.pdf",
    ),
    "EMA26": (
        "EMA Energiewelt, 'Batteriespeicher Q1 2026' (citing Battery Charts / RWTH ISEA and BSW-Solar)",
        "https://ema-energiewelt.de/wissen/batteriespeicher-rekord-q1-2026-grossspeicher-heimspeicher",
    ),
    "SOLSERV26": (
        "Solarserver, 'Batteriekapazität in Deutschland steigt auf 29,8 GWh' (6 Jul 2026, "
        "citing 1KOMMA5° analysis of Battery Charts)",
        "https://www.solarserver.de/2026/07/06/batteriekapazitaet-in-deutschland-waechst-auf-298-gwh-rekordtempo-beim-speicherausbau/",
    ),
    "SPE25": (
        "SolarPower Europe, EU Battery Storage Market Review 2025",
        "https://www.infobuildenergia.it/wp-content/uploads/2026/01/EU_Battery_Storage_Market_Review_2025_Report_Final_1c5ecc5560.pdf",
    ),
    "SMARTEN25": (
        "smartEn, 2025 Market Monitor for Demand Side Flexibility (country profiles pp.21-28)",
        "https://smarten.eu/wp-content/uploads/2026/01/Market-Monitor-2025.pdf",
    ),
    "ACER25": (
        "ACER-CEER, 'Rewarding Flexibility' 2025 retail monitoring report, Figure 6 "
        "(smart meter roll-out and dynamic-contract uptake bands, 2024) and footnote 12",
        "https://www.ceer.eu/wp-content/uploads/2025/11/ACER-CEER-2025-Retail-monitoring.pdf",
    ),
    "ESB25": (
        "ESB Networks newsroom, 'ESB Networks installs over 2 million smart meters' (2025)",
        "https://www.esbnetworks.ie/about-us/newsroom/article/esb-networks-reaches-milestone-of-over-two-million-smart-meters-installed-nationwide-as-part-of-the-national-smart-metering-programme",
    ),
    "CRU24": (
        "CRU, National Energy Demand Strategy Decision Paper (CRU202467, 25 Jul 2024)",
        "https://consult.cru.ie/en/system/files/materials/153/National%20Energy%20Demand%20Strategy%20Decision%20Paper_1.pdf",
    ),
}

# ACEA published shares (% of car fleet, 2024) and fleet size (2024).
ACEA_SHARES = {  # country: (BEV %, PHEV %, car fleet 2024)
    "Netherlands": (6.1, 4.1, 9_621_272),
    "Germany": (3.3, 2.0, 49_339_166),
    "France": (2.8, 1.8, 39_738_933),
    "Ireland": (3.1, 1.5, 2_474_281),
    "Spain": (0.8, 1.0, 26_469_462),
}


def _ev_cell(country: str) -> dict:
    bev, phev, fleet = ACEA_SHARES[country]
    n = (bev + phev) / 100 * fleet
    note = (
        f"BEV {bev}% + PHEV {phev}% of {fleet:,} cars (2024). Count derived by multiplying "
        "ACEA's rounded shares by fleet size, so approx. ±0.1 pp."
    )
    if country == "Germany":
        note += " Newer: KBA counted 2,034,260 BEVs alone at 1 Jan 2026."
    return {
        "value": round(n, -3),
        "display": f"≈{n / 1e6:.2f} m ({bev + phev:.1f}% of cars)" if n >= 1e6 else f"≈{n / 1e3:,.0f} k ({bev + phev:.1f}% of cars)",
        "year": "2024",
        "sources": ["ACEA26"] + (["KBA26"] if country == "Germany" else []),
        "note": note,
    }


HEAT_PUMPS = {"Netherlands": 679_000, "Germany": 2_274_000, "France": 6_554_000, "Ireland": 154_000, "Spain": 1_699_000}


def _hp_cell(country: str) -> dict:
    v = HEAT_PUMPS[country]
    note = "All heat pump types incl. reversible air-to-air units (which inflate FR/ES vs. heating-only counts)."
    if country == "Ireland":
        note += " EHPA notes Irish data are 2024 figures assumed unchanged in its series."
    return {
        "value": v,
        "display": f"{v / 1e6:.2f} m" if v >= 1e6 else f"{v / 1e3:,.0f} k",
        "year": "2024",
        "sources": ["EHPA25"],
        "note": note,
    }


BATTERY = {
    "Germany": {
        "value": 2_500_000,
        "display": "≈2.5 m systems (≈22 GWh home)",
        "year": "Q1–Q2 2026",
        "sources": ["EMA26", "SOLSERV26"],
        "note": "≈2.5 m battery systems in total (BSW-Solar, end-Mar 2026; overwhelmingly home units). "
        "≈22 GWh of ≈29.8 GWh installed capacity is private home storage (Battery Charts, Jul 2026).",
    },
    "Netherlands": {
        "value": None,
        "display": "",
        "year": "",
        "sources": ["SPE25"],
        "note": "No sourced national stock figure found. SolarPower Europe reports the Dutch behind-the-meter "
        "segment added almost 1 GWh in 2025 (annual flow, not stock).",
    },
    "France": {
        "value": None,
        "display": "",
        "year": "",
        "sources": [],
        "note": "No sourced national stock figure for residential batteries found (only partial quarterly "
        "connection counts in secondary press).",
    },
    "Ireland": {
        "value": None,
        "display": "",
        "year": "",
        "sources": [],
        "note": "No sourced national count of domestic batteries found; SEAI publishes solar PV grant "
        "counts but not battery stock.",
    },
    "Spain": {
        "value": None,
        "display": "",
        "year": "",
        "sources": ["SPE25"],
        "note": "No sourced residential stock figure found. SolarPower Europe reports Spain's residential "
        "battery market shrank 60% in 2025 after Next Generation EU funds expired.",
    },
}

SMART_METERS = {
    "Netherlands": ("89%", 89, "2025", ["SMARTEN25", "ACER25"], "ACER 2024 band: 80–100%."),
    "Germany": ("4%", 4, "2025", ["SMARTEN25", "ACER25"],
                "ACER 2024 band: 0–10%. Statutory targets 50% by 2028, 95% by 2030; 20% by 2025 target missed."),
    "France": ("94%", 94, "2025", ["SMARTEN25", "ACER25"], "ACER 2024 band: 80–100%."),
    "Ireland": (">80% of households", 80, "2025", ["ESB25", "ACER25"],
                "Over 2 million smart meters installed; 'more than four out of five households'. ACER 2024 band: 80–100%."),
    "Spain": ("≈100% (complete)", 100, "2025", ["SMARTEN25", "ACER25"],
              "smartEn: 'smart meter rollout is complete'. ACER 2024 band: 80–100%."),
}

FLEX_ACCESS = {
    "France": ("Yes — open", 3, ["SMARTEN25"],
               "Independent aggregators can participate in all markets without a BRP agreement; NEBCO opens "
               "wholesale (incl. demand turn-up); DSF has its own capacity-market allocation. EV/V2G offers "
               "established; heat pumps not yet in flex programmes. Suppliers >200k customers must offer "
               "dynamic tariffs from July 2026."),
    "Netherlands": ("Partial", 2, ["SMARTEN25", "ACER25"],
                    "Aggregators recognised but need a BRP agreement for aFRR/mFRR; no independent-aggregator "
                    "wholesale access; GOPACS for DSO congestion. Dynamic tariffs used by 4% of households; "
                    "Energy Act requires suppliers to offer them from Jan 2026."),
    "Germany": ("Partial", 2, ["SMARTEN25"],
                "Broad TSO markets (FCR, aFRR via PICASSO, mFRR via MARI); aggregators need BRP acknowledgement "
                "and a supplier compensation agreement for wholesale. §14a EnWG controllable loads. Dynamic tariff "
                "uptake ~1%, constrained by 4% smart meter rollout."),
    "Spain": ("Limited", 1, ["SMARTEN25", "ACER25"],
              "Independent aggregation not recognised (Nov 2025 Royal Decree omitted it); aFRR has a 100 MW "
              "minimum portfolio; no FCR market. Households do face hourly prices via the regulated PVPC "
              "tariff (≈40% of households per smartEn; ACER cites 29% on regulated dynamic contracts)."),
    "Ireland": ("Limited", 1, ["CRU24", "ACER25"],
                "CRU (2024) estimates ~5% of daily demand is flexible and is still developing licences for "
                "aggregation/demand response and home-energy-management services. ACER reports no dynamic "
                "contracts offered in Ireland in 2024. Not covered by smartEn's 2025 monitor."),
}


def build() -> dict:
    """Return {country: {metric: cell}}."""
    out = {}
    for c in COUNTRIES:
        sm = SMART_METERS[c]
        fa = FLEX_ACCESS[c]
        out[c] = {
            METRICS[0]: _ev_cell(c),
            METRICS[1]: _hp_cell(c),
            METRICS[2]: BATTERY[c],
            METRICS[3]: {"value": sm[1], "display": sm[0], "year": sm[2], "sources": sm[3], "note": sm[4]},
            METRICS[4]: {"value": fa[1], "display": fa[0], "year": "2025", "sources": fa[2], "note": fa[3]},
        }
    return out


def display_table(sc: dict) -> pd.DataFrame:
    rows = []
    for c in COUNTRIES:
        r = {"Country": c}
        for m in METRICS:
            cell = sc[c][m]
            r[m] = cell["display"] if cell["display"] else "— (no sourced figure)"
        rows.append(r)
    return pd.DataFrame(rows).set_index("Country")


def long_table(sc: dict) -> pd.DataFrame:
    rows = []
    for c in COUNTRIES:
        for m in METRICS:
            cell = sc[c][m]
            rows.append({
                "Country": c,
                "Metric": m,
                "Value": cell["display"] or "",
                "Data year": cell["year"],
                "Note": cell["note"],
                "Sources": "; ".join(cell["sources"]),
            })
    return pd.DataFrame(rows)
