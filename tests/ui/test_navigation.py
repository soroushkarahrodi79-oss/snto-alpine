"""Contracts for the Fase 6.4 four-layer information architecture."""

import pytest

from src.ui.navigation import (
    NAVIGATION_LAYERS,
    layer_tab_labels,
    module_tab_labels,
    navigation_layer,
    navigation_layers,
)


def test_layers_follow_the_v2_decision_flow() -> None:
    assert [layer.key for layer in NAVIGATION_LAYERS] == [
        "decidir",
        "diagnosticar",
        "evidenciar",
        "gobernar",
    ]
    assert layer_tab_labels() == [
        "🧭 Decidir",
        "🔬 Diagnosticar",
        "🛰️ Evidenciar",
        "⚖️ Gobernar",
    ]


def test_every_legacy_module_has_exactly_one_layer_owner() -> None:
    module_keys = [
        module.key for layer in NAVIGATION_LAYERS for module in layer.modules
    ]
    assert len(module_keys) == len(set(module_keys)) == 15
    assert set(module_keys) == {
        "panorama",
        "urgent_actions",
        "budget",
        "socioeconomic",
        "spatial",
        # Alpine Edition: dual-season Sierra Nevada observatory (snow + erosion)
        "alpine",
        "assets",
        "pressure",
        "forecast",
        "satellite",
        "confidence",
        "provenance",
        "methodology",
        "reports",
        "configuration",
    }


def test_module_order_matches_the_approved_option_a_mapping() -> None:
    assert module_tab_labels("decidir") == [
        "Panorama ejecutivo",
        "Acciones urgentes",
        "Simulador de presupuesto",
        "Impacto socioeconómico",
    ]
    assert module_tab_labels("diagnosticar") == [
        "Diagnóstico espacial",
        "Observatorio alpino",
        "Catálogo de activos y sendas",
        "Presión y capacidad de carga",
        "Proyección de tendencia",
    ]
    assert module_tab_labels("evidenciar") == [
        "Evidencia satelital",
        "Confianza e incertidumbre",
        "Proveniencia y linaje",
    ]
    assert module_tab_labels("gobernar") == [
        "Metodología y auditoría",
        "Informes y exportaciones",
        "Configuración territorial",
    ]


def test_each_layer_declares_the_question_it_answers() -> None:
    assert all(layer.question.endswith("?") for layer in NAVIGATION_LAYERS)
    with pytest.raises(ValueError, match="Unknown navigation layer"):
        navigation_layer("unknown")


@pytest.mark.parametrize(
    ("home", "first"),
    [
        ("decidir", "🧭 Decidir"),
        ("diagnosticar", "🔬 Diagnosticar"),
        ("gobernar", "⚖️ Gobernar"),
    ],
)
def test_audience_home_layer_is_first_without_losing_modules(home, first) -> None:
    layers = navigation_layers(home)
    assert layer_tab_labels(home)[0] == first
    assert layers[0].key == home
    assert {layer.key for layer in layers} == {
        "decidir",
        "diagnosticar",
        "evidenciar",
        "gobernar",
    }
