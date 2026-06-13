"""配置读取、校验、默认生成."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from poorcode.provider.base import ProviderConfig

# 优先项目本地 config.yaml，回退到用户目录
LOCAL_CONFIG = Path.cwd() / "config.yaml"
USER_CONFIG = Path.home() / ".poorcode" / "config.yaml"

# ${VAR_NAME} 模式
_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")

DEFAULT_CONFIG = """\
# PoorCode 配置文件
# 修改以下字段后重新启动程序
# 敏感信息（如 api_key）建议用 ${ENV_VAR} 引用环境变量
protocol: anthropic       # 协议类型：anthropic 或 openai
model: your-model-name    # 模型名称
base_url: https://api.example.com  # API 地址
api_key: ${POORCODE_API_KEY}     # API 密钥（支持 ${ENV_VAR} 语法）
max_iterations: 25        # Agent Loop 最大迭代轮次
"""


@dataclass
class AppConfig:
    """应用级配置，包含 Provider 配置和 Agent 参数."""
    provider: ProviderConfig
    max_iterations: int = 25


def _resolve_env_vars(value: str) -> str:
    """将字符串中的 ${VAR_NAME} 替换为环境变量值.

    若环境变量未设置，保留原样并给出警告.
    """
    matches = _ENV_VAR_RE.findall(value)
    for var_name in matches:
        env_val = os.environ.get(var_name, "")
        if env_val:
            value = value.replace(f"${{{var_name}}}", env_val)
        else:
            print(f"⚠️  环境变量 {var_name} 未设置，请检查配置")
    return value


def _resolve_config_path() -> Path:
    """解析配置文件路径：当前目录优先，回退到用户目录."""
    if LOCAL_CONFIG.exists():
        return LOCAL_CONFIG
    if USER_CONFIG.exists():
        return USER_CONFIG
    return LOCAL_CONFIG  # 都不存在则在当前目录生成


def create_default_config(path: Path) -> None:
    """生成含占位值的默认配置文件."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")


def load_config(path: Path | None = None) -> AppConfig:
    """读取并校验配置文件，返回 AppConfig.

    查找顺序：指定路径 > 当前目录 config.yaml > ~/.poorcode/config.yaml。
    支持 ${ENV_VAR} 语法引用环境变量。
    配置文件不存在时在当前目录自动生成默认配置。
    """
    if path is None:
        path = _resolve_config_path()
    path = Path(path)

    if not path.exists():
        create_default_config(path)
        print(f"📝 已生成默认配置文件：{path}")
        print("   请编辑该文件，填入真实的 Provider 信息后重新启动。")
        raise SystemExit(0)

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ 配置文件格式错误：{e}")
        raise SystemExit(1) from e

    if data is None:
        print(f"❌ 配置文件为空：{path}")
        print("   请填入 provider 信息，格式参考默认配置。")
        raise SystemExit(1)

    required_fields = ["protocol", "model", "base_url", "api_key"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        print(f"❌ 配置文件缺少以下字段：{', '.join(missing)}")
        print(f"   文件位置：{path}")
        raise SystemExit(1)

    protocol = _resolve_env_vars(str(data["protocol"]).strip()).lower()
    if protocol not in ("anthropic", "openai"):
        print(f"❌ 不支持的协议类型：{protocol}，仅支持 anthropic 或 openai")
        raise SystemExit(1)

    provider_config = ProviderConfig(
        protocol=protocol,
        model=_resolve_env_vars(str(data["model"]).strip()),
        base_url=_resolve_env_vars(str(data["base_url"]).strip().rstrip("/")),
        api_key=_resolve_env_vars(str(data["api_key"]).strip()),
    )

    max_iterations = int(data.get("max_iterations", 25))

    return AppConfig(provider=provider_config, max_iterations=max_iterations)
