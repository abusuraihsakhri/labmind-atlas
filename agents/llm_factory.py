import os
import logging
from typing import Optional, Any

logger = logging.getLogger("labmind.llm_factory")

def get_llm(role: str = "worker", temperature: float = 0.0) -> Optional[Any]:
    """
    Factory function to initialize LLM clients based on configuration.
    Supports:
      1. Ollama (100% on-premises / air-gapped private medical processing)
      2. Anthropic (Claude 3.5 Sonnet / Claude 3 Haiku)
      3. OpenAI (GPT-4o, GPT-4o-mini)
      4. Custom OpenAI-compatible endpoints (vLLM, LM Studio, LocalAI)
    """
    provider = os.getenv("LLM_PROVIDER", "").lower().strip()

    # Auto-detect provider if not explicitly specified
    if not provider:
        if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_MODEL"):
            provider = "ollama"
        elif os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_API_KEY") != "your_key_here":
            provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("CUSTOM_LLM_BASE_URL"):
            provider = "custom"
        else:
            return None

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        default_model = "llama3.2" if role == "worker" else "llama3.2"
        model_name = os.getenv(f"OLLAMA_{role.upper()}_MODEL") or os.getenv("OLLAMA_MODEL") or default_model

        # 1. Try langchain_ollama
        try:
            from langchain_ollama import ChatOllama
            logger.info("Initialized Local Ollama LLM (%s) for %s at %s", model_name, role, base_url)
            return ChatOllama(base_url=base_url, model=model_name, temperature=temperature)
        except ImportError:
            pass

        # 2. Try langchain_community.chat_models
        try:
            from langchain_community.chat_models import ChatOllama
            logger.info("Initialized Local Ollama LLM (%s) for %s via langchain_community at %s", model_name, role, base_url)
            return ChatOllama(base_url=base_url, model=model_name, temperature=temperature)
        except ImportError:
            pass

        # 3. Try OpenAI-compatible endpoint at /v1
        try:
            from langchain_openai import ChatOpenAI
            openai_url = f"{base_url}/v1"
            logger.info("Initialized Local Ollama LLM (%s) for %s via OpenAI-compatible endpoint %s", model_name, role, openai_url)
            return ChatOpenAI(base_url=openai_url, api_key="ollama", model=model_name, temperature=temperature)
        except ImportError:
            pass

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key or api_key == "your_key_here":
            return None
        default_model = "claude-3-haiku-20240307" if role == "worker" else "claude-3-5-sonnet-20241022"
        model_name = os.getenv(f"ANTHROPIC_{role.upper()}_MODEL") or os.getenv("ANTHROPIC_MODEL") or default_model
        try:
            from langchain_anthropic import ChatAnthropic
            logger.info("Initialized Anthropic Claude LLM (%s) for %s", model_name, role)
            return ChatAnthropic(model=model_name, anthropic_api_key=api_key, temperature=temperature)
        except Exception as e:
            logger.warning("Failed to initialize Anthropic LLM: %s", e)
            return None

    elif provider in ("openai", "custom"):
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_LLM_API_KEY") or "dummy-key"
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("CUSTOM_LLM_BASE_URL")
        default_model = "gpt-4o-mini" if role == "worker" else "gpt-4o"
        model_name = os.getenv(f"OPENAI_{role.upper()}_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("CUSTOM_LLM_MODEL") or default_model

        try:
            from langchain_openai import ChatOpenAI
            kwargs = {"model": model_name, "api_key": api_key, "temperature": temperature}
            if base_url:
                kwargs["base_url"] = base_url.rstrip("/")
            logger.info("Initialized OpenAI/Custom LLM (%s) for %s (Base URL: %s)", model_name, role, base_url or "default")
            return ChatOpenAI(**kwargs)
        except Exception as e:
            logger.warning("Failed to initialize OpenAI/Custom LLM: %s", e)
            return None

    return None
