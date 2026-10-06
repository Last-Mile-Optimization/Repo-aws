"""Pré-processamento compartilhado entre a API individual e a análise por CSV.

O modelo faz a previsão quando o pacote é coletado pela transportadora. Portanto,
todos os campos deste módulo são conhecidos nesse momento, e nenhuma informação
depois da coleta é usada.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd


RAW_COLUMNS = [
    "purchase_date",
    "purchase_time",
    "carrier_datetime",
    "estimated_delivery_datetime",
    "price",
    "freight_value",
    "product_weight_g",
    "height_cm",
    "width_cm",
    "length_cm",
    "distance_km",
    "same_city",
    "customer_city",
    "seller_city",
    "category_name",
]

NUMERIC_COLUMNS = [
    "price",
    "freight_value",
    "product_weight_g",
    "height_cm",
    "width_cm",
    "length_cm",
    "distance_km",
    "same_city",
]


class InputValidationError(ValueError):
    """Erro de dados que deve ser retornado ao usuário com HTTP 400."""


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _holidays_sp(year: int) -> set[date]:
    easter = _easter(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=48),
        easter - timedelta(days=47),
        easter - timedelta(days=2),
        date(year, 4, 21),
        date(year, 5, 1),
        easter + timedelta(days=60),
        date(year, 7, 9),
        date(year, 9, 7),
        date(year, 10, 12),
        date(year, 11, 2),
        date(year, 11, 15),
        date(year, 11, 20),
        date(year, 12, 25),
    }


def _black_friday(year: int) -> date:
    november_first = date(year, 11, 1)
    first_friday = november_first + timedelta(days=(4 - november_first.weekday()) % 7)
    return first_friday + timedelta(days=21)


def _ecommerce_events(year: int) -> set[date]:
    black_friday = _black_friday(year)

    may_first = date(year, 5, 1)
    first_sunday_may = may_first + timedelta(days=(6 - may_first.weekday()) % 7)
    mothers_day = first_sunday_may + timedelta(days=7)

    august_first = date(year, 8, 1)
    first_sunday_august = august_first + timedelta(days=(6 - august_first.weekday()) % 7)
    fathers_day = first_sunday_august + timedelta(days=7)

    return {
        mothers_day,
        fathers_day,
        date(year, 10, 12),  # Dia das Crianças
        black_friday,
        black_friday + timedelta(days=3),  # Cyber Monday
        date(year, 12, 25),
    }


def _calendar_window(anchor: date, calendar_factory) -> list[date]:
    return sorted(
        event
        for year in range(anchor.year - 1, anchor.year + 2)
        for event in calendar_factory(year)
    )


def _days_since(anchor: date, dates: list[date]) -> int:
    prior = [event for event in dates if event <= anchor]
    if not prior:
        raise InputValidationError("Não foi possível calcular a data do último evento.")
    return (anchor - max(prior)).days


def _days_until(anchor: date, dates: list[date]) -> int:
    future = [event for event in dates if event >= anchor]
    if not future:
        raise InputValidationError("Não foi possível calcular a data do próximo evento.")
    return (min(future) - anchor).days


def _has_event_in_range(anchor: date, dates: list[date], start: int, end: int) -> int:
    return int(any(anchor + timedelta(days=offset) in dates for offset in range(start, end + 1)))


def _parse_datetime(series: pd.Series, field_name: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        lines = ", ".join(str(i + 2) for i in parsed.index[parsed.isna()][:5])
        raise InputValidationError(
            f"'{field_name}' possui data/hora inválida nas linhas {lines}. "
            "Use YYYY-MM-DDTHH:MM."
        )
    return parsed


def validate_raw_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in RAW_COLUMNS if column not in raw_df.columns]
    if missing:
        raise InputValidationError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    if raw_df.empty:
        raise InputValidationError("O CSV não possui registros.")

    df = raw_df[RAW_COLUMNS].copy()
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        if df[column].isna().any():
            lines = ", ".join(str(i + 2) for i in df.index[df[column].isna()][:5])
            raise InputValidationError(f"'{column}' possui valor numérico inválido nas linhas {lines}.")

    if (~df["same_city"].isin([0, 1])).any():
        raise InputValidationError("'same_city' deve ser 1 para sim ou 0 para não.")

    for column in ["price", "freight_value", "product_weight_g", "height_cm", "width_cm", "length_cm", "distance_km"]:
        if (df[column] < 0).any():
            raise InputValidationError(f"'{column}' não pode ser negativo.")

    if (df[["height_cm", "width_cm", "length_cm", "product_weight_g"]] <= 0).any().any():
        raise InputValidationError("Peso e dimensões do produto devem ser maiores que zero.")

    df["purchase_datetime"] = _parse_datetime(
        df["purchase_date"].astype(str).str.strip() + "T" + df["purchase_time"].astype(str).str.strip(),
        "purchase_date/purchase_time",
    )
    df["carrier_datetime"] = _parse_datetime(df["carrier_datetime"], "carrier_datetime")
    df["estimated_delivery_datetime"] = _parse_datetime(
        df["estimated_delivery_datetime"], "estimated_delivery_datetime"
    )

    for column in ["customer_city", "seller_city", "category_name"]:
        df[column] = df[column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    return df


def transform_raw_dataframe(raw_df: pd.DataFrame, artifact: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valida e transforma dados brutos, devolvendo entrada limpa e features normalizadas."""
    df = validate_raw_dataframe(raw_df)
    carrier_dates = df["carrier_datetime"].dt.date

    holiday_dates = [_calendar_window(current, _holidays_sp) for current in carrier_dates]
    ecommerce_dates = [_calendar_window(current, _ecommerce_events) for current in carrier_dates]

    feature_df = pd.DataFrame(index=df.index)
    feature_df["holiday_at_carrier"] = [
        int(current in calendar) for current, calendar in zip(carrier_dates, holiday_dates)
    ]
    feature_df["days_since_last_holiday"] = [
        _days_since(current, calendar) for current, calendar in zip(carrier_dates, holiday_dates)
    ]
    feature_df["days_until_next_holiday"] = [
        _days_until(current, calendar) for current, calendar in zip(carrier_dates, holiday_dates)
    ]
    feature_df["ecommerce_event_at_carrier"] = [
        int(current in calendar) for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["days_since_last_ecommerce_event"] = [
        _days_since(current, calendar) for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["days_until_next_ecommerce_event"] = [
        _days_until(current, calendar) for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["is_ecommerce_event_in_7_days"] = [
        _has_event_in_range(current, calendar, 1, 7)
        for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["is_ecommerce_event_in_14_days"] = [
        _has_event_in_range(current, calendar, 1, 14)
        for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["had_ecommerce_event_7_days_ago"] = [
        _has_event_in_range(current, calendar, -7, -1)
        for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["had_ecommerce_event_14_days_ago"] = [
        _has_event_in_range(current, calendar, -14, -1)
        for current, calendar in zip(carrier_dates, ecommerce_dates)
    ]
    feature_df["purchase_hour"] = df["purchase_datetime"].dt.hour
    # A base de treino usa a convenção 0=domingo, 1=segunda, ..., 6=sábado.
    feature_df["purchase_day_of_week"] = (df["purchase_datetime"].dt.dayofweek + 1) % 7
    feature_df["price"] = df["price"]
    feature_df["freight_value"] = df["freight_value"]
    feature_df["product_weight_g"] = df["product_weight_g"]
    feature_df["volume_cm3"] = df["height_cm"] * df["width_cm"] * df["length_cm"]
    feature_df["distance_km"] = df["distance_km"]
    feature_df["same_city"] = df["same_city"]
    feature_df["prazo_transportadora_dias"] = (
        df["estimated_delivery_datetime"] - df["carrier_datetime"]
    ).dt.days
    feature_df["purchase_month"] = df["purchase_datetime"].dt.month
    feature_df["prazo_por_km"] = feature_df["prazo_transportadora_dias"] / (feature_df["distance_km"] + 1)
    feature_df["frete_por_kg"] = feature_df["freight_value"] / (
        feature_df["product_weight_g"] / 1000 + 0.1
    )
    feature_df["densidade_produto"] = feature_df["product_weight_g"] / (feature_df["volume_cm3"] + 1)

    encoding_maps = artifact["encoding_maps"]
    global_rate = float(artifact["global_delay_rate"])
    for raw_name, encoded_name in [
        ("customer_city", "customer_city_encoded"),
        ("seller_city", "seller_city_encoded"),
        ("category_name", "category_name_encoded"),
    ]:
        feature_df[encoded_name] = df[raw_name].map(encoding_maps[raw_name]).fillna(global_rate)

    feature_names = artifact["feature_names"]
    missing_features = [feature for feature in feature_names if feature not in feature_df.columns]
    if missing_features:
        raise RuntimeError("Artefato incompatível: " + ", ".join(missing_features))

    unscaled = feature_df[feature_names]
    scaled = pd.DataFrame(
        artifact["scaler"].transform(unscaled), columns=feature_names, index=unscaled.index
    )
    clean_raw = df[RAW_COLUMNS].copy()
    return clean_raw, scaled
