from dataclasses import dataclass, field
from typing import Optional

from snakemake_interface_logger_plugins.settings import LogHandlerSettingsBase


@dataclass
class LoggerSettings(LogHandlerSettingsBase):
    url: Optional[str] = field(
        default=None,
        metadata={
            "help": "Base URL of the panoptes server (e.g. http://localhost:5000).",
            "env_var": False,
            "required": True,
        },
    )
    flush_interval: float = field(
        default=2.0,
        metadata={
            "help": "Maximum seconds to buffer events before flushing.",
            "env_var": False,
            "required": False,
        },
    )
    batch_size: int = field(
        default=50,
        metadata={
            "help": "Maximum number of events to buffer before flushing.",
            "env_var": False,
            "required": False,
        },
    )
