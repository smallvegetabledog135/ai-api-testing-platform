# -*- coding: utf-8 -*-  
"""  
AI服务配置
"""
import os
from dataclasses import dataclass
from app import global_logger

@dataclass
class AIConfig:
    """AI配置类"""
    api_key: str
    base_url: str
    model: str
    timeout: int
    max_tokens: int
    temperature: float

# 从环境变量或配置文件加载
def _load_ai_config() -> AIConfig:
    """加载AI配置"""
    try:
        return AIConfig(
            # 硅基流动API配置 - DeepSeek-V3
            api_key=os.getenv('SILICONFLOW_API_KEY', 'your-siliconflow-api-key-here'),
            base_url=os.getenv('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1'),
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B'),
            timeout=int(os.getenv('AI_TIMEOUT', '60')),
            max_tokens=int(os.getenv('AI_MAX_TOKENS', '8000')),
            temperature=float(os.getenv('AI_TEMPERATURE', '0.3'))
        )
    except Exception as e:
        global_logger.error(f"加载AI配置失败: {e}")
        # 返回默认配置，避免程序崩溃
        return AIConfig(
            api_key=os.getenv('SILICONFLOW_API_KEY', 'your-siliconflow-api-key-here'),
            base_url='https://api.siliconflow.cn/v1',
            model='deepseek-ai/DeepSeek-R1-Distill-Qwen-7B',
            timeout=60,
            max_tokens=8000,
            temperature=0.3
        )

# 验证配置
def _validate_config(config: AIConfig) -> bool:
    """验证配置有效性"""
    if not config.api_key or config.api_key == 'your-siliconflow-api-key-here':
        global_logger.error("硅基流动 API Key未配置")
        return False

    if not config.base_url:
        global_logger.error("AI Base URL未配置")
        return False

    if not config.model:
        global_logger.error("AI模型未配置")
        return False

    # 验证API Key格式
    if not config.api_key.startswith('sk-'):
        global_logger.warning("API Key格式可能不正确")

    return True

# 全局配置实例
try:
    AI_CONFIG = _load_ai_config()
    _config_valid = _validate_config(AI_CONFIG)

    if _config_valid:
        global_logger.info(f"硅基流动AI配置加载成功，模型: {AI_CONFIG.model}")
        if AI_CONFIG.api_key != 'your-siliconflow-api-key-here':
            global_logger.info(f"API Key: {AI_CONFIG.api_key[:8]}...{AI_CONFIG.api_key[-4:]}")
    else:
        global_logger.warning("AI配置验证失败，请检查环境变量配置")
except Exception as e:
    global_logger.error(f"AI配置初始化失败: {e}")
    # 创建默认配置
    AI_CONFIG = AIConfig(
        api_key=os.getenv('SILICONFLOW_API_KEY', 'your-siliconflow-api-key-here'),
        base_url='https://api.siliconflow.cn/v1',
        model='deepseek-ai/DeepSeek-R1-Distill-Qwen-7B',
        timeout=60,
        max_tokens=8000,
        temperature=0.3
    )
    _config_valid = False

# 导出配置验证状态  
CONFIG_VALID = _config_valid