"""Information-architecture contract for the Fase 6.4 dashboard shell.

The application keeps Streamlit's in-page tab model (roadmap option 2.1-A)
while giving every existing module exactly one owner among the four v2 layers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationModule:
    """One existing dashboard module exposed inside an IA layer."""

    key: str
    label: str


@dataclass(frozen=True)
class NavigationLayer:
    """One of the four product-level navigation layers."""

    key: str
    label: str
    icon: str
    question: str
    modules: tuple[NavigationModule, ...]

    @property
    def tab_label(self) -> str:
        return f"{self.icon} {self.label}"


NAVIGATION_LAYERS = (
    NavigationLayer(
        key="decidir",
        label="Decidir",
        icon="🧭",
        question="¿Qué debe decidirse esta semana?",
        modules=(
            NavigationModule("panorama", "Panorama ejecutivo"),
            NavigationModule("urgent_actions", "Acciones urgentes"),
            NavigationModule("budget", "Simulador de presupuesto"),
            NavigationModule("socioeconomic", "Impacto socioeconómico"),
        ),
    ),
    NavigationLayer(
        key="diagnosticar",
        label="Diagnosticar",
        icon="🔬",
        question="¿Es real la señal y dónde ocurre?",
        modules=(
            NavigationModule("spatial", "Diagnóstico espacial"),
            NavigationModule("alpine", "Observatorio alpino"),
            NavigationModule("assets", "Catálogo de activos y sendas"),
            NavigationModule("pressure", "Presión y capacidad de carga"),
            NavigationModule("forecast", "Proyección de tendencia"),
        ),
    ),
    NavigationLayer(
        key="evidenciar",
        label="Evidenciar",
        icon="🛰️",
        question="¿Qué datos sostienen la señal?",
        modules=(
            NavigationModule("satellite", "Evidencia satelital"),
            NavigationModule("confidence", "Confianza e incertidumbre"),
            NavigationModule("provenance", "Proveniencia y linaje"),
        ),
    ),
    NavigationLayer(
        key="gobernar",
        label="Gobernar",
        icon="⚖️",
        question="¿Puede reconstruirse y auditarse la decisión?",
        modules=(
            NavigationModule("methodology", "Metodología y auditoría"),
            NavigationModule("reports", "Informes y exportaciones"),
            NavigationModule("configuration", "Configuración territorial"),
        ),
    ),
)

_LAYERS_BY_KEY = {layer.key: layer for layer in NAVIGATION_LAYERS}


def layer_tab_labels(home_layer_key: str | None = None) -> list[str]:
    """Return layer labels with an optional audience home first."""
    return [layer.tab_label for layer in navigation_layers(home_layer_key)]


def navigation_layer(key: str) -> NavigationLayer:
    """Return one layer or fail loudly when app wiring uses an unknown key."""
    try:
        return _LAYERS_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"Unknown navigation layer: {key}") from exc


def navigation_layers(
    home_layer_key: str | None = None,
) -> tuple[NavigationLayer, ...]:
    """Put one audience home first while preserving canonical remainder order."""
    if home_layer_key is None:
        return NAVIGATION_LAYERS
    home = navigation_layer(home_layer_key)
    return (home,) + tuple(
        layer for layer in NAVIGATION_LAYERS if layer.key != home_layer_key
    )


def module_tab_labels(layer_key: str) -> list[str]:
    """Return the visible module tabs owned by a layer."""
    return [module.label for module in navigation_layer(layer_key).modules]
