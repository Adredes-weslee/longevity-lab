# Optional Data-Source Candidate Screen

Screened on: `2026-05-06`

This document is generated from `conf/data_source_candidates.yaml` by `pdm run python -m longevity_lab.pipeline.source_screening --output docs/data_source_candidate_screen.md`.

No raw data is downloaded by this screen. Future ingestion PRs must pass this registry screen before adding a source to `conf/data_sources.yaml`.

## Decision Rubric

| Criterion | Required evidence | Pass condition |
| --- | --- | --- |
| Public access | Official public landing page plus a scriptable download/API path; no private credentials, proprietary datasets, or manual-only exports. | The access method can be automated and cited from an official source without storing secrets. |
| Join feasibility | Documented geography and time keys that can support state-year, county-year, tract-year, or separate validation semantics. | The source has a defensible join path or is explicitly marked validation-only with no row join to BRFSS. |
| Prior signal rationale | A plausible relationship to modeled conditions, scenario sensitivity, contextual explanation, fairness review, or external validation. | The source is not added just because it is available; it must target a named model/report use. |
| Bias review | Known limitations, modeled-estimate risks, missingness, suppression, survey coverage, ecological fallacy, and temporal mismatch are recorded. | A future PR can present the source with caveats that match the measurement process. |
| Operational fit | Expected local size, processing complexity, and deployment implications are compatible with the local-first repo. | Raw and processed outputs remain gitignored, and a dev/sample path can be kept small. |
| Ablation plan | A concrete first experiment or an explicit no-training decision for context-only and validation-only sources. | Future ingestion defines what lift, stability, or validation check would justify retaining the source. |

## First-Pass Decisions

| Source | Decision | Join feasibility | Expected size |
| --- | --- | --- | --- |
| AHRQ Community-Level Health Database | `watchlist` | medium | Moderate to large: county files are about 10-16 MB per year, tract files about 50-65 MB, and block-group files up to about 262 MB. |
| USDA ERS Food Environment Atlas and Food Access Research Atlas | `ready-for-ablation` | medium | Small to moderate: current Food Environment CSV ZIP is about 6.2 MB; Food Access current ZIP is about 8.65 MB and XLSX about 81.83 MB. |
| County Health Rankings and Roadmaps Analytic Data | `context-only` | high | Small to moderate: annual national CSV/SAS analytic and trend downloads, plus documentation; exact sizes vary by release. |
| CDC WONDER Mortality Query API | `validation-only` | low | Small per scripted query because the API returns summarized result tables, not record-level files. |
| CDC NHANES Public-Use Data | `validation-only` | none | Moderate if curated: selected XPT modules by cycle are manageable, while broad lab/exam/diet ingestion can grow quickly. |
| CDC NHIS Public-Use Data | `watchlist` | none | Small to moderate: 2024 sample adult CSV is 32.8 MB, sample child CSV is 4.9 MB, and paradata CSV is 15.1 MB. |

## Candidate Details

### AHRQ Community-Level Health Database

