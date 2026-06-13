"""Provider 抽象层——启动时自动注册所有实现."""

from poorcode.provider.anthropic import AnthropicProvider
from poorcode.provider.base import LLMProvider, Message, ProviderConfig, StreamEvent
from poorcode.provider.openai import OpenAIProvider
from poorcode.provider.registry import create_provider, register_provider

# 启动时注册所有 Provider 实现
register_provider("anthropic", AnthropicProvider)
register_provider("openai", OpenAIProvider)

__all__ = [
    "LLMProvider",
    "Message",
    "ProviderConfig",
    "StreamEvent",
    "create_provider",
    "register_provider",
]
