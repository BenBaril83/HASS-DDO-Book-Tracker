"""DDO library book tracker.

A small toolkit to log in to the Dollard-des-Ormeaux public library OPAC and
report every book currently on loan (across linked family accounts) with due
dates, so you never miss a return.
"""

from .calendar import build_ics
from .client import DDOAuthError, DDOLibraryClient, DDOLibraryError
from .config import (
    AccountConfig,
    CalendarConfig,
    Config,
    ConfigError,
    load_config,
)
from .digest import EmailConfig, render_html, render_text, send_email, subject_line
from .models import Account, Loan, parse_api_date
from .report import all_loans, build_summary, format_table

__version__ = "0.1.0"

__all__ = [
    "DDOLibraryClient",
    "DDOLibraryError",
    "DDOAuthError",
    "Config",
    "AccountConfig",
    "CalendarConfig",
    "ConfigError",
    "load_config",
    "Account",
    "Loan",
    "parse_api_date",
    "all_loans",
    "build_summary",
    "format_table",
    "build_ics",
    "EmailConfig",
    "render_text",
    "render_html",
    "subject_line",
    "send_email",
    "__version__",
]