- Source ID: `ahrq_clh_database`
- Decision: `watchlist`
- Source URL: https://www.ahrq.gov/data/innovations/clh-data.html
- Supporting URLs: https://www.ahrq.gov/sdoh/data-analytics.html
- Access method: official XLSX downloads by year and geography from AHRQ landing page; scriptable=yes; credentials_required=no; manual_only=no. The CLH page exposes downloadable data files and documentation; this screen does not download them.
- Geography/time keys: geographies=county; ZIP Code; census tract; census block group; time_keys=year; join_keys=county_fips; zip_code; tract_geoid; block_group_geoid; year; time_coverage=2009-2023, with geography availability varying by level. BRFSS 2023 can only use state-year joins today; lower-geography CLH fields would need aggregation or future geography-aware artifacts.
- Likely features: healthcare provider supply; insurance and access context; economic and education context; physical infrastructure; community-level health-condition context
- Target outcomes: healthcare access context; diabetes; heart disease; depression; chronic lung disease; equity and subgroup review
- Join feasibility: medium. County-year keys are useful for context tables, but many variables duplicate ACS/SVI/PLACES and BRFSS cannot row-join below state-year in the current contract.
- Bias caveats: Curated from heterogeneous source systems with varying missingness and measurement methods.; Lower-geography context can create ecological-fallacy risk when attached to person-level BRFSS rows.; Health-system variables may encode access and utilization differences rather than underlying need.; AHRQ warns not to combine the updated CLH database with prior SDOH v1 files because variable construction changed.
- Decision rationale: Keep on watchlist until ACS/SVI/PLACES ablations are stable; use only if it provides nonredundant context or simpler provenance than raw upstream sources.
- Rubric evidence: public_access=Pass: official public downloads are available without credentials.; join_feasibility=Conditional: county-year is feasible for context, but current prediction rows are state-year only.; prior_signal_rationale=Strong for health-system and SDOH context, but much overlaps existing ACS/SVI/PLACES sources.; bias_review=Requires variable-by-variable source caveats, suppression review, and temporal alignment checks.; operational_fit=Acceptable only for selected county fields; tract/block-group downloads are too broad for a default local build.; ablation_plan=After PR20-style context ablations, test a small county-to-state aggregate subset against ACS/SVI-only artifacts.

### USDA ERS Food Environment Atlas and Food Access Research Atlas

- Source ID: `usda_food_environment_food_access`
- Decision: `ready-for-ablation`
- Source URL: https://www.ers.usda.gov/data-products/food-environment-atlas/data-access-and-documentation-downloads/
- Supporting URLs: https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data
- Access method: official ZIP/XLSX downloads from USDA ERS landing pages; scriptable=yes; credentials_required=no; manual_only=no. Food Environment Atlas provides machine-readable CSV ZIP downloads; Food Access Research Atlas provides XLSX and ZIP downloads.
- Geography/time keys: geographies=county; census tract; time_keys=atlas release year; measure-specific source year; join_keys=county_fips; tract_geoid; measure_year; time_coverage=Food Environment current release updated 2025; Food Access current data file is 2019 with 2010 tract geometry. Food Environment county FIPS can support state aggregation; Food Access tract keys are useful only as contextual geography, not a BRFSS row join.
- Likely features: grocery and supermarket access; low-income and low-access tract indicators; food insecurity and SNAP context; food store and restaurant density; obesity and diabetes contextual measures
- Target outcomes: diabetes; heart disease; obesity-related risk context; equity and access context
- Join feasibility: medium. County FIPS and tract GEOID are clear, but current BRFSS training can only use aggregated state-year context unless later artifacts support finer geography.
- Bias caveats: Food access measures are area-level proxies and do not measure individual diet or purchasing behavior.; Food Access uses 2010 tract geography for the current file, which can mismatch newer Census geography and BRFSS years.; Atlas measures come from many source years, so temporal alignment must be feature-specific.; SNAP/store density variables may reflect policy and business reporting differences as well as access.
- Decision rationale: Selected county/state-aggregated measures have a plausible diabetes and cardiovascular signal and manageable size; ingestion still requires a focused ablation PR.
- Rubric evidence: public_access=Pass: official public ERS downloads are scriptable and require no credentials.; join_feasibility=Conditional pass: county/state aggregation is feasible; tract features need careful geography handling.; prior_signal_rationale=Strong for diet-access context related to diabetes, obesity, and cardiometabolic risk.; bias_review=Must document ecological fallacy, old tract boundaries, and measure-specific source years.; operational_fit=Good for a curated CSV subset; do not ingest all Atlas columns by default.; ablation_plan=Run no_food_access versus selected_food_access ablations after geography-aware context artifacts exist.

### County Health Rankings and Roadmaps Analytic Data

