from dataclasses import dataclass

@dataclass
class DatabasePoolConfig:
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout_sec: float = 10.0
    retry_attempts: int = 3
    retry_delay_sec: float = 1.0
