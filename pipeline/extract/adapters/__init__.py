from pipeline.extract.adapters.base import SourceAdapter
from pipeline.extract.adapters.cdsa import CdsaAdapter
from pipeline.extract.adapters.cpsa import CpsaAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "cpsa": CpsaAdapter,
    "cdsa": CdsaAdapter,
}


def get_adapter(name: str) -> SourceAdapter:
    try:
        return ADAPTERS[name]()
    except KeyError as exc:
        raise KeyError(f"Unknown source adapter {name!r}") from exc