- Source ID: `county_health_rankings`
- Decision: `context-only`
- Source URL: https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation
- Supporting URLs: https://github.com/CountyHealthRankings
- Access method: official CSV/SAS downloads and public GitHub assets; scriptable=yes; credentials_required=no; manual_only=no. The data documentation page links national annual data, trend data, analytic data, data dictionaries, and select GitHub resources.
- Geography/time keys: geographies=county; state; national; time_keys=release year; measure year; join_keys=state_fips; county_fips; release_year; measure_year; time_coverage=Annual releases with trend files; 2025 release plus March 2026 supplemental release were visible during screening. County keys are clear, but many fields are downstream health outcomes or composites that should not be treated as independent predictors.
- Likely features: county health factors; county health outcomes; clinical care and access measures; social and economic factors; physical environment context
- Target outcomes: dashboard context; external reasonableness checks; county-level trend comparison; equity and communication context
- Join feasibility: high. County/state/time keys are explicit, but the intended use is context and validation rather than person-level training features.
- Bias caveats: Composite rankings and z-score style measures are not raw causal inputs.; Some measures are modeled, lagged, suppressed, or sourced from other datasets already in the repo.; Using CHR health outcomes in training could leak target prevalence or create circular validation.; Comparability varies across states and release years.
- Decision rationale: Use for dashboards and source comparison, not model training, because many measures are redundant composites or outcome summaries.
- Rubric evidence: public_access=Pass: official public files and documentation are available.; join_feasibility=Pass for county context; fail for person-level labels.; prior_signal_rationale=Useful for communication and reasonableness checks, but weak as novel predictive signal.; bias_review=Must separate rankings/composites from source variables and document comparability limits.; operational_fit=Acceptable for small context/report tables.; ablation_plan=No training ablation by default; compare model aggregates against selected county measures in validation reports only if needed.

### CDC WONDER Mortality Query API

- Source ID: `cdc_wonder_mortality`
- Decision: `validation-only`
- Source URL: https://wonder.cdc.gov/wonder/help/wonder-api.html
- Supporting URLs: https://wonder.cdc.gov/wonder/help/main.html; https://wonder.cdc.gov/wonder/help/ucd.html
- Access method: official XML POST query API returning aggregated statistics; scriptable=yes; credentials_required=no; manual_only=no. The API can automate summary queries, but CDC notes that National Vital Statistics API queries cannot group or limit mortality and births data by subnational geography.
- Geography/time keys: geographies=national through API for mortality; subnational through web UI only; time_keys=year; month for selected datasets; join_keys=year; cause_of_death; time_coverage=Dataset-specific; underlying-cause help page documents county-level 1999-2020 data in the web application, while API mortality geography is national only. Do not plan a state/county automated join from the WONDER mortality API unless CDC exposes a documented scriptable geography path.
- Likely features: age-adjusted mortality rates; crude death rates; death counts by ICD-10 cause group; national cause-of-death time trends
- Target outcomes: heart disease mortality context; stroke mortality context; diabetes mortality context; chronic lower respiratory disease mortality context; national validation trend checks
- Join feasibility: low. National API output can align by year and cause, but not by state/county through a scriptable mortality API path.
- Bias caveats: Mortality is not incidence or self-reported diagnosis prevalence.; Cause-of-death coding changes and suppression rules affect comparisons.; The API applies provider-specific caveats and suppression constraints that must be preserved.; National-only API output cannot validate geography-specific model behavior.
- Decision rationale: Use only for national mortality context and trend sanity checks unless a scriptable subnational path is officially documented.
- Rubric evidence: public_access=Pass: public API without private credentials.; join_feasibility=Limited: year/cause joins only for mortality API output.; prior_signal_rationale=Strong for outcome context, but mortality semantics differ from BRFSS diagnosis labels.; bias_review=Must preserve CDC caveats, suppression notes, and mortality-versus-prevalence distinctions.; operational_fit=Good for small query outputs.; ablation_plan=No training ablation; compare national predicted-risk trends with national mortality-rate context only.

### CDC NHANES Public-Use Data

