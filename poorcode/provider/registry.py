"""Provider 注册表：protocol 到 Provider 类的映射与工厂方法."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poorcode.provider.base import LLMProvider, ProviderConfig

_registry: dict[str, type["LLMProvider"]] = {}


def register_provider(protocol: str, provider_cls: type["LLMProvider"]) -> None:
    """注册一个 Provider 实现.

    Args:
        protocol: 协议名（如 "anthropic", "openai"）.
        provider_cls: LLMProvider 子类.
    """
    _registry[protocol.lower()] = provider_cls


def create_provider(config: "ProviderConfig") -> "LLMProvider":
    """根据配置创建对应的 Provider 实例.

    Args:
        config: ProviderConfig 配置对象.

    Returns:
        LLMProvider 实例.

    Raises:
        ValueError: 配置的 protocol 没有对应的注册实现.
    """
    protocol = config.protocol.lower()
    provider_cls = _registry.get(protocol)
    if provider_cls is None:
        supported = ", ".join(sorted(_registry.keys())) or "(无)"
        raise ValueError(
            f"不支持的协议类型：{protocol}，"
            f"当前支持：{supported}。"
            f"请检查配置文件中的 protocol 字段。"
        )
    return provider_cls(config)
