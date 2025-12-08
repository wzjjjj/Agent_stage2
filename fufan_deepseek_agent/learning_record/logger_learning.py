"""
Loguru 学习示例：
- 配置多个日志 sink（控制台、文件、错误文件、JSON）
- 绑定服务上下文，记录结构化事件
- 演示异常堆栈记录与常规日志
"""
from loguru import logger
import sys
from pathlib import Path

def setup_logging():
    """
    初始化日志系统：
    - 创建 `logs` 目录用于保存日志文件
    - 清除默认 sink，避免重复输出
    - 添加 4 个 sink：控制台、人类可读文件、错误文件、JSON 结构化文件
    - 使用异步写盘 `enqueue=True` 提高吞吐
    """
    # 确保日志目录存在
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 移除 loguru 默认的控制台输出，防止重复打印
    logger.remove()

    # 控制台输出：人类友好格式，显示时间、级别、服务名、位置、消息
    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:<8}</level> | svc={extra[service]} | evt={extra[event_type]} | {name}:{function}:{line} - <level>{message}</level>",
    )

    # 普通文件：轮转、保留、压缩，适合人工查看
    logger.add(
        "logs/app.log",
        rotation="500 MB",      # 文件超过 500MB 自动滚动
        retention="10 days",    # 保留 10 天历史
        compression="zip",      # 历史文件压缩为 zip
        level="INFO",
        encoding="utf-8",
        enqueue=True,           # 异步写盘，降低阻塞
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | svc={extra[service]} | evt={extra[event_type]} | {name}:{function}:{line} - {message}",
    )

    # 错误文件：单独记录 ERROR 及以上，便于快速排查
    logger.add(
        "logs/error.log",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        level="ERROR",
        encoding="utf-8",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | svc={extra[service]} | evt={extra[event_type]} | {process.id}:{name}:{function}:{line} - {message}",
    )

    # JSON 文件：机器可读的结构化日志   ，适合检索或接入日志系统
    logger.add(
        "logs/app.json",
        rotation="500 MB",
        retention="10 days",
        level="INFO",
        enqueue=True,
        serialize=True,         # 以 JSON 形式输出
    )

def get_logger(service: str):
    """
    返回绑定了 `service` 与默认 `event_type` 的 logger。
    默认为普通日志绑定 `event_type="-"`，避免在格式中引用 `evt={extra[event_type]}` 时出现 KeyError。
    """
    return logger.bind(service=service, event_type="-")

def log_structured(event_type: str, data: dict):
    """
    记录结构化事件日志：
    - `event_type` 作为额外上下文，标记事件类型
    - `data` 为事件主体（字典），在 JSON sink 中会完整呈现
    """
    # 绑定事件类型后输出，便于分类检索
    # 与控制台/文件格式中的 svc 引用保持一致，绑定一个默认的 service，避免 KeyError
    logger.bind(service="demo", event_type=event_type).info(data)

def main():
    """
    演示日志输出的完整流程：
    - 初始化日志系统
    - 常规信息日志与结构化事件日志
    - 异常捕获并记录堆栈
    - 结束告警
    """
    # 初始化日志
    setup_logging()

    # 获取带服务名的记录器
    log = get_logger("demo")

    # 常规信息日志
    log.info("demo start")

    # 结构化事件日志示例
    log_structured("user_signup", {"user_id": 123, "plan": "pro"})

    # 异常演示：使用 logger.exception 自动包含堆栈
    try:
        raise ValueError("invalid value")
    except Exception:
        log.exception("exception occurred")

    # 结束告警
    log.warning("demo end")

if __name__ == "__main__":
    main()