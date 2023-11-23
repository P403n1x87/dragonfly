class DragonflySettings:
    trace_opcodes: str = "0"

    def set(self, setting: str, value: str) -> None:  # noqa
        setting = setting.replace("-", "_")
        if not hasattr(self, setting):
            msg = f"unknown setting: {setting}"
            raise ValueError(msg)
        setattr(self, setting, value)
