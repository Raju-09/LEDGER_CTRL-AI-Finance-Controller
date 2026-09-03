"""Policy thresholds. Tuned on a fixed DEV seed only — never on holdout."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- matching (locked after seed=42, n=400, split=dev) ---
    auto_close_threshold: float = 0.90
    review_threshold: float = 0.60
    tie_delta: float = 0.05
    date_window_days: int = 3
    amount_rel_tolerance: float = 0.02
    # Max candidates per side passed to the policy gate.
    # Keeps scoring O(n·k) instead of O(n²). Tune via blocking-key analysis, not here.
    candidate_pool_size: int = 12

    score_w_reference: float = 0.35
    score_w_amount: float = 0.25
    score_w_vendor: float = 0.20
    score_w_date: float = 0.20

    # --- generator mix (must sum ~1.0 before twin injection) ---
    rate_exact: float = 0.40
    rate_date_shift: float = 0.15
    rate_amount_delta: float = 0.15
    rate_vendor_variation: float = 0.10
    rate_duplicate: float = 0.10
    rate_orphan: float = 0.10
    rate_ambiguous_twin: float = 0.03
    rate_partial: float = 0.08

    db_path: str = "data/finance.db"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 8.0

    matcher_version: str = "1.4.0"
    policy_version: str = "1.2.0"
    eval_protocol: str = "holdout-v1"


settings = Settings()
