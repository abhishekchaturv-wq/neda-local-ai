"""TEST-015 broker-independent paper execution. No network/broker execution."""
from dataclasses import dataclass
from enum import Enum

class PaperSide(str, Enum):
    BUY="BUY"; SELL="SELL"

class PaperOrderStatus(str, Enum):
    ACCEPTED="ACCEPTED"; FILLED="FILLED"; REJECTED="REJECTED"; CANCELLED="CANCELLED"

@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    side: PaperSide
    quantity: float
    limit_price: float | None
    status: PaperOrderStatus
    fill_price: float | None = None
    reason: str | None = None

@dataclass
class PaperPosition:
    symbol: str
    quantity: float = 0.0
    average_entry: float = 0.0
    realized_pnl: float = 0.0

    def mark(self, price):
        return (price - self.average_entry) * self.quantity

    def apply_fill(self, side, quantity, price):
        signed = quantity if side is PaperSide.BUY else -quantity
        if self.quantity == 0:
            self.quantity, self.average_entry = signed, price
            return
        if (self.quantity > 0) == (signed > 0):
            old = abs(self.quantity); new = old + abs(signed)
            self.average_entry = (self.average_entry*old + price*abs(signed))/new
            self.quantity += signed
            return
        close = min(abs(self.quantity), abs(signed))
        direction = 1 if self.quantity > 0 else -1
        self.realized_pnl += (price-self.average_entry)*close*direction
        self.quantity += signed
        if self.quantity == 0: self.average_entry = 0.0
        elif (self.quantity > 0) != (direction > 0): self.average_entry = price

class PaperExecutionAdapter:
    MODE="PAPER"
    def __init__(self, fee_rate=0.0, slippage_bps=0.0):
        if fee_rate < 0 or slippage_bps < 0: raise ValueError("invalid fee/slippage")
        self.fee_rate=fee_rate; self.slippage_bps=slippage_bps
        self._counter=0; self.orders=[]; self.positions={}

    def submit(self, symbol, side, quantity, bid, ask, limit_price=None):
        if quantity <= 0: raise ValueError("quantity must be positive")
        self._counter += 1
        oid=f"PAPER-{self._counter:06d}"
        ref=ask if side is PaperSide.BUY else bid
        if ref is None or ref <= 0:
            o=PaperOrder(oid,symbol,side,quantity,limit_price,PaperOrderStatus.REJECTED,reason="NO_QUOTE")
            self.orders.append(o); return o
        if limit_price is not None:
            crossed=(side is PaperSide.BUY and ref <= limit_price) or (side is PaperSide.SELL and ref >= limit_price)
            if not crossed:
                o=PaperOrder(oid,symbol,side,quantity,limit_price,PaperOrderStatus.ACCEPTED,reason="LIMIT_NOT_CROSSED")
                self.orders.append(o); return o
        slip=self.slippage_bps/10000
        fill=ref*(1+slip if side is PaperSide.BUY else 1-slip)
        o=PaperOrder(oid,symbol,side,quantity,limit_price,PaperOrderStatus.FILLED,fill)
        self.orders.append(o)
        self.positions.setdefault(symbol,PaperPosition(symbol)).apply_fill(side,quantity,fill)
        return o

    def unrealized_pnl(self,symbol,mark_price):
        return self.positions[symbol].mark(mark_price)

    def total_pnl(self,symbol,mark_price):
        p=self.positions[symbol]; return p.realized_pnl+p.mark(mark_price)

    def broker_call_count(self):
        return 0


class BuyerOnlyPaperExecutionAdapter(PaperExecutionAdapter):
    """TEST-016 paper adapter for an options buyer.

    BUY opens/increases long option positions.
    SELL is permitted only when it reduces an existing long position.
    SELL-to-open / naked short option orders are rejected.
    """

    MODE = "PAPER_BUYER_ONLY"

    def submit(self, symbol, side, quantity, bid, ask, limit_price=None):
        if side is PaperSide.SELL:
            position = self.positions.get(symbol)
            current_qty = position.quantity if position else 0.0
            if current_qty < quantity:
                self._counter += 1
                oid = f"PAPER-{self._counter:06d}"
                order = PaperOrder(
                    oid, symbol, side, quantity, limit_price,
                    PaperOrderStatus.REJECTED,
                    reason="OPTIONS_BUYER_POLICY_SELL_TO_OPEN_FORBIDDEN",
                )
                self.orders.append(order)
                return order
        return super().submit(symbol, side, quantity, bid, ask, limit_price)
