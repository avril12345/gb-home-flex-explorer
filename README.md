# GB Home Flex Explorer

A Streamlit app that answers two questions with public data only:

1. **What is household flexibility worth in Great Britain?** It models a typical household on the Ofgem price cap and on a time-of-use (ToU) tariff, then adds an EV and a home battery that charge in the cheapest half-hours.
2. **How ready are NL, DE, FR, IE and ES?** A sourced scorecard covering EV, heat-pump and home-battery stock, smart-meter rollout, and household access to flexibility and balancing markets. It exports as a one-page PDF memo.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The first load fetches about 60 small requests from Elexon plus two Ofgem documents, which takes about 10 s. Results are cached for 6 hours.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI with three tabs: GB model, Country scorecard, Sources & method |
| `data_sources.py` | Live fetchers for Ofgem and Elexon. They raise `DataSourceError` and never fall back to stored numbers |
| `model.py` | Load profile, tariffs, EV scheduling, battery linear programme, scenarios |
| `scorecard.py` | Country figures, each with its source key, data year and note |
| `memo_pdf.py` | One-page landscape A4 PDF memo (fpdf2) |

## Data sources

### Fetched live by the app

| Data | Source | How it is used |
|---|---|---|
| Price cap unit rate and standing charge (electricity and gas) | Ofgem, *Energy price cap unit rates and standing charges*: https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges | The app parses the **current** period column of the GB-average Direct Debit table. At build time (Nov 2026) this was **1 Oct – 31 Dec 2026: electricity 26.32 p/kWh, 54.83 p/day; gas 7.97 p/kWh, 29.68 p/day**. Ofgem notes there is **no VAT on electricity from 1 Oct 2026 to 31 Mar 2027**. |
| Typical Domestic Consumption Values (TDCV) | Ofgem, *Energy price cap update from 1 July 2026* (revised TDCV letter): https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf | The app parses the 2026 medium TDCV: **2,500 kWh electricity**, 9,500 kWh gas, 3,400 kWh multi-register. The older 2,700 / 11,500 kWh values were superseded on 1 July 2026. |
| Half-hourly wholesale price | Elexon BMRS, Market Index Data (MID), provider `APXMIDP`: https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index (docs: https://bmrs.elexon.co.uk/api-documentation/endpoint/balancing/pricing/market-index) | The last 365 complete UTC days, fetched in 6-day windows because the API limit is 7 days. |

**Failure behaviour:** the app stops with an error naming the source instead of inventing numbers if any of these happen:

- a source is unreachable;
- the page layout has changed so parsing fails;
- parsed values fall outside sanity bounds;
- more than 5% of half-hours are missing.

### Scorecard sources (read from published reports, not fetched live)

| Key | Source |
|---|---|
| ACEA26 | ACEA, *Vehicles on European roads*, Jan 2026 (2024 data). https://www.acea.auto/files/ACEA_Report-%E2%80%93-Vehicles_on_European_roads_2026.pdf |
| KBA26 | KBA vehicle stock at 1 Jan 2026, as reported by electrive.net. https://www.electrive.net/2026/02/27/endlich-ueber-zwei-millionen-elektroautos-auf-deutschen-strassen/ |
| EHPA25 | EHPA, *European Heat Pump Market Report 2025*, executive summary, Fig. 4. https://www.ehpa.org/wp-content/uploads/2025/07/EHPA-Market-Report-2025-executive-summary.pdf |
| EMA26 | EMA Energiewelt, Q1 2026 battery storage (citing Battery Charts / RWTH ISEA and BSW-Solar). https://ema-energiewelt.de/wissen/batteriespeicher-rekord-q1-2026-grossspeicher-heimspeicher |
| SOLSERV26 | Solarserver, 6 Jul 2026 (citing 1KOMMA5° analysis of Battery Charts). https://www.solarserver.de/2026/07/06/batteriekapazitaet-in-deutschland-waechst-auf-298-gwh-rekordtempo-beim-speicherausbau/ |
| SPE25 | SolarPower Europe, *EU Battery Storage Market Review 2025*. The copy read was hosted at https://www.infobuildenergia.it/wp-content/uploads/2026/01/EU_Battery_Storage_Market_Review_2025_Report_Final_1c5ecc5560.pdf (a third-party mirror of the SPE report) |
| SMARTEN25 | smartEn, *2025 Market Monitor for Demand Side Flexibility*. https://smarten.eu/wp-content/uploads/2026/01/Market-Monitor-2025.pdf |
| ACER25 | ACER-CEER, *Rewarding Flexibility*, 2025 retail monitoring report, Fig. 6 and footnote 12. https://www.ceer.eu/wp-content/uploads/2025/11/ACER-CEER-2025-Retail-monitoring.pdf |
| ESB25 | ESB Networks, *over 2 million smart meters installed*. https://www.esbnetworks.ie/about-us/newsroom/article/esb-networks-reaches-milestone-of-over-two-million-smart-meters-installed-nationwide-as-part-of-the-national-smart-metering-programme |
| CRU24 | CRU, *National Energy Demand Strategy Decision Paper* (CRU202467). https://consult.cru.ie/en/system/files/materials/153/National%20Energy%20Demand%20Strategy%20Decision%20Paper_1.pdf |

## Every assumption

Assumptions marked ✎ can be edited in the app sidebar or main panel.

### Data handling
1. **Wholesale price** = Elexon Market Index Price from the APX provider (`APXMIDP`), a volume-weighted short-term traded price. It is used as the "wholesale" signal and is not a day-ahead auction price. The N2EX provider is excluded because it reports zero.
2. **Window** = the most recent 365 complete days (UTC midnight to UTC midnight) before the fetch.
3. Half-hours with **zero traded volume** (reported price 0) are treated as missing and filled by **linear interpolation**. The fetch fails if more than 5% are missing. The count is shown in the app.
4. Times are converted to **Europe/London** for the load shape, EV windows and battery days, so DST days have 46 or 50 half-hours.
5. **Price cap rates** are the GB-average **Direct Debit** single-rate electricity values for the current cap period. Regional, prepayment, standard-credit and Economy 7 rates are not used.
6. The current cap rates are applied to **every half-hour of the historic year**. This prices a past year's consumption at today's cap.
7. Results are annualised to 365 days.
8. **Electricity only.** Gas TDCV and gas rates are fetched and displayed but not modelled. No heat pump is modelled in the GB tab.

### Household
9. ✎ Annual consumption = **Ofgem 2026 medium TDCV, 2,500 kWh**.
10. ✎ **Hourly load shape is a stylised assumption, not a sourced dataset.** It has an overnight trough, a morning shoulder and a 17:00–20:00 evening peak. Elexon Profile Class 1 data are not openly available via the BMRS API. Default relative weights by hour (00–23): 0.55, 0.45, 0.40, 0.38, 0.38, 0.42, 0.60, 0.85, 0.90, 0.80, 0.75, 0.75, 0.80, 0.78, 0.75, 0.80, 0.95, 1.30, 1.50, 1.45, 1.30, 1.15, 0.95, 0.75.
11. ✎ **Monthly seasonal factors (assumption)**, Jan–Dec: 1.20, 1.12, 1.05, 0.95, 0.88, 0.83, 0.83, 0.85, 0.92, 1.02, 1.12, 1.23.
12. The same shape applies on weekdays and weekends. Both half-hours within an hour get the same weight.
13. The household's baseline load is not flexible. Only the EV and battery move energy.
14. There is no solar PV.

### Tariffs
15. ✎ Price cap: flat unit rate and standing charge, defaulting to the fetched Ofgem values.
16. ✎ **ToU standing charge = price cap standing charge** by default.
17. ✎ **Wholesale-tracking ToU (default):** `rate(t) = cap unit rate + k × (W(t) − W̄) × (1 + VAT)`, where:
    - W(t) is the half-hourly wholesale price in p/kWh;
    - W̄ is the household-consumption-weighted average wholesale price over the year;
    - k is the pass-through, default 1.0.

    This is a **stylised, revenue-neutral** tariff: a household with the baseline profile pays the same as on the cap, so savings come only from shifting. It is not a replica of any supplier's product. Real ToU tariffs also differ through network-charge shape and supplier margins, which k > 1 roughly represents.
18. ✎ VAT on the wholesale deviation: **0%** by default, because Ofgem states no VAT on electricity from 1 Oct 2026 to 31 Mar 2027. Otherwise 5%.
19. ✎ No floor or ceiling on the ToU rate by default, so **negative rates are allowed**. Both can be turned on.
20. ✎ **Static 3-band ToU (alternative):**
    - off-peak 00:00–07:00, peak 16:00–19:00, all other hours "day";
    - the default rates are the household-weighted average of the wholesale-tracking tariff within each band, so they come from the data rather than from any supplier.

### EV
21. ✎ **7 kWh/day**, measured at the meter (charger losses included), every day of the year.
22. ✎ Charger **7 kW**, so at most 3.5 kWh per half-hour.
23. ✎ Plugged in **18:00 to 07:00** the next morning (local). Plug-in must be at or after 12:00 and departure before 12:00.
24. *Unmanaged* charging starts at plug-in at full power until done. *Smart* charging fills the cheapest half-hours within the window. This is optimal for a linear tariff with perfect knowledge of that night's prices.
25. If the window is too short for the requested energy, the EV charges what fits.
26. The year is treated as **cyclic** for EV sessions: the first morning and last evening of the window form one session, giving exactly 365 sessions.
27. On the price cap, EV timing does not affect cost.

### Battery
28. ✎ **10 kWh usable**, **5 kW** charge/discharge (combined limit per half-hour), **90% round-trip efficiency**, split equally between charge and discharge (√0.9 each way).
29. Dispatch is a **linear programme for each local calendar day with day-ahead perfect foresight** of that day's prices. It minimises import cost of charging minus avoided import cost (minus export revenue) plus degradation.
30. End-of-day state of charge must equal start-of-day; the starting level is chosen by the optimiser. There are no cross-day arbitrage or forecast errors.
31. ✎ **No export by default.** Discharge cannot exceed the home's load (household plus smart EV) in that half-hour. If export is enabled, it is paid at a user-set share of the import ToU rate (default 50% when enabled; an assumption).
32. ✎ Degradation cost: **0 p/kWh** by default.
33. The battery is optimised **after** the smart EV schedule, not jointly.
34. The battery's grid import includes round-trip losses, shown in "Grid import (kWh)".
35. On the flat price cap a battery has no arbitrage value, so no "cap + battery" scenario is shown.

### Outputs
36. **Value of flexibility** = differences in annual bill between scenarios: cap → ToU, unmanaged → smart EV, smart EV → plus battery, and cap with EV → best ToU case.
37. These are **bill savings only**. Hardware, installation, financing and any supplier fees are **not** netted off.
38. There is **no market-revenue stacking** (Demand Flexibility Service, capacity market, balancing-mechanism or ancillary-service payments). Only tariff arbitrage is modelled.

### Equipment cost & payback
39. ✎ **Battery installed cost £5,750**: the midpoint of the indicative £4,500–£7,000 range for a 10 kWh home battery from [Switch Together](https://switchtogether.co.uk/resource-hub/blog/solar-battery-storage-cost-roi), a comparison site. The same page cites MCS data: the average battery installation in 2024 cost ≈ £8,035 across all sizes. No impartial official per-kWh price was found; the Energy Saving Trust page blocked automated access. If you change the battery size, adjust the cost too; it does not scale automatically.
40. Home batteries, including standalone grid-charged units, are **zero-rated for VAT from 1 Feb 2024 to 31 Mar 2027** ([HMRC Notice 708/6 s.2.19](https://www.gov.uk/guidance/vat-on-energy-saving-materials-and-heating-equipment-notice-7086)). The default cost assumes 0% VAT.
41. ✎ **Smart EV charging costs £0 extra**: since 30 June 2022, private charge points sold in GB must be smart ([Smart Charge Points Regulations 2021](https://www.gov.uk/guidance/regulations-electric-vehicle-smart-charge-points)). The EV and charger are assumed to be bought anyway.
42. ✎ **Battery lifetime 10 years** and **charger lifetime 10 years**: **assumptions, not sourced**. Savings stop at end of life, with no residual value.
43. ✎ **Discount rate 3% real**: HM Treasury [Green Book Discount Rate Review (2026)](https://assets.publishing.service.gov.uk/media/6a43915e7ac6fd9c6a94abbe/Findings_and_Recommendations_-_Green_Book_Discount_Rate_Review.pdf). This is a public-sector social rate; a household might reasonably use a higher personal rate.
44. ✎ **Annual savings held flat in real terms (0%/yr)**: assumption. Battery degradation or narrowing price spreads would reduce savings (enter a negative %).
45. Year-1 savings are the modelled annual differences: smart EV = scenario 4 − 5, battery = scenario 5 − 6 (or 3 − 6 without an EV). Savings arrive at year end.
46. The appraisal excludes maintenance, inverter replacement, financing costs, grid-service income (e.g. Demand Flexibility Service), backup-power value and resale value.

### Scorecard
47. Figures were researched in **November 2026** and transcribed from the reports listed above. They are not fetched live. Each cell shows its data year.
48. **EV stock** = BEV + PHEV passenger cars:
    - counts are derived as ACEA's published % share × ACEA's 2024 car fleet;
    - shares are rounded to 0.1 pp, so counts are approximate;
    - Germany also gets a note with the newer KBA count (2,034,260 BEVs at 1 Jan 2026).
49. **Heat pump stock** = EHPA 2024 stock, all types including reversible air-to-air units. This raises France and Spain compared with heating-only counts. EHPA's Irish figures are 2024 values carried forward.
50. **Home battery stock:**
    - Germany: ≈2.5 m systems in total, overwhelmingly home units (BSW-Solar, end-Mar 2026), and ≈22 GWh of home capacity (Battery Charts, Jul 2026).
    - **NL, FR, IE and ES are left blank**: no sourced national stock figure was found. Notes give the annual-flow figures that do exist.
51. **Smart meters:**
    - smartEn 2025 national figures for NL (89%), DE (4%), FR (94%) and ES (complete);
    - ESB Networks for IE ("more than four out of five households");
    - the ACER-CEER 2024 map bands are given as corroboration.
52. **Household access to flexibility/balancing markets:**
    - the Yes / Partial / Limited rating is **this app's summary** of the cited regulatory assessments (smartEn, CRU, ACER), not an official score;
    - smartEn's 2025 monitor does not cover Ireland, so Ireland draws on CRU and ACER.

## Known limitations

- Ofgem and Elexon page and API layouts can change. The parsers fail loudly rather than guess.
- Elexon MID is a traded-market index, not a retail price. Using it for ToU shape is a modelling choice.
- One year of history is only one weather and price regime, and the value of flexibility varies a lot from year to year.
