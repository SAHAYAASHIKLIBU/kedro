import logging
from typing import Any

from kedro.framework.context import KedroContext
from kedro.framework.project import pipelines as _pipelines
from kedro.io import KedroDataCatalog


def is_parameter(dataset_name: str) -> bool:
    # TODO: when breaking change move it to kedro/io/core.py
    """Check if dataset is a parameter."""
    return dataset_name.startswith("params:") or dataset_name == "parameters"


class CatalogCommandsMixin:
    @property
    def context(self) -> KedroContext: ...  # type: ignore[empty-body]

    @property
    def _logger(self) -> logging.Logger: ...  # type: ignore[empty-body]

    def list_catalog_datasets(self, pipelines: list[str] | None = None) -> dict:
        """Show datasets per type."""
        catalog = self.context.catalog
        # TODO: remove after moving to new catalog
        if not isinstance(catalog, KedroDataCatalog):
            self._logger.warning(
                "This method is available for `KedroDataCatalog` only."
            )
            return {}

        # TODO: revise setting default pattern logic based on https://github.com/kedro-org/kedro/issues/4475
        runtime_pattern = {"{default}": {"type": "MemoryDataset"}}

        target_pipelines = pipelines or _pipelines.keys()

        result = {}
        for pipe in target_pipelines:
            pl_obj = _pipelines.get(pipe)
            if pl_obj:
                pipeline_ds = pl_obj.datasets()
            else:
                existing_pls = ", ".join(sorted(_pipelines.keys()))
                raise ValueError(
                    f"'{pipe}' pipeline not found! Existing pipelines: {existing_pls}"
                )

            catalog_ds = set(catalog.keys())

            patterns_ds = set()
            default_ds = set()
            for ds_name in pipeline_ds - catalog_ds:
                if catalog.config_resolver.match_pattern(ds_name):
                    patterns_ds.add(ds_name)
                else:
                    default_ds.add(ds_name)

            catalog.config_resolver.add_runtime_patterns(runtime_pattern)

            used_ds_by_type = _group_ds_by_type(
                pipeline_ds - patterns_ds - default_ds, catalog
            )
            patterns_ds_by_type = _group_ds_by_type(patterns_ds, catalog)
            default_ds_by_type = _group_ds_by_type(default_ds, catalog)

            catalog.config_resolver.remove_runtime_patterns(runtime_pattern)

            data = (
                ("datasets", used_ds_by_type),
                ("factories", patterns_ds_by_type),
                ("defaults", default_ds_by_type),
            )
            result[pipe] = {key: value for key, value in data}

        return result

    def list_catalog_patterns(self) -> list[str]:
        """List all dataset factories in the catalog, ranked by priority
        by which they are matched.
        """
        return self.context.catalog.config_resolver.list_patterns()

    def resolve_catalog_patterns(self, include_default: bool = False) -> dict[str, Any]:
        """Resolve catalog factories against pipeline datasets."""
        catalog = self.context.catalog

        # TODO: remove after moving to new catalog
        if not isinstance(catalog, KedroDataCatalog):
            self._logger.warning(
                "This method is available for `KedroDataCatalog` only."
            )
            return {}

        # TODO: revise setting default pattern logic based on https://github.com/kedro-org/kedro/issues/4475
        runtime_pattern = {"{default}": {"type": "MemoryDataset"}}
        if include_default:
            catalog.config_resolver.add_runtime_patterns(runtime_pattern)

        pipeline_datasets = set()

        for pipe in _pipelines.keys():
            pl_obj = _pipelines.get(pipe)
            if pl_obj:
                pipeline_datasets.update(pl_obj.datasets())

        # We need to include datasets defined in the catalog.yaml and datasets added manually to the catalog
        explicit_datasets = {}
        for ds_name, ds in catalog.items():
            if is_parameter(ds_name):
                continue

            unresolved_config, _ = catalog.config_resolver.unresolve_credentials(
                ds_name, ds.to_config()
            )
            explicit_datasets[ds_name] = unresolved_config

        for ds_name in pipeline_datasets:
            if ds_name in explicit_datasets or is_parameter(ds_name):
                continue

            ds_config = catalog.config_resolver.resolve_pattern(ds_name)
            if ds_config:
                explicit_datasets[ds_name] = ds_config

        if include_default:
            catalog.config_resolver.remove_runtime_patterns(runtime_pattern)

        return explicit_datasets


def _group_ds_by_type(
    datasets: set[str], catalog: KedroDataCatalog
) -> dict[str, list[str]]:
    mapping = {}
    for ds_name in datasets:
        if is_parameter(ds_name):
            continue

        str_type = catalog.get_type(ds_name)
        if str_type not in mapping:
            mapping[str_type] = []

        mapping[str_type].append(ds_name)

    return mapping
