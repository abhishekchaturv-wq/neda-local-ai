"""NEDA Options Engine V1: dependency-light options data model."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

class OptionType(str, Enum):
    CALL="CALL"; PUT="PUT"
class AssetClass(str, Enum):
    STOCK="STOCK"; INDEX="INDEX"; COMMODITY="COMMODITY"
class Moneyness(str, Enum):
    ITM="ITM"; ATM="ATM"; OTM="OTM"

@dataclass(frozen=True)
class OptionContract:
    symbol:str; asset_class:AssetClass; expiry:date; strike:float; option_type:OptionType; contract_multiplier:float=1.0
    def __post_init__(self):
        if not self.symbol.strip(): raise ValueError("symbol cannot be empty")
        if self.strike<=0: raise ValueError("strike must be positive")
        if self.contract_multiplier<=0: raise ValueError("contract_multiplier must be positive")
    @property
    def key(self): return f"{self.symbol.upper()}|{self.expiry.isoformat()}|{self.strike:g}|{self.option_type.value}"

@dataclass(frozen=True)
class OptionQuote:
    bid:Optional[float]=None; ask:Optional[float]=None; last:Optional[float]=None
    volume:Optional[int]=None; open_interest:Optional[int]=None; change_in_open_interest:Optional[int]=None
    implied_volatility:Optional[float]=None
    def __post_init__(self):
        for v,n in ((self.bid,"bid"),(self.ask,"ask"),(self.last,"last"),(self.implied_volatility,"implied_volatility")):
            if v is not None and v<0: raise ValueError(f"{n} cannot be negative")
        for v,n in ((self.volume,"volume"),(self.open_interest,"open_interest")):
            if v is not None and v<0: raise ValueError(f"{n} cannot be negative")
        if self.bid is not None and self.ask is not None and self.bid>self.ask: raise ValueError("bid cannot be greater than ask")

@dataclass(frozen=True)
class Greeks:
    delta:Optional[float]=None; gamma:Optional[float]=None; theta:Optional[float]=None; vega:Optional[float]=None; rho:Optional[float]=None

@dataclass(frozen=True)
class OptionSnapshot:
    contract:OptionContract; underlying_price:float; quote:OptionQuote; greeks:Greeks=Greeks(); timestamp_epoch:Optional[float]=None
    def __post_init__(self):
        if self.underlying_price<=0: raise ValueError("underlying_price must be positive")
    @property
    def moneyness(self):
        if abs(self.underlying_price-self.contract.strike)/self.underlying_price<=0.005: return Moneyness.ATM
        if self.contract.option_type is OptionType.CALL: return Moneyness.ITM if self.underlying_price>self.contract.strike else Moneyness.OTM
        return Moneyness.ITM if self.underlying_price<self.contract.strike else Moneyness.OTM
    @property
    def intrinsic_value(self):
        return max(0.0, self.underlying_price-self.contract.strike) if self.contract.option_type is OptionType.CALL else max(0.0,self.contract.strike-self.underlying_price)
    @property
    def mid_price(self):
        return (self.quote.bid+self.quote.ask)/2 if self.quote.bid is not None and self.quote.ask is not None else self.quote.last

def make_contract(symbol, asset_class, expiry, strike, option_type, contract_multiplier=1.0):
    return OptionContract(symbol.strip().upper(), asset_class if isinstance(asset_class,AssetClass) else AssetClass(str(asset_class).strip().upper()), expiry, float(strike), option_type if isinstance(option_type,OptionType) else OptionType(str(option_type).strip().upper()), float(contract_multiplier))
