"""AWS Bedrock LLM factory — returns cached BedrockChat instances per agent role."""

import os
from functools import lru_cache

import yaml
from langchain_aws import ChatBedrock


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=10)
def get_llm(agent_name: str) -> ChatBedrock:
    """
    Returns the correct Bedrock LLM for each agent.
    Haiku for fast/simple agents. Sonnet for complex reasoning.

    Usage:
        haiku  = get_llm("market")        → Claude Haiku
        sonnet = get_llm("fundamentals")  → Claude Sonnet
    """
    config = _load_config()
    model_id = config["models"][agent_name]
    region = os.environ.get("AWS_REGION", config.get("aws_region", "us-east-1"))

    return ChatBedrock(
        model_id=model_id,
        region_name=region,
        model_kwargs={
            "temperature": 0.1,      # low temp for consistent, reproducible analysis
            "max_tokens": 4096,
        },
    )