- Source ID: `cdc_nhanes_public`
- Decision: `validation-only`
- Source URL: https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/
- Supporting URLs: https://www.cdc.gov/nchs/nhanes/about/index.html
- Access method: official public-use module downloads and documentation by survey cycle; scriptable=yes; credentials_required=no; manual_only=no. Public-use data files are downloadable by component; restricted data require RDC access and are out of scope.
- Geography/time keys: geographies=national survey sample; time_keys=two-year survey cycle; join_keys=survey_cycle; respondent_sequence_number; time_coverage=Continuous NHANES public-use cycles since 1999, with 08/2021-08/2023 and newer cycle pages visible during screening. NHANES can link modules within survey cycle by respondent ID, but it should not row-join to BRFSS.
- Likely features: measured BMI and blood pressure; laboratory biomarkers; dietary recall and nutrition measures; questionnaire disease history; exam-based validation variables
- Target outcomes: diabetes validation experiments; cardiometabolic biomarker validation; obesity and diet context; measurement-bias review
- Join feasibility: none. NHANES is a separate national survey; use it as a separate validation pipeline rather than attaching rows to BRFSS respondents.
- Bias caveats: Complex survey design and weights differ from BRFSS.; Sample sizes can be small for subgroups and condition-specific labels.; Restricted geography is not public-use; public data cannot support state/county joins.; Measurement differences between exam/lab variables and self-reported BRFSS fields must be explicit.
- Decision rationale: Valuable for separate biomarker and measurement-bias validation, but not as a training feature source for BRFSS-based artifacts.
- Rubric evidence: public_access=Pass for public-use modules; restricted modules are out of scope.; join_feasibility=No BRFSS join; internal NHANES module joins only.; prior_signal_rationale=Strong for biomarkers and measured health variables that BRFSS lacks.; bias_review=Requires survey-weight handling, cycle pooling rules, and measurement-semantics documentation.; operational_fit=Acceptable only for curated modules and cycles.; ablation_plan=No training ablation; build a separate validation report comparing BRFSS-derived risk patterns with NHANES measured outcomes.

### CDC NHIS Public-Use Data

- Source ID: `cdc_nhis_public`
- Decision: `watchlist`
- Source URL: https://www.cdc.gov/nchs/nhis/documentation/index.html
- Supporting URLs: https://ftp.cdc.gov/pub/health_statistics/nchs/dataset_documentation/NHIS/2024/Checksum-Filelist.pdf
- Access method: official public-use CSV/ASCII downloads and documentation by survey year; scriptable=yes; credentials_required=no; manual_only=no. Public-use files are downloadable from CDC/NCHS; linked restricted files through RDC are out of scope.
- Geography/time keys: geographies=national survey sample; public region and urban-rural variables; time_keys=survey year; join_keys=survey_year; household_id; person_id; time_coverage=Recent annual pages for 2019-2025 are linked from the CDC documentation gateway; earlier years are archived. Public-use NHIS can join internal files within year, but not person rows to BRFSS or county/state context at a granular level.
- Likely features: self-reported diagnosed conditions; health insurance and access; usual source of care; mental health measures; health behavior and demographic covariates
- Target outcomes: depression benchmark; healthcare access benchmark; alternate survey validation; survey-method sensitivity review
- Join feasibility: none. NHIS is a separate national survey and cannot row-join to BRFSS; use only for external survey benchmarking.
- Bias caveats: Question wording and survey mode differ from BRFSS.; Public-use geography is limited, while linked files require restricted RDC access.; Survey redesigns can break trend comparability.; Overlapping self-reported outcomes could duplicate BRFSS rather than validate it independently.
- Decision rationale: Keep on watchlist for depression and healthcare-access benchmarking only; do not ingest until a specific validation question beats BRFSS-only alternatives.
- Rubric evidence: public_access=Pass for public-use files; restricted linked data are rejected by scope.; join_feasibility=No BRFSS join; internal annual file joins only.; prior_signal_rationale=Moderate for depression/access benchmarks, weaker for conditions already covered by BRFSS.; bias_review=Requires survey redesign, weighting, and construct-alignment review.; operational_fit=Good for selected annual public-use files.; ablation_plan=No default training ablation; define a depression/access validation question before ingestion.
