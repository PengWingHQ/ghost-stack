"""GhostStack configuration management."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

GHOSTSTACK_DIR = ".ghoststack"
CONFIG_FILE = "config.json"
STACK_FILE = "stack.json"


@dataclass
class GhostStackConfig:
    """GhostStack configuration."""

    version: str = "1.0"
    default_base: str = "main"
    auto_stash: bool = True
    json_output: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GhostStackConfig":
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StackItem:
    """A single item in the stack."""

    name: str
    parent: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StackItem":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StackState:
    """The full stack state."""

    items: list[StackItem] = field(default_factory=list)
    base_branch: str = "main"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_branch": self.base_branch,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StackState":
        """Create from dictionary."""
        return cls(
            base_branch=data.get("base_branch", "main"),
            items=[StackItem.from_dict(item) for item in data.get("items", [])],
        )

    def add_item(self, name: str, parent: str | None = None) -> StackItem:
        """Add a new item to the stack."""
        from datetime import datetime, timezone

        item = StackItem(
            name=name,
            parent=parent,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.items.append(item)
        return item

    def remove_item(self, name: str) -> bool:
        """Remove an item from the stack."""
        for i, item in enumerate(self.items):
            if item.name == name:
                self.items.pop(i)
                return True
        return False

    def get_item(self, name: str) -> StackItem | None:
        """Get an item by name."""
        for item in self.items:
            if item.name == name:
                return item
        return None

    def get_children(self, name: str) -> list[StackItem]:
        """Get all items that have the given name as parent."""
        return [item for item in self.items if item.parent == name]


class ConfigManager:
    """Manages GhostStack configuration files."""

    def __init__(self, repo_path: Path | None = None):
        """Initialize config manager for the given repository path."""
        self.repo_path = repo_path or Path.cwd()
        self.ghoststack_dir = self.repo_path / GHOSTSTACK_DIR

    @property
    def config_file(self) -> Path:
        """Path to the config file."""
        return self.ghoststack_dir / CONFIG_FILE

    @property
    def stack_file(self) -> Path:
        """Path to the stack state file."""
        return self.ghoststack_dir / STACK_FILE

    def is_initialized(self) -> bool:
        """Check if GhostStack is initialized in this repo."""
        return self.config_file.exists()

    def initialize(self, config: GhostStackConfig | None = None) -> GhostStackConfig:
        """Initialize GhostStack in the repository."""
        self.ghoststack_dir.mkdir(exist_ok=True)

        config = config or GhostStackConfig()
        self.save_config(config)

        # Initialize empty stack
        self.save_stack(StackState(base_branch=config.default_base))

        return config

    def load_config(self) -> GhostStackConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            raise FileNotFoundError("GhostStack not initialized. Run 'gs init' first.")
        with open(self.config_file) as f:
            return GhostStackConfig.from_dict(json.load(f))

    def save_config(self, config: GhostStackConfig) -> None:
        """Save configuration to file."""
        with open(self.config_file, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

    def load_stack(self) -> StackState:
        """Load stack state from file."""
        if not self.stack_file.exists():
            return StackState()
        with open(self.stack_file) as f:
            return StackState.from_dict(json.load(f))

    def save_stack(self, stack: StackState) -> None:
        """Save stack state to file."""
        with open(self.stack_file, "w") as f:
            json.dump(stack.to_dict(), f, indent=2)
