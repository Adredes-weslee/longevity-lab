"""Evidence-status service for data, model, and report surfaces."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from longevity_lab.api.schemas import (
    EvidenceAssetGroup,
    EvidenceAssetStatus,
    EvidenceFeatureInventory,
    EvidenceInactiveGap,
    EvidenceProductionArtifactSummary,
    EvidenceReportSummary,
    EvidenceSourceSummary,
    EvidenceStatusResponse,
    ModelMetadataResponse,
    RuntimeMetadataResponse,
)
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.config import Settings
from longevity_lab.config_files import config_file_path
from longevity_lab.pipeline.ingest import build_ingest_paths
from longevity_lab.pipeline.sources import load_data_source_registry

EvidenceSourceRole = Literal[
    "active_model",
    "pipeline_context",
    "external_validation",
    "local_workflow",
]


def _iso_utc_from_mtime(mtime_seconds: float) -> str:
    return dt.datetime.fromtimestamp(mtime_seconds, tz=dt.UTC).isoformat()


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _asset(
    asset_id: str,
    label: str,
    kind: Literal["raw", "processed", "provenance", "duckdb", "artifact", "report"],
    path: Path,
    *,
    root: Path,
    source_ids: list[str] | None = None,
    caveat: str | None = None,
) -> EvidenceAssetStatus:
    exists = path.exists()
    if not exists:
        return EvidenceAssetStatus(
            asset_id=asset_id,
            label=label,
            kind=kind,
            path=_display_path(path, root=root),
            exists=False,
            source_ids=source_ids or [],
            caveat=caveat,
        )
    stat = path.stat()
    return EvidenceAssetStatus(
        asset_id=asset_id,
        label=label,
        kind=kind,
        path=_display_path(path, root=root),
        exists=True,
        bytes=stat.st_size,
        modified_at=_iso_utc_from_mtime(stat.st_mtime),
        source_ids=source_ids or [],
        caveat=caveat,
    )


def _group(group_id: str, label: str, assets: list[EvidenceAssetStatus]) -> EvidenceAssetGroup:
    return EvidenceAssetGroup(
        group_id=group_id,
        label=label,
        ready_count=sum(1 for item in assets if item.exists),
        total_count=len(assets),
        assets=assets,
    )


class EvidenceService:
    """Build comprehensive evidence status for the UI."""

    def __init__(
        self,
        *,
        settings: Settings,
        runtime: RuntimeMetadataResponse,
        model_metadata: ModelMetadataResponse,
    ) -> None:
        """Store runtime settings and metadata snapshots."""
        self._settings = settings
        self._runtime = runtime
        self._model_metadata = model_metadata

    def get_status(self, *, year: int) -> EvidenceStatusResponse:
        """Return source, asset, report, artifact, and feature status."""
        data_root = self._settings.data_dir
        artifact_root = self._settings.artifacts_dir
        bundle = self._active_bundle()
        return EvidenceStatusResponse(
            year=year,
            runtime=self._runtime,
            model_metadata=self._model_metadata,
            sources=self._sources(bundle),
            asset_groups=self._asset_groups(
                year=year,
                data_root=data_root,
                artifact_root=artifact_root,
            ),
            reports=self._reports(),
            production_artifact=self._production_artifact(bundle),
            feature_inventory=self._feature_inventory(bundle),
            inactive_gaps=self._inactive_gaps(bundle),
        )

    def _sources(self, bundle: ArtifactBundle | None) -> list[EvidenceSourceSummary]:
        registry = load_data_source_registry()
        active_source_ids = {
            "cdc_brfss_llcp_xpt",
            "epa_airdata_annual_aqi_by_county",
            "epa_airdata_annual_conc_by_monitor",
        }
        active_source_ids.update(_active_context_source_ids(bundle))
        external_validation = {"cdc_places_county_opendata"}
        pipeline_context = {"census_acs5_api_context", "cdc_atsdr_svi_us_county_csv"}
        summaries: list[EvidenceSourceSummary] = []
        for source in registry.sources:
            if source.source_id in active_source_ids:
                role: EvidenceSourceRole = "active_model"
                active = True
                caveat = None
            elif source.source_id in external_validation:
                role = "external_validation"
                active = False
                caveat = "Context and reasonableness checks only; not person-level labels."
            elif source.source_id in pipeline_context:
                role = "pipeline_context"
                active = False
                caveat = (
                    "Implemented as geography context; active only for artifacts that declare "
                    "state-year context feature lookup provenance."
                )
            else:
                role = "local_workflow"
                active = False
                caveat = None
            summaries.append(
                EvidenceSourceSummary(
                    source_id=source.source_id,
                    title=source.title,
                    geography=source.geography,
                    expected_file_pattern=source.expected_file_pattern,
                    local_landing_path=source.local_landing_path,
                    active_in_model=active,
                    role=role,
                    caveat=caveat,
                )
            )
        return summaries

    def _asset_groups(
        self,
        *,
        year: int,
        data_root: Path,
        artifact_root: Path,
    ) -> list[EvidenceAssetGroup]:
        paths = build_ingest_paths(data_root)
        provenance_dir = paths.provenance_dir
        raw = [
            _asset(
                "brfss_xpt",
                f"BRFSS {year} raw XPT",
                "raw",
                paths.brfss_raw_dir(year) / f"LLCP{year}.XPT",
                root=data_root,
                source_ids=["cdc_brfss_llcp_xpt"],
            ),
            _asset(
                "epa_aqi_csv",
                f"EPA AirData AQI {year}",
                "raw",
                paths.epa_airdata_annual_aqi_csv(year),
                root=data_root,
                source_ids=["epa_airdata_annual_aqi_by_county"],
            ),
            _asset(
                "epa_conc_csv",
                f"EPA annual concentration {year}",
                "raw",
                paths.epa_airdata_raw_dir()
                / f"annual_conc_by_monitor_{year}"
                / f"annual_conc_by_monitor_{year}.csv",
                root=data_root,
                source_ids=["epa_airdata_annual_conc_by_monitor"],
            ),
            _asset(
                "acs_county_json",
                "ACS county context raw JSON",
                "raw",
                data_root / "external" / "acs" / "acs5" / "2022" / "acs5_county_context.json",
                root=data_root,
                source_ids=["census_acs5_api_context"],
            ),
            _asset(
                "svi_county_csv",
                "CDC/ATSDR SVI county CSV",
                "raw",
                data_root / "external" / "svi" / "2022" / "SVI_2022_US_county.csv",
                root=data_root,
                source_ids=["cdc_atsdr_svi_us_county_csv"],
            ),
            _asset(
                "places_county_csv",
                "CDC PLACES county CSV",
                "raw",
                data_root / "external" / "places" / "county" / "2025" / "places_county_2025.csv",
                root=data_root,
                source_ids=["cdc_places_county_opendata"],
            ),
        ]
        processed = [
            _asset(
                "brfss_person_parquet",
                f"BRFSS {year} processed person table",
                "processed",
                paths.brfss_person_parquet(year),
                root=data_root,
                source_ids=["cdc_brfss_llcp_xpt"],
            ),
            _asset(
                "epa_state_year_parquet",
                "EPA state-year pollutants",
                "processed",
                paths.epa_state_year_parquet(),
                root=data_root,
                source_ids=[
                    "epa_airdata_annual_aqi_by_county",
                    "epa_airdata_annual_conc_by_monitor",
                ],
            ),
            _asset(
                "context_state_year_parquet",
                "ACS/SVI state-year context",
                "processed",
                data_root / "processed" / "context" / "context_state_year.parquet",
                root=data_root,
                source_ids=["census_acs5_api_context", "cdc_atsdr_svi_us_county_csv"],
                caveat="Available state-year context; active only for context-aware artifacts.",
            ),
            _asset(
                "places_county_year_parquet",
                "PLACES county validation context",
                "processed",
                data_root / "processed" / "places" / "places_county_year.parquet",
                root=data_root,
                source_ids=["cdc_places_county_opendata"],
                caveat="External validation/context only.",
            ),
            _asset(
                "integrated_person_year_parquet",
                f"Integrated BRFSS/EPA {year}",
                "processed",
                paths.integrated_person_year_parquet(year),
                root=data_root,
                source_ids=[
                    "cdc_brfss_llcp_xpt",
                    "epa_airdata_annual_aqi_by_county",
                    "epa_airdata_annual_conc_by_monitor",
                ],
            ),
            _asset(
                "duckdb",
                "DuckDB local analytics views",
                "duckdb",
                paths.duckdb_path,
                root=data_root,
            ),
        ]
        provenance = [
            _asset(candidate.stem, candidate.stem, "provenance", candidate, root=data_root)
            for candidate in sorted(provenance_dir.glob("*.json"))
        ]
        evidence_bundle_root = _evidence_bundle_asset_path(
            artifact_root=artifact_root,
            bundle_id=self._settings.evidence_bundle,
        )
        evidence_caveat = (
            "Public evidence bundle content for Community Context surfaces only; not scoring input."
        )
        public_evidence = [
            _asset(
                "bundle_state_context",
                "Bundled ACS/SVI state context",
                "artifact",
                evidence_bundle_root / "processed" / "context" / "context_state_year.parquet",
                root=artifact_root,
                caveat=evidence_caveat,
            ),
            _asset(
                "bundle_county_context",
                "Bundled ACS/SVI county context",
                "artifact",
                evidence_bundle_root / "processed" / "context" / "context_county_year.parquet",
                root=artifact_root,
                caveat=evidence_caveat,
            ),
            _asset(
                "bundle_places_context",
                "Bundled CDC PLACES county context",
                "artifact",
                evidence_bundle_root / "processed" / "places" / "places_county_year.parquet",
                root=artifact_root,
                caveat=evidence_caveat,
            ),
            _asset(
                "bundle_places_validation",
                "Bundled PLACES aggregate validation",
                "artifact",
                evidence_bundle_root
                / "processed"
                / "validation"
                / "places_external_context_validation_2025.json",
                root=artifact_root,
                caveat=evidence_caveat,
            ),
            _asset(
                "bundle_causal_reports",
                "Bundled causal workbench reports",
                "artifact",
                evidence_bundle_root / "processed" / "reports" / "causal",
                root=artifact_root,
                caveat=evidence_caveat,
            ),
        ]
        artifact = [
            _asset(
                "active_model_bundle",
                "Active local model bundle",
                "artifact",
                artifact_root / "models" / str(self._runtime.artifact_bundle_id or ""),
                root=artifact_root,
            ),
            _asset(
                "public_evidence_bundle",
                "Public Community Context evidence bundle",
                "artifact",
                evidence_bundle_root,
                root=artifact_root,
                caveat=(
                    "Downloaded evidence bundle for deployed Community Context surfaces; "
                    "not used by Explorer scoring."
                ),
            ),
        ]
        return [
            _group("raw_sources", "Raw source downloads", raw),
            _group("processed_tables", "Processed and integrated tables", processed),
            _group("provenance", "Provenance files", provenance),
            _group(
                "public_evidence_bundle",
                "Public evidence bundle contents",
                public_evidence,
            ),
            _group("model_artifacts", "Model artifacts", artifact),
        ]

    def _reports(self) -> list[EvidenceReportSummary]:
        candidates = [
            (
                "eda",
                "Scripted EDA report",
                Path("reports") / "eda" / "index.html",
                "Generated locally by the EDA report command.",
            ),
            (
                "benchmarks",
                "Model benchmark report",
                Path("reports") / "benchmarks",
                "Benchmark outputs are local evidence and are not served as predictions.",
            ),
            (
                "causal_smoking_lung",
                "Causal smoking-to-lung workbench",
                self._settings.data_dir / "processed" / "reports" / "causal",
                "Causal reports are separate from predictive scores.",
            ),
        ]
        reports: list[EvidenceReportSummary] = []
        root = Path.cwd()
        for report_id, label, path, caveat in candidates:
            exists = path.exists()
            stat = path.stat() if exists else None
            reports.append(
                EvidenceReportSummary(
                    report_id=report_id,
                    label=label,
                    path=_display_path(path, root=root),
                    exists=exists,
                    bytes=stat.st_size if stat and path.is_file() else None,
                    modified_at=_iso_utc_from_mtime(stat.st_mtime) if stat else None,
                    caveat=caveat,
                )
            )
        return reports

    def _production_artifact(
        self,
        bundle: ArtifactBundle | None,
    ) -> EvidenceProductionArtifactSummary:
        url_configured = bool(os.environ.get("LONGEVITY_LAB_ARTIFACT_URL"))
        sha_configured = bool(os.environ.get("LONGEVITY_LAB_ARTIFACT_SHA256"))
        configured_bundle = self._settings.artifact_bundle
        return EvidenceProductionArtifactSummary(
            active_bundle_id=self._runtime.artifact_bundle_id,
            configured_bundle_id=configured_bundle,
            url_configured=url_configured,
            sha256_configured=sha_configured,
            local_bundle_exists=bundle is not None,
            release_download_configured=(
                url_configured and sha_configured and bool(configured_bundle)
            ),
        )

    def _feature_inventory(self, bundle: ArtifactBundle | None) -> EvidenceFeatureInventory:
        training_config = self._read_training_config()
        config_features = [str(item) for item in training_config.get("features", [])]
        contract = training_config.get("feature_contract", {})
        scenario_editable = [str(item) for item in contract.get("scenario_editable_features", [])]
        context_features = [str(item) for item in contract.get("context_features", [])]
        active_features = list(bundle.manifest.features) if bundle else []
        by_condition: dict[str, list[str]] = {}
        if bundle:
            for condition in bundle.manifest.conditions:
                features = active_features
                if condition.metrics_path:
                    metrics_path = bundle.path / condition.metrics_path
                    if metrics_path.exists():
                        try:
                            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            payload = {}
                        metric_features = payload.get("features")
                        if isinstance(metric_features, list):
                            features = [str(item) for item in metric_features]
                by_condition[condition.condition_id] = features
        return EvidenceFeatureInventory(
            scenario_editable=scenario_editable,
            active_model_features=active_features,
            active_model_features_by_condition=by_condition,
            training_config_features=config_features,
            training_context_features=context_features,
            available_pipeline_context_features=self._available_context_features(),
            report_only_features=[
                "places_*",
                "acs_*",
                "svi_*",
                "causal_workbench_outputs",
                "benchmark_reports",
            ],
        )

    def _inactive_gaps(self, bundle: ArtifactBundle | None) -> list[EvidenceInactiveGap]:
        gaps: list[EvidenceInactiveGap] = []
        context_candidates = set(self._available_context_features())
        inactive_context = sorted(context_candidates)
        if inactive_context:
            active_context = _active_context_feature_names(bundle)
            if not active_context:
                feature_names_without_contract = sorted(
                    context_candidates & set(bundle.manifest.features if bundle else [])
                )
                explanation = (
                    "These features are built as geography context tables, but the active "
                    "scoring artifact does not declare context feature lookup provenance."
                )
                gaps.append(
                    EvidenceInactiveGap(
                        gap_id="context_not_active",
                        label="ACS/SVI context is implemented but not active in scoring",
                        status="implemented_not_active",
                        evidence=feature_names_without_contract or inactive_context,
                        explanation=explanation,
                        next_action=(
                            "Train and publish context-aware state-year artifacts before using "
                            "these features in predictions."
                        ),
                    ),
                )
            else:
                gaps.append(
                    EvidenceInactiveGap(
                        gap_id="county_context_not_active",
                        label="County-level ACS/SVI context remains inactive in scoring",
                        status="not_served",
                        evidence=["context_county_year.parquet", *active_context],
                        explanation=(
                            "The active artifact uses state-year ACS/SVI context only. "
                            "County-level context is not injected because current BRFSS "
                            "person rows do not expose county join keys."
                        ),
                        next_action=None,
                    )
                )
        gaps.append(
            EvidenceInactiveGap(
                gap_id="places_validation_only",
                label="PLACES remains validation/context only",
                status="not_served",
                evidence=["places_county_year.parquet", "external reasonableness report"],
                explanation=(
                    "PLACES is modeled aggregate geography data, not an independent "
                    "person-level label source."
                ),
                next_action=None,
            )
        )
        return gaps

    def _active_bundle(self) -> ArtifactBundle | None:
        if self._runtime.artifact_bundle_id is None:
            return None
        store = ArtifactStore(self._settings.artifacts_dir / "models")
        try:
            return store.resolve(bundle_id=self._runtime.artifact_bundle_id)
        except Exception:
            return None

    @staticmethod
    def _read_training_config() -> dict[str, Any]:
        path = config_file_path("train.yaml")
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _available_context_features() -> list[str]:
        path = config_file_path("context_features.yaml")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        features: list[str] = []
        for family in ("acs", "svi"):
            family_payload = payload.get(family, {})
            for item in family_payload.get("features", []):
                if isinstance(item, dict) and item.get("name"):
                    features.append(str(item["name"]))
        return features


def _active_context_feature_names(bundle: ArtifactBundle | None) -> list[str]:
    if bundle is None or bundle.manifest.context_features is None:
        return []
    feature_names = list(bundle.manifest.context_features.feature_names)
    if not set(feature_names).issubset(set(bundle.manifest.features)):
        return []
    return feature_names


def _active_context_source_ids(bundle: ArtifactBundle | None) -> set[str]:
    if bundle is None or bundle.manifest.context_features is None:
        return set()
    if not _active_context_feature_names(bundle):
        return set()
    return set(bundle.manifest.context_features.source_ids)


def _evidence_bundle_asset_path(*, artifact_root: Path, bundle_id: str | None) -> Path:
    if not bundle_id:
        return artifact_root / "evidence" / "__unconfigured__"
    bundle_path = Path(bundle_id)
    if bundle_path.is_absolute() or ".." in bundle_path.parts:
        return artifact_root / "evidence" / "__invalid__"
    return artifact_root / "evidence" / bundle_id
