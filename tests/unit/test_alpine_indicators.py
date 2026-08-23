"""Unit tests for src.socioeconomic.alpine_indicators (issue #22)."""
from __future__ import annotations

import json

from src.socioeconomic.alpine_indicators import (
    load_sierra_nevada_indicators,
    parse_sima_ficha_html,
)

# A trimmed but structurally real IECA/SIMA ficha fragment. Row order and
# label wording mirror the actual page (mun=18134 Monachil, fetched
# 2026-08-23); only unrelated rows were dropped, and the real reported values
# are kept as-is. The two singular "Principal cultivo ... (ha)" rows are real
# decoys: they must NOT be captured by the plural "cultivos ... (ha)" surface
# needles (issue #27 needle discrimination).
_MONACHIL_FICHA_HTML = """
<html><body><table>
<tr><td>Extensi&oacute;n superficial (Km2). 2019</td><td>88,85</td></tr>
<tr><td>Poblaci&oacute;n total. 2025</td><td>8.676</td></tr>
<tr><td>Porcentaje de poblaci&oacute;n mayor de 65 a&ntilde;os. 2025</td>
<td>15,6</td></tr>
<tr><td>Variaci&oacute;n relativa de la poblaci&oacute;n en diez
a&ntilde;os (%). 2014-2024</td>
<td>16,4</td></tr>
<tr><td>Transacciones inmobiliarias. Vivienda nueva. 2025</td><td>19</td></tr>
<tr><td>Transacciones inmobiliarias. Vivienda segunda mano. 2025</td><td>412</td></tr>
<tr><th colspan="2">Establecimientos con actividad econ&oacute;mica. 2025</th></tr>
<tr><td>Total establecimientos</td><td>885</td></tr>
<tr><td>Secci&oacute;n I. Hosteler&iacute;a</td><td>181</td></tr>
<tr><td>Superficie dedicada a cultivos herb&aacute;ceos (ha)</td><td>48</td></tr>
<tr><td>Principal cultivo herb&aacute;ceo de secano (ha)</td><td>20</td></tr>
<tr><td>Superficie dedicada a cultivos le&ntilde;osos (ha)</td><td>345</td></tr>
<tr><td>Principal cultivo le&ntilde;oso de regad&iacute;o (ha)</td><td>200</td></tr>
<tr><td>Hoteles. 2025</td><td>18</td></tr>
<tr><td>Hostales y pensiones. 2025</td><td>*</td></tr>
<tr><td>Plazas en hoteles. 2025</td><td>2.651</td></tr>
<tr><td>Plazas en hostales y pensiones. 2025</td><td>*</td></tr>
<tr><td>Consumo de energ&iacute;a el&eacute;ctrica (MWh) (Endesa). 2025</td>
<td>57.280</td></tr>
<tr><td>Consumo de energ&iacute;a el&eacute;ctrica residencial (MWh)
(Endesa). 2025</td><td>25.352</td></tr>
<tr><td>Tasa municipal de desempleo (%). 2025</td><td>16,1</td></tr>
<tr><td>Ingresos por habitante (euros). 2024</td><td>1.709</td></tr>
<tr><td>Gastos por habitante (euros). 2024</td><td>1.663</td></tr>
<tr><td>Renta bruta media. 2023</td><td>28004</td></tr>
<tr><td>Renta disponible media. 2023</td><td>22919</td></tr>
</table></body></html>
"""

# A tiny-municipality fragment where hotel/income rows are published with the
# "-" suppression marker instead of a number (real formatting seen for e.g.
# Bayárcal, mun=04020).
_TINY_MUNICIPALITY_HTML = """
<html><body><table>
<tr><td>Poblaci&oacute;n total. 2025</td><td>294</td></tr>
<tr><td>Hoteles. 2025</td><td>-</td></tr>
<tr><td>Plazas en hoteles. 2025</td><td>-</td></tr>
<tr><td>Renta bruta media. 2023</td><td>-</td></tr>
</table></body></html>
"""


def test_parses_real_reported_values() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.population == 8676
    assert rec.pct_over_65 == 15.6
    assert rec.pop_change_10y_pct == 16.4
    assert rec.unemployment_rate_pct == 16.1
    assert rec.hosteleria_establishments == 181
    assert rec.hotels == 18
    assert rec.hotel_beds == 2651
    assert rec.gross_income_mean_eur == 28004.0
    assert rec.disposable_income_mean_eur == 22919.0


