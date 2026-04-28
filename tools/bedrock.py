"""LLM factory — returns cached CrewAI LLM instances per agent role.

Currently configured for Anthropic API directly.
To switch back to AWS Bedrock, swap the model strings to
'bedrock/converse/<inference-profile-arn>' and remove ANTHROPIC_API_KEY.
"""

import os
from functools import lru_cache

import yaml
from crewai import LLM

# Anthropic API model IDs
ANTHROPIC_MODELS = {
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku":  "anthropic/claude-haiku-4-5-20251001",
}

# Which agents use sonnet vs haiku
SONNET_AGENTS = {"orchestrator", "world", "causal", "fundamentals", "ranking"}


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=10)
def get_llm(agent_name: str) -> LLM:
    """
    Returns the correct LLM for each agent.
    Sonnet for reasoning agents, Haiku for fast structured agents.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    tier = "sonnet" if agent_name in SONNET_AGENTS else "haiku"
    model = ANTHROPIC_MODELS[tier]
    max_tokens = 8192 if agent_name == "ranking" else 4096

    return LLM(
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_tokens=max_tokens,
    )
