"""Vehicle (OBJECTS §2.2, §4.6, WP3): a depreciating real asset.

Same lifecycle, purchase, carry-in, sale and growth as RealEstate (``APPRECIATION`` with
negative amounts); no marketValue. Its running costs are associated expenses (ADR-0067;
older files' ``annualMaintenance`` / ``maintenanceIncrease`` are converted to one by
upgrade.py).
"""
from ..compiler import item_type
from .real_estate import RealAsset, compile_real_asset


class Vehicle(RealAsset):
    kind = "vehicle"


@item_type("vehicle")
def compile_vehicle(item, ctx):
    yield from compile_real_asset(Vehicle, item, ctx)
