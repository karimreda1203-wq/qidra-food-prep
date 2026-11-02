"""Qidra — predict how much of each dish a restaurant should prepare today."""
from .calendar_eg import DAY_NAMES, build_events, calendar_keys, season
from .data_io import build_restaurant, guess_mapping, load_file, read_table
from .model import SAFETY, DemandModel, receipt_text
from .restaurant import Restaurant, template_excel_bytes

__all__ = [
    "DAY_NAMES", "SAFETY", "DemandModel", "Restaurant", "build_events", "build_restaurant",
    "calendar_keys", "guess_mapping", "load_file", "read_table", "receipt_text", "season",
    "template_excel_bytes",
]
