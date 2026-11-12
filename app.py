"""GB Home Flex Explorer — Streamlit app.

Run:  streamlit run app.py
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_sources as ds
import economics as econ
import model as m
import scorecard as sc_mod
import ui
from memo_pdf import build_memo

st.set_page_config(page_title="GB Home Flex Explorer", page_icon="⚡", layout="wide")

# Validated categorical palette led by brand red (fixed order, never cycled).
C_TOU, C_CAP, C_HOUSE, C_EV, C_BAT = (ui.CHART[k] for k in ("tou", "cap", "house", "ev", "bat"))


# ---------------------------------------------------------------------------
# Data loading — fail loudly, never substitute numbers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_cap():
    return ds.fetch_ofgem_price_cap()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_tdcv():
    return ds.fetch_ofgem_tdcv()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_prices():
    return ds.fetch_elexon_mid_year(365)


def fetch_or_stop(fn, label):
    try:
        with st.spinner(f"Fetching {label}…"):
            return fn()
    except ds.DataSourceError as e:
        st.error(
            f"**Could not fetch {label}.** The app has stopped rather than use invented or default "
            f"numbers.\n\nDetail: `{e}`"
        )
        st.stop()


ui.apply_theme()
ui.hero()

cap, cap_src = fetch_or_stop(load_cap, "the Ofgem price cap (ofgem.gov.uk)")
tdcv, tdcv_src = fetch_or_stop(load_tdcv, "Ofgem typical domestic consumption values")
prices, price_src = fetch_or_stop(load_prices, "a year of half-hourly prices from Elexon BMRS")

# ---------------------------------------------------------------------------
# Sidebar — every assumption is editable
# ---------------------------------------------------------------------------
sb = st.sidebar
sb.header("⚙️ Your settings")
sb.caption("Start with the defaults (a typical British home), then change anything. Hover the ⓘ icons for where each number comes from.")

with sb.expander("🏠 Household", expanded=True):
    annual_kwh = st.number_input(
        "Annual electricity use (kWh)", 500, 15000, int(tdcv["elec_kwh"]), 100,
        help=f"Default = Ofgem 2026 medium TDCV ({tdcv['elec_kwh']:,} kWh). Gas TDCV {tdcv['gas_kwh']:,} kWh is not modelled.",
    )

with sb.expander("💷 Price cap tariff", expanded=False):
    cap_unit = st.number_input("Unit rate (p/kWh)", 0.0, 200.0, float(cap["elec_unit_p_kwh"]), 0.01,
                               help=f"Ofgem, {cap['period']}, GB average Direct Debit.")
    cap_sc = st.number_input("Standing charge (p/day)", 0.0, 300.0, float(cap["elec_sc_p_day"]), 0.01)

with sb.expander("⏱️ Time-of-use tariff", expanded=False):
    tou_type_label = st.radio(
        "ToU design", ["Wholesale-tracking (half-hourly)", "Static 3-band"], index=0,
        help="Wholesale-tracking: cap unit rate + (half-hourly wholesale − household-weighted average wholesale). "
        "Static: three fixed bands. Defaults are derived from the wholesale data.",
    )
    tou_sc = st.number_input("ToU standing charge (p/day)", 0.0, 300.0, float(cap["elec_sc_p_day"]), 0.01,
                             help="Default: same as the price cap.")
    tou_pass = 1.0
    tou_vat = 0.0
    floor = cap_ceiling = None
    if tou_type_label.startswith("Wholesale"):
        tou_pass = st.slider("Wholesale pass-through", 0.0, 2.0, 1.0, 0.05,
                             help="Multiplier on wholesale deviations (1.0 = pass through 1:1; >1 adds a shape premium, e.g. network peak charges).")
        tou_vat = st.number_input("VAT on wholesale deviation (%)", 0.0, 20.0,
                                  0.0 if cap["no_vat_on_electricity"] else 5.0, 0.5,
                                  help="Ofgem: " + (cap["vat_note"] or "5% VAT on domestic electricity.")) / 100
        if st.checkbox("Floor unit rate", value=False):
            floor = st.number_input("Floor (p/kWh)", -100.0, 100.0, 0.0, 0.5)
        if st.checkbox("Cap unit rate", value=False):
            cap_ceiling = st.number_input("Ceiling (p/kWh)", 0.0, 300.0, 100.0, 1.0)

with sb.expander("🚗 Electric car", expanded=True):
    ev_on = st.checkbox("Add EV", value=True)
    ev_kwh = st.number_input("Charging energy (kWh/day, at the meter)", 0.0, 50.0, 7.0, 0.5)
    ev_kw = st.number_input("Charger power (kW)", 1.0, 22.0, 7.0, 0.1)
    ev_plug = st.slider("Plug-in time (local)", 12.0, 23.5, 18.0, 0.5, format="%.1f h")
    ev_dep = st.slider("Departure time next morning (local)", 0.0, 11.5, 7.0, 0.5, format="%.1f h")

with sb.expander("🔋 Home battery", expanded=True):
    bat_on = st.checkbox("Add battery", value=True)
    bat_kwh = st.number_input("Usable capacity (kWh)", 0.0, 50.0, 10.0, 0.5)
    bat_kw = st.number_input("Max charge/discharge power (kW)", 0.5, 20.0, 5.0, 0.5)
    bat_rte = st.slider("Round-trip efficiency", 0.5, 1.0, 0.90, 0.01)
    bat_deg = st.number_input("Degradation cost (p per kWh discharged)", 0.0, 50.0, 0.0, 0.5)
    bat_exp = st.checkbox("Allow export to grid", value=False)
    bat_exp_share = st.slider("Export price as share of import rate", 0.0, 1.0, 0.5, 0.05, disabled=not bat_exp) if bat_exp else 0.0

with sb.expander("🧾 Equipment costs & payback", expanded=False):
    bat_cost = st.number_input(
        "Battery installed cost (£)", 0.0, 50000.0, econ.DEFAULT_BATTERY_COST_GBP, 250.0,
        help="Default £5,750 = midpoint of an indicative £4,500–£7,000 UK installed range for a 10 kWh battery "
        "(Switch Together, citing installer data). 0% VAT applies to home batteries until 31 Mar 2027 (HMRC).",
    )
    if bat_kwh != econ.DEFAULT_BATTERY_REF_KWH:
        st.caption(f"⚠ The default cost is for a {econ.DEFAULT_BATTERY_REF_KWH:.0f} kWh battery. Adjust it for {bat_kwh:g} kWh.")
    bat_life = st.number_input("Battery lifetime (years)", 1, 30, econ.DEFAULT_BATTERY_LIFE_YEARS, 1,
                               help="Assumption (not sourced). Savings stop after this many years.")
    ev_extra = st.number_input(
        "Extra hardware cost for smart EV charging (£)", 0.0, 5000.0, econ.DEFAULT_SMART_CHARGER_EXTRA_GBP, 50.0,
        help="Default £0: since 30 June 2022 every home charge point sold in GB must be smart "
        "(Smart Charge Points Regulations 2021), so smart charging needs no extra kit. Raise this if an upgrade is needed.",
    )
    ev_life = st.number_input("Charger lifetime (years)", 1, 30, 10, 1, help="Assumption (not sourced).")
    disc = st.number_input("Discount rate (real, %/yr)", 0.0, 20.0, econ.DEFAULT_DISCOUNT_RATE * 100, 0.5,
                           help="Default 3% = HM Treasury Green Book review (2026). A household might use its "
                           "mortgage or savings rate instead.") / 100
    growth = st.number_input("Change in annual savings (real, %/yr)", -20.0, 20.0, 0.0, 0.5,
                             help="Assumption, default 0%: savings held flat. Use a negative value for battery "
                             "degradation or narrowing price spreads, positive for widening spreads.") / 100

# Load shape editor (main area, collapsed)
shape_state = st.session_state.setdefault("hourly_shape", list(m.DEFAULT_HOURLY_SHAPE))
month_state = st.session_state.setdefault("monthly_factor", list(m.DEFAULT_MONTHLY_FACTOR))

tab_gb, tab_sc, tab_src = st.tabs(["🏠  Your home's savings", "🌍  Europe scorecard", "📚  Sources & method"])

# ===========================================================================
# TAB 1 — GB household model
# ===========================================================================
with tab_gb:
    with st.expander("📖 New to this? Jargon buster"):
        ui.glossary()
    with st.expander("📈 Advanced: when during the day the household uses electricity (editable)"):
        st.caption(
            "A stylised daily shape, not a sourced dataset: Elexon's domestic Profile Class 1 data are not openly "
            "available through the BMRS API. Weights are relative and rescaled so the year sums to the annual kWh."
        )
        c1, c2 = st.columns(2)
        hs = c1.data_editor(
            pd.DataFrame({"Hour (local)": [f"{h:02d}:00" for h in range(24)], "Relative weight": shape_state}),
            hide_index=True, disabled=["Hour (local)"], key="hs_editor", height=880,
        )
        mf = c2.data_editor(
            pd.DataFrame({"Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                          "Seasonal factor": month_state}),
            hide_index=True, disabled=["Month"], key="mf_editor",
        )
        if c2.button("Reset load shape to defaults"):
            st.session_state["hourly_shape"] = list(m.DEFAULT_HOURLY_SHAPE)
            st.session_state["monthly_factor"] = list(m.DEFAULT_MONTHLY_FACTOR)
            for k in ("hs_editor", "mf_editor"):
                st.session_state.pop(k, None)
            st.rerun()
    hourly_shape = [max(0.0, float(x)) for x in hs["Relative weight"].fillna(0)]
    monthly_factor = [max(0.0, float(x)) for x in mf["Seasonal factor"].fillna(0)]
    if sum(hourly_shape) <= 0 or sum(monthly_factor) <= 0:
        st.error("Load shape weights must not all be zero.")
        st.stop()

    a = m.Assumptions(
        annual_kwh=annual_kwh, hourly_shape=hourly_shape, monthly_factor=monthly_factor,
        cap_unit_p=cap_unit, cap_sc_p_day=cap_sc,
        tou_type="wholesale" if tou_type_label.startswith("Wholesale") else "static",
        tou_sc_p_day=tou_sc, tou_pass_through=tou_pass, tou_vat=tou_vat,
        tou_floor_p=floor, tou_cap_p=cap_ceiling, static_bands=None,
        ev_on=ev_on, ev_kwh_day=ev_kwh, ev_charger_kw=ev_kw, ev_plugin_hour=ev_plug, ev_depart_hour=ev_dep,
        bat_on=bat_on, bat_kwh=bat_kwh, bat_kw=bat_kw, bat_rte=bat_rte,
        bat_allow_export=bat_exp, bat_export_share=bat_exp_share, bat_degradation_p=bat_deg,
    )

    if a.tou_type == "static":
        house_tmp = m.household_profile(prices.index, a)
        derived = m.static_band_defaults(prices, house_tmp, a)
        with st.expander("Static 3-band ToU rates", expanded=True):
            st.caption("Defaults = household-weighted average of the wholesale-tracking tariff within each band, so they are derived from the fetched data.")
            b1, b2, b3 = st.columns(3)
            op = b1.number_input("Off-peak rate (p/kWh)", -50.0, 200.0, derived["offpeak"][2], 0.1)
            op_s, op_e = b1.slider("Off-peak hours", 0.0, 24.0, (derived["offpeak"][0], derived["offpeak"][1]), 0.5)
            pk = b2.number_input("Peak rate (p/kWh)", -50.0, 200.0, derived["peak"][2], 0.1)
            pk_s, pk_e = b2.slider("Peak hours", 0.0, 24.0, (derived["peak"][0], derived["peak"][1]), 0.5)
            dy = b3.number_input("All other hours (p/kWh)", -50.0, 200.0, derived["day"][2], 0.1)
        a.static_bands = {"offpeak": (op_s, op_e, op), "peak": (pk_s, pk_e, pk), "day": (0, 24, dy)}

    @st.cache_data(show_spinner=False, max_entries=32)
    def _run(_prices, key, a_dict):
        return m.run_scenarios(_prices, m.Assumptions(**a_dict))

    with st.spinner("Optimising EV and battery schedules over 365 days…"):
        res, extra = _run(prices, (price_src.retrieved_utc, len(prices)), a.__dict__.copy())
    series = extra["series"]
    flex = m.flexibility_values(res)

    # Headline numbers
    t = res["total_gbp"]
    ref_key = next(k for k in t.index if k.startswith("2.")) if ev_on else next(k for k in t.index if k.startswith("1."))
    best_key = t.index[-1]
    total_flex = next((v for (lbl, v, _) in flex if lbl.startswith("Total")), 0.0)
    kit = " and ".join(x for x, on in (("an electric car", ev_on), ("a home battery", bat_on)) if on) or "no extra equipment"
    ui.summary(
        f"For a home using <b>{annual_kwh:,} kWh</b> a year with {kit}, electricity costs "
        f"<b>£{t[ref_key]:,.0f}</b> a year on the price cap. Switching to a time-of-use tariff and letting the "
        f"equipment pick the cheapest hours brings it to <b>£{t[best_key]:,.0f}</b>: a saving of "
        f"<b>£{total_flex:,.0f} a year</b> (about £{total_flex / 12:,.0f} a month)."
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💷 On the price cap", f"£{t[ref_key]:,.0f}/yr", help=ref_key)
    k2.metric("⚡ Smart tariff + kit", f"£{t[best_key]:,.0f}/yr", help=best_key)
    k3.metric("✅ You save", f"£{total_flex:,.0f}/yr", help="Price-cap cost minus best time-of-use cost. Bill savings only.")
    k4.metric("📊 Avg wholesale price", f"{series['wholesale_p'].mean():.1f}p/kWh",
              help="Simple time-weighted mean of Elexon APX MID over the last 365 days, £/MWh ÷ 10.")

    c_left, c_right = st.columns([3, 2])
    with c_left:
        ui.section("1", "What you'd pay in a year", "Each bar is one way of running the same home.")
        fig = go.Figure(go.Bar(
            y=res.index[::-1], x=res["total_gbp"][::-1], orientation="h",
            marker=dict(color=[C_CAP if "Price cap" in i else C_TOU for i in res.index[::-1]], line=dict(width=0)),
            text=[f"£{v:,.0f}" for v in res["total_gbp"][::-1]], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>£%{x:,.0f} per year<extra></extra>",
        ))
        fig.update_layout(height=60 + 46 * len(res), margin=dict(l=0, r=60, t=10, b=60), bargap=0.35,
                          xaxis=dict(title="£ per year (energy + standing charge)", gridcolor="rgba(128,128,128,0.15)"),
                          yaxis=dict(title=None), showlegend=False)
        st.plotly_chart(fig, width="stretch")
        st.caption("🔵 Blue = fixed price cap · 🔴 Red = time-of-use tariff. Shorter bar = cheaper.")
    with c_right:
        ui.section("£", "Where the savings come from", "Each step on its own.")
        st.dataframe(
            pd.DataFrame([{"Step": l, "£ / year": round(v, 0), "Scenarios": s} for l, v, s in flex]),
            hide_index=True, width="stretch",
            column_config={"£ / year": st.column_config.NumberColumn(format="£%d")},
        )
        st.caption(
            "Bill savings only: hardware cost (EV charger, battery) is not netted off. On the flat price cap "
            "shifting load is worth nothing, so a battery there would only lose energy to round-trip losses."
        )

    # ---------------- Equipment cost & payback ----------------
    ui.section("2", "Is the equipment worth buying?", "Savings compared with what the kit costs. Change costs in the sidebar under 🧾.")
    tot = lambda p: next((t[k] for k in t.index if k.startswith(p)), None)  # noqa: E731
    invest = []
    if ev_on and tot("4.") is not None:
        invest.append(("Smart EV charging", ev_extra, tot("4.") - tot("5."), int(ev_life), C_EV))
    if bat_on and tot("6.") is not None:
        base = tot("5.") if ev_on else tot("3.")
        invest.append(("Home battery", bat_cost, base - tot("6."), int(bat_life), C_BAT))

    if not invest:
        st.info("Turn on the EV and/or battery in the sidebar to see payback.")
    else:
        horizon = max(20, max(i[3] for i in invest))
        rows, apps = [], []
        for name, cost, saving, life, color in invest:
            ap = econ.appraise(cost, saving, life, disc, growth, horizon)
            apps.append((name, ap, life, color))
            rows.append({
                "Investment": name,
                "Upfront cost": cost,
                "Saving in year 1": saving,
                "Payback": econ.fmt_years(ap["simple_payback"], life),
                f"Payback at {disc * 100:g}%": econ.fmt_years(ap["discounted_payback"], life),
                "Life (yrs)": life,
                "Lifetime gain (NPV)": ap["npv"],
                "Break-even cost": econ.break_even_cost(saving, life, disc, growth),
            })
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width="stretch",
            column_config={
                "Upfront cost": st.column_config.NumberColumn(format="£%d"),
                "Saving in year 1": st.column_config.NumberColumn(format="£%d"),
                "Lifetime gain (NPV)": st.column_config.NumberColumn(format="£%d", help="Discounted savings over the lifetime minus upfront cost. Positive = worth it."),
                "Break-even cost": st.column_config.NumberColumn(format="£%d", help="The most you could pay up front and still break even over the lifetime (discounted)."),
            },
        )
        for name, ap, life, _ in apps:
            if ap["cost"] == 0:
                st.markdown(f"- **{name}:** no extra hardware needed, so the £{ap['saving_y1']:,.0f}/yr saving is free money.")
            elif ap["pays_back"]:
                st.markdown(f"- **{name}:** pays for itself in about **{ap['discounted_payback']:.1f} years**, "
                            f"well within its {life}-year life. Net gain over its life: **£{ap['npv']:,.0f}** (in today's money).")
            else:
                be = econ.break_even_cost(ap["saving_y1"], life, disc, growth)
                st.markdown(f"- **{name}:** does **not** pay for itself on tariff savings alone. Over {life} years it "
                            f"recovers £{ap['npv'] + ap['cost']:,.0f} of its £{ap['cost']:,.0f} cost (in today's money). "
                            f"It would need to cost under **£{be:,.0f}**, or save about "
                            f"£{ap['cost'] / max(be / max(ap['saving_y1'], 1e-9), 1e-9):,.0f}/yr, to break even.")

        fc = go.Figure()
        for name, ap, life, color in apps:
            sr = ap["series"]
            fc.add_trace(go.Scatter(
                x=sr["year"], y=sr["cumulative_discounted"], name=name, mode="lines+markers",
                line=dict(color=color, width=2), marker=dict(size=8),
                hovertemplate="Year %{x}<br>£%{y:,.0f}<extra>" + name + "</extra>",
            ))
        fc.add_hline(y=0, line=dict(color="rgba(128,128,128,0.8)", width=1))
        fc.update_layout(
            height=320, margin=dict(l=0, r=0, t=40, b=0), hovermode="x unified",
            title=dict(text="Cumulative net position (£, today's money): below zero = still paying off", font=dict(size=14)),
            xaxis=dict(title="Years after purchase", dtick=2, gridcolor="rgba(128,128,128,0.15)"),
            yaxis=dict(gridcolor="rgba(128,128,128,0.15)", tickprefix="£"),
            legend=dict(orientation="h", y=1.12, x=0.55),
        )
        st.plotly_chart(fc, width="stretch")
        st.caption(
            "Counts only tariff bill savings. It does not include grid-service income (e.g. Demand Flexibility Service), "
            "backup-power value, maintenance, replacement inverters, or the EV itself (assumed bought anyway). "
            "Cost sources: " + "; ".join(f"[{v[0].split(' — ')[0].split(',')[0]}]({v[1]})" for v in econ.COST_SOURCES.values()) + "."
        )

    with st.expander("🔢 Full numbers for every scenario"):
        st.caption("Grid import, energy cost, standing charge and totals per year.")
        show = res.copy()
        show.columns = ["Grid import (kWh)", "Energy (£)", "Standing charge (£)", "Export credit (£)", "Degradation (£)", "Total (£)"]
        st.dataframe(show.round(0), width="stretch")
        st.download_button("Download scenario results (CSV)", show.to_csv().encode(), "gb_flex_scenarios.csv", "text/csv")

    # Example week
    ui.section("3", "Look inside a week", "Drag the slider to see how the car and battery chase the cheapest hours.")
    idx_local = series.index
    weeks = pd.date_range(idx_local[0].normalize() + timedelta(days=1), idx_local[-1] - timedelta(days=7), freq="7D")
    wk = st.select_slider("Week starting", options=list(weeks), value=weeks[len(weeks) // 2],
                          format_func=lambda d: d.strftime("%d %b %Y"))
    w = series[(series.index >= wk) & (series.index < wk + timedelta(days=7))]

    fp = go.Figure()
    fp.add_trace(go.Scatter(x=w.index, y=w["tou_p"], name="ToU unit rate", line=dict(color=C_TOU, width=2),
                            hovertemplate="%{y:.2f} p/kWh<extra>ToU</extra>"))
    fp.add_trace(go.Scatter(x=w.index, y=w["cap_p"], name="Price cap unit rate", line=dict(color=C_CAP, width=2),
                            hovertemplate="%{y:.2f} p/kWh<extra>Cap</extra>"))
    fp.update_layout(height=280, margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified",
                     title=dict(text="Unit rate (p/kWh)", font=dict(size=14)),
                     yaxis=dict(gridcolor="rgba(128,128,128,0.15)"), legend=dict(orientation="h", y=1.15, x=0.35))
    st.plotly_chart(fp, width="stretch")

    fl = go.Figure()
    fl.add_trace(go.Bar(x=w.index, y=w["house_kwh"], name="Household", marker_color=C_HOUSE,
                        hovertemplate="%{y:.2f} kWh<extra>Household</extra>"))
    if ev_on:
        fl.add_trace(go.Bar(x=w.index, y=w["ev_smart_kwh"], name="EV (smart)", marker_color=C_EV,
                            hovertemplate="%{y:.2f} kWh<extra>EV smart</extra>"))
    if bat_on:
        fl.add_trace(go.Bar(x=w.index, y=w["bat_charge_kwh"], name="Battery charging", marker_color=C_BAT,
                            hovertemplate="%{y:.2f} kWh<extra>Battery charge</extra>"))
        fl.add_trace(go.Bar(x=w.index, y=-(w["bat_discharge_kwh"] + w["bat_export_kwh"]), name="Battery discharging",
                            marker_color=C_BAT, marker_pattern_shape="/", opacity=0.75,
                            hovertemplate="%{y:.2f} kWh<extra>Battery discharge</extra>"))
    fl.update_layout(barmode="relative", height=300, margin=dict(l=0, r=0, t=30, b=0), bargap=0.05,
                     hovermode="x unified", title=dict(text="Energy per half-hour (kWh), ToU scenario with all flexibility", font=dict(size=14)),
                     yaxis=dict(gridcolor="rgba(128,128,128,0.15)"), legend=dict(orientation="h", y=1.18, x=0.2))
    st.plotly_chart(fl, width="stretch")
    st.caption("Battery discharge is drawn below zero: it displaces household and EV imports in the most expensive half-hours.")

    with st.expander("Average ToU rate by time of day (whole year)"):
        prof = series.groupby(series.index.hour + series.index.minute / 60)[["tou_p", "wholesale_p"]].mean()
        fh = go.Figure()
        fh.add_trace(go.Scatter(x=prof.index, y=prof["tou_p"], name="ToU unit rate", line=dict(color=C_TOU, width=2)))
        fh.add_hline(y=cap_unit, line=dict(color=C_CAP, width=2, dash="dot"), annotation_text="Price cap", annotation_position="top left")
        fh.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Local hour", yaxis_title="p/kWh",
                         hovermode="x unified", showlegend=False, yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
        st.plotly_chart(fh, width="stretch")

    st.markdown("##### Data used on this tab")
    st.markdown(
        f"- **Price cap:** [{cap_src.name}]({cap_src.url}), retrieved {cap_src.retrieved_utc}. "
        f"Electricity {cap['elec_unit_p_kwh']} p/kWh, {cap['elec_sc_p_day']} p/day; gas {cap['gas_unit_p_kwh']} p/kWh, "
        f"{cap['gas_sc_p_day']} p/day. _{cap_src.detail}_\n"
        f"- **Typical consumption:** [{tdcv_src.name}]({tdcv_src.url}), retrieved {tdcv_src.retrieved_utc}. {tdcv_src.detail}\n"
        f"- **Wholesale prices:** [{price_src.name}]({price_src.url}) (endpoint `{price_src.extra['api']}`), "
        f"retrieved {price_src.retrieved_utc}. {price_src.detail}"
    )

# ===========================================================================
# TAB 2 — Country scorecard
# ===========================================================================
with tab_sc:
    sc = sc_mod.build()
    ui.section("🌍", "How ready are other countries?", "Netherlands · Germany · France · Ireland · Spain")
    st.caption(
        "Latest sourced figures found (researched Nov 2026). A dash means no sourced figure was found, not zero; "
        "the note says what was searched. Figures come from published reports and are not fetched live."
    )
    tbl = sc_mod.display_table(sc)
    st.dataframe(tbl, width="stretch")

    country = st.selectbox("Notes and sources for", sc_mod.COUNTRIES)
    for metric in sc_mod.METRICS:
        cell = sc[country][metric]
        links = ", ".join(f"[{k}]({sc_mod.SOURCES[k][1]})" for k in cell["sources"]) or "none found"
        val = cell["display"] or "_blank: no sourced figure_"
        st.markdown(f"**{metric}:** {val}" + (f" ({cell['year']})" if cell["year"] else "") +
                    f"  \n{cell['note']}  \nSources: {links}")

    st.markdown("##### Export")
    author = st.text_input("Memo 'From' line (optional)", "")
    e1, e2 = st.columns(2)
    try:
        pdf_bytes = build_memo(sc, author)
        e1.download_button("Download one-page PDF memo", pdf_bytes, "flex_scorecard_memo.pdf", "application/pdf", type="primary")
    except Exception as ex:  # noqa: BLE001
        e1.error(f"PDF generation failed: {ex}")
    e2.download_button("Download scorecard with notes (CSV)", sc_mod.long_table(sc).to_csv(index=False).encode(),
                       "flex_scorecard.csv", "text/csv")

    st.markdown("##### Scorecard sources")
    for k, (name, url) in sc_mod.SOURCES.items():
        st.markdown(f"- **[{k}]** [{name}]({url})")

# ===========================================================================
# TAB 3 — Sources & method
# ===========================================================================
with tab_src:
    st.subheader("Live sources (fetched by this app)")
    for s in (cap_src, tdcv_src, price_src):
        st.markdown(f"- **{s.name}**: <{s.url}>  \n  Retrieved {s.retrieved_utc}. {s.detail}")
    st.subheader("Equipment cost & payback sources (not fetched live)")
    for name, url in econ.COST_SOURCES.values():
        st.markdown(f"- {name}: <{url}>")
    st.markdown("- Battery and charger **lifetimes** and the **change in savings over time** are assumptions, not sourced.")
    st.subheader("Method in brief")
    st.markdown(
        """
