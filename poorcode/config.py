"""配置读取、校验、默认生成."""

from pathlib import Path

import yaml

from poorcode.provider.base import ProviderConfig

# 优先项目本地 config.yaml，回退到用户目录
LOCAL_CONFIG = Path.cwd() / "config.yaml"
USER_CONFIG = Path.home() / ".poorcode" / "config.yaml"

DEFAULT_CONFIG = """\
# PoorCode 配置文件
# 修改以下字段后重新启动程序
protocol: anthropic       # 协议类型：anthropic 或 openai
model: your-model-name    # 模型名称
base_url: https://api.example.com  # API 地址
api_key: your-api-key     # API 密钥
"""


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


def load_config(path: Path | None = None) -> ProviderConfig:
    """读取并校验配置文件，返回 ProviderConfig.

    查找顺序：指定路径 > 当前目录 config.yaml > ~/.poorcode/config.yaml。
    配置文件不存在时在当前目录自动生成默认配置。
    字段缺失或为空时给出明确的中文错误提示。
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

    protocol = str(data["protocol"]).strip().lower()
    if protocol not in ("anthropic", "openai"):
        print(f"❌ 不支持的协议类型：{protocol}，仅支持 anthropic 或 openai")
        raise SystemExit(1)

    return ProviderConfig(
        protocol=protocol,
        model=str(data["model"]).strip(),
        base_url=str(data["base_url"]).strip().rstrip("/"),
        api_key=str(data["api_key"]).strip(),
    )
