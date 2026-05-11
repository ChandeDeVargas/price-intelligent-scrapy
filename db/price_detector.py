"""
Price Change Detector — detecta cambios entre el precio anterior y el nuevo.

Esta es la lógica central del sistema: compara dos registros de PriceHistory
y decide si el cambio es relevante para generar una alerta.

Separado del engine (Day 5) para poder testearlo sin scheduler.

Uso:
    from db.price_detector import PriceChangeDetector, ChangeResult

    detector = PriceChangeDetector(threshold_pct=5.0)
    result = detector.detect(old_record, new_record)
    if result.should_alert:
        print(result.summary)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import PriceHistory

logger = logging.getLogger(__name__)


# ── Change types ──────────────────────────────────────────────────────────────

class ChangeType(str, Enum):
    NO_CHANGE       = "no_change"
    PRICE_DROP      = "price_drop"       # bajó de precio
    PRICE_RISE      = "price_rise"       # subió de precio
    BACK_IN_STOCK   = "back_in_stock"    # volvió a estar disponible
    OUT_OF_STOCK    = "out_of_stock"     # se agotó
    NEW_ALL_TIME_LOW  = "new_low"        # precio mínimo histórico
    NEW_ALL_TIME_HIGH = "new_high"       # precio máximo histórico
    FIRST_RECORD    = "first_record"     # primer precio registrado


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ChangeResult:
    """Resultado de comparar dos registros de precio."""

    change_type: ChangeType = ChangeType.NO_CHANGE

    old_price: Optional[float] = None
    new_price: Optional[float] = None
    change_pct: Optional[float] = None   # positivo = subió, negativo = bajó
    change_abs: Optional[float] = None   # diferencia absoluta
    currency: str = "USD"

    old_in_stock: bool = True
    new_in_stock: bool = True

    is_new_low: bool = False
    is_new_high: bool = False
    all_time_low: Optional[float] = None
    all_time_high: Optional[float] = None

    threshold_used: float = 5.0
    should_alert: bool = False

    @property
    def summary(self) -> str:
        """Mensaje legible para logs y notificaciones."""
        if self.change_type == ChangeType.NO_CHANGE:
            return f"Sin cambio: {self.currency} {self.new_price}"

        if self.change_type == ChangeType.FIRST_RECORD:
            return f"Primer precio registrado: {self.currency} {self.new_price}"

        if self.change_type == ChangeType.BACK_IN_STOCK:
            return f"¡Volvió a stock! Precio: {self.currency} {self.new_price}"

        if self.change_type == ChangeType.OUT_OF_STOCK:
            return f"Se agotó. Último precio: {self.currency} {self.old_price}"

        direction = "↓" if self.change_pct and self.change_pct < 0 else "↑"
        abs_pct = abs(self.change_pct) if self.change_pct else 0
        msg = (
            f"Precio {direction} {abs_pct:.1f}%: "
            f"{self.currency} {self.old_price} → {self.currency} {self.new_price}"
        )
        if self.is_new_low:
            msg += " 🏆 NUEVO MÍNIMO HISTÓRICO"
        return msg

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type.value,
            "old_price": self.old_price,
            "new_price": self.new_price,
            "change_pct": self.change_pct,
            "change_abs": self.change_abs,
            "currency": self.currency,
            "old_in_stock": self.old_in_stock,
            "new_in_stock": self.new_in_stock,
            "is_new_low": self.is_new_low,
            "is_new_high": self.is_new_high,
            "all_time_low": self.all_time_low,
            "all_time_high": self.all_time_high,
            "should_alert": self.should_alert,
            "summary": self.summary,
        }


# ── Detector ──────────────────────────────────────────────────────────────────

class PriceChangeDetector:
    """
    Compara dos registros de PriceHistory y produce un ChangeResult.

    Args:
        threshold_pct: % mínimo de cambio de precio para generar alerta.
                       Default 5.0 (cualquier cambio >= 5% genera alerta).
    """

    def __init__(self, threshold_pct: float = 5.0):
        self.threshold_pct = threshold_pct

    def detect(
        self,
        previous: Optional[PriceHistory],
        current: PriceHistory,
        all_time_low: Optional[float] = None,
        all_time_high: Optional[float] = None,
    ) -> ChangeResult:
        """
        Detecta el tipo de cambio entre el registro anterior y el actual.

        Args:
            previous:      Registro de precio anterior (None si es el primero)
            current:       Registro de precio más reciente
            all_time_low:  Precio mínimo histórico (para detectar nuevos mínimos)
            all_time_high: Precio máximo histórico

        Returns:
            ChangeResult con el tipo de cambio y si debe generar alerta
        """
        result = ChangeResult(
            new_price=current.price,
            new_in_stock=current.in_stock,
            currency=current.currency,
            threshold_used=self.threshold_pct,
            all_time_low=all_time_low,
            all_time_high=all_time_high,
        )

        # ── Primer registro ────────────────────────────────────────────────
        if previous is None:
            result.change_type = ChangeType.FIRST_RECORD
            result.should_alert = False
            logger.debug(f"[detector] First record: {current.price} {current.currency}")
            return result

        result.old_price = previous.price
        result.old_in_stock = previous.in_stock

        # ── Cambio de stock ────────────────────────────────────────────────
        if not previous.in_stock and current.in_stock:
            result.change_type = ChangeType.BACK_IN_STOCK
            result.should_alert = True
            logger.info(f"[detector] Back in stock! Price: {current.price}")
            return result

        if previous.in_stock and not current.in_stock:
            result.change_type = ChangeType.OUT_OF_STOCK
            result.should_alert = True
            logger.info(f"[detector] Out of stock. Last price: {previous.price}")
            return result

        # ── Sin precio (no se pudo parsear) ───────────────────────────────
        if current.price is None or previous.price is None:
            result.change_type = ChangeType.NO_CHANGE
            return result

        # ── Cambio de precio ───────────────────────────────────────────────
        change_abs = current.price - previous.price
        change_pct = (change_abs / previous.price) * 100

        result.change_abs = round(change_abs, 2)
        result.change_pct = round(change_pct, 2)

        abs_change_pct = abs(change_pct)

        if abs_change_pct < 0.01:
            # Diferencia despreciable (menos del 0.01%)
            result.change_type = ChangeType.NO_CHANGE
            return result

        if change_pct < 0:
            result.change_type = ChangeType.PRICE_DROP
        else:
            result.change_type = ChangeType.PRICE_RISE

        # ── Nuevo mínimo / máximo histórico ───────────────────────────────
        if all_time_low is not None and current.price < all_time_low:
            result.is_new_low = True
            result.change_type = ChangeType.NEW_ALL_TIME_LOW
            result.should_alert = True  # siempre alertar nuevo mínimo

        if all_time_high is not None and current.price > all_time_high:
            result.is_new_high = True

        # ── Umbral de alerta ──────────────────────────────────────────────
        if not result.should_alert:
            result.should_alert = abs_change_pct >= self.threshold_pct

        if result.should_alert:
            logger.info(
                f"[detector] {result.change_type.value}: "
                f"{previous.price} → {current.price} "
                f"({result.change_pct:+.1f}%) | alert=True"
            )

        return result

    def detect_from_prices(
        self,
        old_price: float,
        new_price: float,
        currency: str = "USD",
        old_in_stock: bool = True,
        new_in_stock: bool = True,
        all_time_low: Optional[float] = None,
    ) -> ChangeResult:
        """
        Versión simplificada que acepta precios directamente (sin ORM).
        Útil para tests y scripts.
        """
        old = PriceHistory(
            product_id=0,
            price=old_price,
            currency=currency,
            in_stock=old_in_stock,
        )
        new = PriceHistory(
            product_id=0,
            price=new_price,
            currency=currency,
            in_stock=new_in_stock,
        )
        return self.detect(old, new, all_time_low=all_time_low)