- **Window:** the last 365 complete days of Elexon *Market Index Data* (APX provider), half-hourly, converted to local GB time. Zero-volume periods are treated as missing and linearly interpolated. The app refuses to run if more than 5% of periods are missing.
- **Household:** annual kWh spread over half-hours with an editable hourly shape and monthly seasonal factor (assumption).
- **Price cap:** a flat unit rate and standing charge from the current Ofgem cap period, applied to every half-hour of the historic year.
- **Wholesale-tracking ToU:** `rate = cap rate + pass-through × (wholesale − household-weighted mean wholesale) × (1 + VAT)`. This is revenue-neutral for the baseline household, so any saving comes from *shifting* load.
- **Static ToU:** three bands; default rates are the household-weighted average of the wholesale-tracking tariff in each band.
- **EV:** a fixed energy per overnight session, plug-in to departure, at charger power. *Unmanaged* charging starts at plug-in. *Smart* charging fills the cheapest half-hours in the window.
- **Battery:** a linear programme for each local day with day-ahead price foresight. Charging cost minus avoided import is minimised, subject to capacity, power, round-trip efficiency, and end-of-day state of charge equal to the start. No export by default.
- **Value of flexibility:** differences between scenarios. Bill savings only, before hardware cost.
- **Payback:** the year-1 saving from each step (smart EV = scenario 4 − 5; battery = 5 − 6) recurs annually, changes by an editable % per year, and stops at the equipment lifetime. Simple payback = time until undiscounted savings cover the cost. Discounted payback and NPV use the real discount rate (default 3%, Green Book review 2026).

The full assumption list is in `README.md`.
"""
    )