def test_parses_richer_real_fields_issue_27() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.real_estate_tx_new == 19
    assert rec.real_estate_tx_used == 412
    assert rec.total_establishments == 885
    assert rec.ag_area_herbaceous_ha == 48.0
    assert rec.ag_area_woody_ha == 345.0
    assert rec.elec_consumption_mwh == 57280.0
    assert rec.elec_consumption_residential_mwh == 25352.0
    assert rec.income_per_capita_eur == 1709.0
    assert rec.expense_per_capita_eur == 1663.0


def test_plural_surface_needle_does_not_capture_singular_principal_cultivo() -> None:
    """The 'Superficie dedicada a cultivos leñosos (ha)' surface row (345 ha)
    must win over the singular 'Principal cultivo leñoso ... (ha)' decoy
    (200 ha), and likewise for herbáceos (48 vs 20)."""
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.ag_area_woody_ha == 345.0  # not 200 (the principal-cultivo row)
    assert rec.ag_area_herbaceous_ha == 48.0  # not 20


def test_residential_energy_needle_does_not_swallow_total() -> None:
    """The total-electricity needle is a superstring risk for the residential
    row; the two must resolve to distinct real values."""
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.elec_consumption_mwh == 57280.0
    assert rec.elec_consumption_residential_mwh == 25352.0
    assert rec.elec_consumption_mwh != rec.elec_consumption_residential_mwh


def test_does_not_confuse_hotel_beds_with_hotel_count() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.hotels != rec.hotel_beds
    assert rec.hotels == 18
    assert rec.hotel_beds == 2651


def test_provenance_carries_each_fields_own_vintage() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    assert rec.provenance["population"].endswith("2025")
    assert rec.provenance["gross_income_mean_eur"].endswith("2023")
    assert rec.provenance["pop_change_10y_pct"].endswith("2014-2024")


def test_asterisk_suppressed_value_is_none_with_a_caveat() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    # "Hostales y pensiones" and its plazas are IECA `*`-suppressed in the
    # real Monachil ficha (statistical secrecy) — now mapped (issue #27), so
    # both parse to None with an explicit caveat, never a fabricated number.
    assert rec.hostales_pensiones is None
    assert rec.hostal_pension_beds is None
    joined = " ".join(rec.caveats)
    assert any("hostales_pensiones" in c for c in rec.caveats)
    assert any("hostal_pension_beds" in c for c in rec.caveats)
    assert "secreto" in joined  # honest suppression wording, not a guess


def test_dash_suppressed_values_are_none_with_a_caveat() -> None:
    rec = parse_sima_ficha_html("04020", _TINY_MUNICIPALITY_HTML)
    assert rec.population == 294
    assert rec.hotels is None
    assert rec.hotel_beds is None
    assert rec.gross_income_mean_eur is None
    assert any("hotels" in c for c in rec.caveats)
    assert any("hotel_beds" in c for c in rec.caveats)
    assert any("gross_income_mean_eur" in c for c in rec.caveats)


def test_missing_row_is_none_without_a_fabricated_value() -> None:
    html = "<table><tr><td>Poblaci&oacute;n total. 2025</td><td>500</td></tr></table>"
    rec = parse_sima_ficha_html("99999", html)
    assert rec.population == 500
    assert rec.unemployment_rate_pct is None
    assert rec.hotels is None


def test_round_trip_through_dict() -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    rebuilt = type(rec).from_dict(rec.to_dict())
    assert rebuilt == rec


def test_load_sierra_nevada_indicators_from_a_snapshot(tmp_path) -> None:
    rec = parse_sima_ficha_html("18134", _MONACHIL_FICHA_HTML)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "source": "IECA/SIMA",
                "n_municipalities": 1,
                "municipalities": {"18134": rec.to_dict()},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    load_sierra_nevada_indicators.cache_clear()
    loaded = load_sierra_nevada_indicators(snapshot)
    assert loaded["18134"].population == 8676


def test_load_sierra_nevada_indicators_degrades_honestly_when_absent(tmp_path) -> None:
    load_sierra_nevada_indicators.cache_clear()
    loaded = load_sierra_nevada_indicators(tmp_path / "does_not_exist.json")
    assert loaded == {}
