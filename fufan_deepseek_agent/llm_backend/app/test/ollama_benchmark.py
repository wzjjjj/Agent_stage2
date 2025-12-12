import aiohttp
import asyncio
import time
from pathlib import Path
from loguru import logger
import random
from tqdm import tqdm
import json
from datetime import datetime
import psutil
import GPUtil

# 配置日志
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logger.add(
    "logs/benchmark.log",
    rotation="100 MB",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}"
)

"""
关键指标:
1. 吞吐量 (Throughput)：
吞吐量是指单位时间内系统能够处理的请求数量或数据量。通常以请求/秒 (requests per second) 或 tokens/秒 (tokens per second) 来衡量。
吞吐量反映了系统的处理能力，越高的吞吐量意味着系统在给定时间内能够处理更多的请求。

对于大模型服务来说，每秒生成的 Token 数量就可以被视为系统的吞吐量。


2. 并发 (Concurrency)
并发是指系统在同一时间内能够处理的请求数量。它表示系统的并行处理能力。
高并发意味着系统可以同时处理多个请求，这通常会提高吞吐量，但是会降低单个请求的生成时间。


1. 尽可能保证生成的token数量保持一致，通过num_predict参数来控制
2. 



1. 并发会导致单个请求的处理时间变长
2. 因为是并行处理，虽然单个请求时间变成，但是系统整体吞吐量会得到提升
"""

# 测试问题列表
questions = [
    # 科学解释类问题
    "为什么天空是蓝色的？", 
    "为什么我们会做梦？",
    "为什么海水是咸的？",
    "为什么树叶会变色？",
    "为什么鸟儿会唱歌？",
    
    # 编程相关问题
    "解释什么是Python中的装饰器？",
    "什么是面向对象编程？",
    "如何处理Python中的异常？",
    "解释什么是递归函数？",
    "什么是设计模式？",
    
    # 数学问题
    "解释什么是傅里叶变换？",
    "什么是微积分？",
    "解释什么是线性代数？",
    "什么是概率论？",
    "解释什么是统计学？",
    
    # AI/ML问题
    "什么是神经网络？",
    "解释什么是深度学习？",
    "什么是机器学习？",
    "解释什么是强化学习？",
    "什么是自然语言处理？",
    
    # 哲学问题
    "什么是意识？",
    "为什么我们存在？",
    "什么是自由意志？",
    "解释什么是道德？",
    "什么是知识？"
]

class OllamaBenchmark:  # 压测类，封装与 Ollama 交互及统计
    def __init__(self, url: str, model: str):  # 初始化方法，保存服务地址与模型名
        self.url = url  # Ollama 服务地址
        self.model = model  # 待压测的模型名称
        
    async def single_request(self, session: aiohttp.ClientSession) -> dict:  # 发送单个请求并计算性能指标的方法定义
        """发送单个请求并计算性能指标"""  # 方法说明
        try:  # 捕获异常，保证测试过程不因单次失败中断
            # 随机选择一个问题
            prompt = random.choice(questions)  # 从问题列表中随机选择提示词
            
            # 调用 ollama 的 generate 接口
            async with session.post(  # 以 POST 方式调用生成接口
                f"{self.url}/api/generate",  # 目标接口地址
                json={  # 请求体为 JSON
                    "model": self.model,  # 指定模型名称
                    "prompt": prompt,  # 指定生成的输入文本
                    "stream": False,  # 关闭流式输出，便于一次性统计
                    "keep_alive": "5m",  # 保持模型加载5分钟
                    "options": {  # 推理选项
                        "temperature": 0.7,  # 采样温度
                        "num_predict": 300,  # 限制生成token数量
                    }  # 结束 options
                }  # 结束 json
            ) as response:  # 获取 HTTP 响应对象
                result = await response.json()  # 解析响应为 JSON
                # 从响应中获取性能指标
                eval_count = result.get("eval_count", 0)  # 生成的token数
                eval_duration = result.get("eval_duration", 0)  # 生成时间(纳秒)
                total_duration = result.get("total_duration", 0)  # 总时间(纳秒)
                
                # 计算 tokens/second
                tokens_per_second = (eval_count / eval_duration * 1e9) if eval_duration > 0 else 0  # 安全计算每秒生成数
                
                return {  # 返回成功结果
                    "success": True,  # 成功标记
                    "eval_count": eval_count,  # 生成的token数量
                    "eval_duration_seconds": eval_duration / 1e9,  # 生成耗时（秒）
                    "total_duration_seconds": total_duration / 1e9,  # 总耗时（秒）
                    "tokens_per_second": tokens_per_second  # 每秒生成的token数
                }  # 结束返回字典
        except Exception as e:  # 捕获并记录异常
            return {  # 返回失败结果
                "success": False,  # 失败标记
                "error": str(e)  # 错误信息
            }  # 结束失败字典

    async def test_single_request(self, num_tests: int = 5):  # 批量运行单请求测试并统计
        """测试单个请求的性能"""  # 方法说明
        logger.info("开始测试单个请求性能...")  # 记录开始日志
        
        async with aiohttp.ClientSession() as session:  # 创建会话复用连接
            results = []  # 存放每次测试的结果
            for i in range(num_tests):  # 循环执行指定次数
                logger.info(f"执行测试 {i+1}/{num_tests}")  # 标记当前轮次
                result = await self.single_request(session)  # 发起单次测试
                if result["success"]:  # 仅统计成功结果
                    results.append(result)  # 保存成功结果
                    msg_parts = [  # 组装日志消息的各段
                        f"测试 {i+1} 结果:\n",  # 标题行，显示当前轮次
                        f"- 生成的token数: {result['eval_count']}\n",  # 输出生成的 token 数
                        f"- 生成时间: {result['eval_duration_seconds']:.2f}秒\n",  # 输出生成耗时（秒）
                        f"- 总时间: {result['total_duration_seconds']:.2f}秒\n",  # 输出总耗时（秒）
                        f"- 每秒生成token数: {result['tokens_per_second']:.2f}"  # 输出每秒生成的 token 数
                    ]  # 结束列表
                    logger.info("".join(msg_parts))  # 拼接并输出日志
                await asyncio.sleep(2)  # 冷却时间，短时间频繁请求可能导致过载
            
            if results:  # 仅在有成功结果时计算平均值
                avg_tokens = sum(r["eval_count"] for r in results) / len(results)  # 平均生成 token 数
                avg_gen_time = sum(r["eval_duration_seconds"] for r in results) / len(results)  # 平均生成时间
                avg_total_time = sum(r["total_duration_seconds"] for r in results) / len(results)  # 平均总时间
                avg_tps = sum(r["tokens_per_second"] for r in results) / len(results)  # 平均 tokens/s
                
                logger.info(f"\n{len(results)}次成功测试的平均性能:")  # 输出汇总标题
                logger.info(f"- 平均token数: {avg_tokens:.2f}")  # 输出平均 token
                logger.info(f"- 平均生成时间: {avg_gen_time:.2f}秒")  # 输出平均生成时间
                logger.info(f"- 平均总时间: {avg_total_time:.2f}秒")  # 输出平均总时间
                logger.info(f"- 平均每秒token数: {avg_tps:.2f}")  # 输出平均 tokens/s
                
                return {  # 返回平均统计
                    "avg_tokens": avg_tokens,  # 平均 token 数
                    "avg_generation_time": avg_gen_time,  # 平均生成时间（秒）
                    "avg_total_time": avg_total_time,  # 平均总耗时（秒）
                    "avg_tokens_per_second": avg_tps,  # 平均 tokens/s
                    "individual_results": results  # 单次结果列表
                }  # 结束返回

    async def test_concurrent_requests(self, concurrent_requests: int, total_requests: int):  # 并发测试入口
        """使用信号量测试并发性能"""  # 方法说明
        logger.info(f"开始测试 {concurrent_requests} 并发请求，共 {total_requests} 个请求...")  # 标记并发规模
        
        # 控制并发的工具。它的作用是限制同时执行的协程数量，以防止系统过载。
        sem = asyncio.Semaphore(concurrent_requests)  # 根据并发数初始化信号量
        
        async def bounded_request(session):  # 包装单次请求以受信号量保护
            async with sem:  # 进入信号量，限制并发
                result = await self.single_request(session)  # 执行单次请求
                # 每个请求后等待一小段时间
                await asyncio.sleep(0.5)  # 500ms 间隔
                return result  # 返回单次结果
        
        async with aiohttp.ClientSession() as session:  # 创建会话
            start_time = time.time()  # 记录开始时间
            
            # 创建所有任务
            tasks = []  # 存放任务引用
            # 使用tqdm显示进度条
            with tqdm(total=total_requests, desc="处理请求") as pbar:  # 初始化进度条
                # 创建任务
                for _ in range(total_requests):  # 生成指定数量的任务
                    # 异步创建任务
                    task = asyncio.create_task(bounded_request(session))  # 创建并发请求任务
                    # 任务完成后更新进度条
                    task.add_done_callback(lambda _: pbar.update(1))  # 回调更新进度
                    tasks.append(task)  # 收集任务
                
                # 等待所有任务完成
                responses = await asyncio.gather(*tasks)  # 并发执行并收集结果
            
            end_time = time.time()  # 记录结束时间
            
            # 计算统计信息
            successful = [r for r in responses if r["success"]]  # 过滤成功结果
            if successful:  # 若有成功结果则统计
                total_tokens = sum(r["eval_count"] for r in successful)  # 成功请求生成的总 token
                avg_gen_time = sum(r["eval_duration_seconds"] for r in successful) / len(successful)  # 平均生成时间
                avg_total_time = sum(r["total_duration_seconds"] for r in successful) / len(successful)  # 平均总耗时
                avg_tps = sum(r["tokens_per_second"] for r in successful) / len(successful)  # 平均 tokens/s
                actual_time = end_time - start_time  # 实际总耗时（秒）
                
                results = {  # 汇总并发测试结果
                    "concurrent_requests": concurrent_requests,  # 并发请求数
                    "total_requests": total_requests,  # 总请求数
                    "success_rate": len(successful) / total_requests,  # 成功率
                    "total_tokens": total_tokens,  # 总生成 token 数
                    "average_generation_time": avg_gen_time,  # 平均生成时间（秒）
                    "average_total_time": avg_total_time,  # 平均总耗时（秒）
                    "average_tokens_per_second": avg_tps,  # 平均 tokens/s
                    "actual_total_time": actual_time,  # 实际总耗时（秒）
                    "system_throughput": total_tokens / actual_time  # 系统吞吐量（tokens/s）
                }  # 结束结果字典
                
                logger.info("\n并发测试结果:")  # 打印并发测试标题
                logger.info(f"- 成功率: {len(successful)}/{total_requests}")  # 输出成功率
                logger.info(f"- 总token数: {total_tokens}")  # 输出总 token
                logger.info(f"- 平均生成时间: {avg_gen_time:.2f}秒")  # 输出平均生成时间
                logger.info(f"- 平均总时间: {avg_total_time:.2f}秒")  # 输出平均总耗时
                logger.info(f"- 平均每秒token数: {avg_tps:.2f}")  # 输出平均 tokens/s
                logger.info(f"- 实际总耗时: {actual_time:.2f}秒")  # 输出实际耗时
                logger.info(f"- 系统整体吞吐量: {results['system_throughput']:.2f} tokens/s")  # 输出系统吞吐量
                
                return results  # 返回并发测试结果
            return None  # 若无成功结果，返回空

    async def check_system_health(self) -> tuple[bool, dict]:  # 系统健康检查，返回(是否健康, 指标)
        """检查系统健康状态"""  # 方法说明
        try:  # 外层异常捕获
            # CPU 使用率
            cpu_percent = psutil.cpu_percent(interval=1)  # 采样 1 秒得到 CPU 使用率
            
            # 内存使用率
            memory = psutil.virtual_memory()  # 获取内存信息
            memory_percent = memory.percent  # 内存使用百分比
            
            metrics = {  # 指标字典
                "cpu_percent": cpu_percent,  # CPU 使用率
                "memory_percent": memory_percent,  # 内存使用率
                "gpu_info": []  # GPU 信息列表
            }  # 结束指标字典
            
            # 检查 CPU 和内存
            is_healthy = (  # 以阈值判定是否健康
                cpu_percent < 90 and    # CPU 低于 90%
                memory_percent < 90      # 内存低于 90%
            )  # 结束健康判定表达式
            
            # 只在资源接近阈值时打印警告
            if cpu_percent > 85:  # CPU 高于 85% 给出警告
                logger.warning(f"CPU 使用率较高: {cpu_percent:.1f}%")  # 输出 CPU 警告
            if memory_percent > 85:  # 内存高于 85% 给出警告
                logger.warning(f"内存使用率较高: {memory_percent:.1f}%")  # 输出内存警告
            
            # GPU 检查
            try:  # GPU 信息采集尝试
                import subprocess  # 引入标准库 subprocess
                result = subprocess.run(  # 执行 nvidia-smi 查询
                    ['nvidia-smi', '--query-gpu=index,memory.used,memory.total,memory.free', '--format=csv,noheader,nounits'],  # 查询参数
                    capture_output=True,  # 捕获输出
                    text=True  # 文本模式
                )  # 结束运行
                
                if result.returncode == 0:  # 命令执行成功
                    for line in result.stdout.strip().split('\n'):  # 逐行解析输出
                        index, used, total, free = map(float, line.split(','))  # 提取并转为数值
                        memory_percent = (used / total) * 100  # 计算显存使用率
                        
                        metrics["gpu_info"].append({  # 追加 GPU 指标
                            "id": int(index),  # GPU 编号
                            "memory_used": used,  # 已用显存（MB）
                            "memory_total": total,  # 显存总量（MB）
                            "memory_free": free,  # 剩余显存（MB）
                            "memory_percent": memory_percent  # 显存使用率（%）
                        })  # 结束追加
                        
                        # 只在 GPU 显存使用率高时打印警告
                        if memory_percent > 85:  # 显存使用率超过 85%
                            logger.warning(f"GPU {int(index)} 显存使用率较高: {memory_percent:.1f}%")  # 输出警告
                        
                        if memory_percent > 90:  # 显存使用率超过 90%
                            is_healthy = False  # 标记系统不健康
                            
            except Exception as e:  # 捕获 GPU 信息采集异常
                logger.error(f"获取GPU信息时出错: {e}")  # 记录错误
            
            return is_healthy, metrics  # 返回健康状态与指标
            
        except Exception as e:  # 捕获外层异常
            logger.error(f"检查系统状态时出错: {e}")  # 记录错误
            return False, {}  # 发生异常视为不健康

    async def find_max_concurrency(self, start_concurrent: int = 1, max_concurrent: int = 20,  # 并发探索的参数设定
                                 requests_per_test: int = 5, success_rate_threshold: float = 0.8,  # 每轮请求数与成功率阈值
                                 latency_threshold: float = 10.0):  # 延迟阈值（秒）
        """通过逐步增加并发数来寻找系统极限"""  # 方法说明
        logger.info("\n=== 开始寻找最大并发数 ===")  # 打印阶段标题
        
        results = []  # 保存每轮并发测试结果
        optimal_concurrent = 0  # 当前满足条件的最优并发数
        max_throughput = 0  # 当前记录的最大吞吐量
        consecutive_failures = 0  # 连续失败计数
        
        for concurrent in range(start_concurrent, max_concurrent + 1):  # 逐步增大并发
            # 每轮测试前检查系统状态
            is_healthy, metrics = await self.check_system_health()  # 采集健康指标
            if not is_healthy:  # 若系统不健康则停止
                logger.warning("\n系统负载过高，立即停止测试")  # 输出警告
                # 等待系统恢复
                await asyncio.sleep(30)  # 等待更久时间以恢复
                break  # 退出循环
                
            # 如果 CPU 或内存使用率超过 90%，立即停止
            if metrics["cpu_percent"] > 90 or metrics["memory_percent"] > 90:  # 资源接近极限
                logger.warning("\n系统资源接近极限，紧急停止")  # 输出警告
                break  # 退出循环
            
            logger.info(f"\n测试并发数: {concurrent}")  # 标记当前并发值
            
            # 运行并发测试
            result = await self.test_concurrent_requests(concurrent, requests_per_test)  # 发起并发测试
            
            if not result:  # 若本轮无有效结果
                consecutive_failures += 1  # 连续失败次数+1
                if consecutive_failures >= 2:  # 连续失败2次就停止
                    logger.warning("连续测试失败，停止测试")  # 输出警告
                    break  # 退出循环
                continue  # 继续下一轮
            else:  # 有有效结果
                consecutive_failures = 0  # 重置失败计数  # 重置失败计数
            
            results.append(result)  # 记录本轮结果
            
            # 检查是否达到系统极限
            success_rate = result["success_rate"]  # 当前成功率
            avg_latency = result["average_generation_time"]  # 当前平均生成时延
            throughput = result["system_throughput"]  # 当前系统吞吐量
            
            logger.info(f"成功率: {success_rate:.2%}")  # 打印成功率
            logger.info(f"平均延迟: {avg_latency:.2f}秒")  # 打印平均延迟
            logger.info(f"系统吞吐量: {throughput:.2f} tokens/s")  # 打印吞吐量
            
            # 更新最优并发数
            if (success_rate >= success_rate_threshold and  # 成功率达标
                avg_latency <= latency_threshold and  # 延迟达标
                throughput > max_throughput):  # 吞吐量更高
                optimal_concurrent = concurrent  # 更新最优并发
                max_throughput = throughput  # 更新最大吞吐量
            
            # 检查是否应该停止测试
            if (success_rate < success_rate_threshold or  # 成功率低于阈值
                avg_latency > latency_threshold):  # 延迟超过阈值
                logger.info(f"\n检测到系统瓶颈:")  # 输出瓶颈提示
                logger.info(f"- 成功率低于 {success_rate_threshold:.0%}" if success_rate < success_rate_threshold else "")  # 说明成功率不足
                logger.info(f"- 延迟超过 {latency_threshold}秒" if avg_latency > latency_threshold else "")  # 说明延迟过高
                break  # 退出循环
            
            # 每次测试后检查系统状态并等待恢复
            is_healthy, _ = await self.check_system_health()  # 再次检查健康状态
            if not is_healthy:  # 若仍不健康
                logger.warning("系统需要更多恢复时间")  # 输出警告
                await asyncio.sleep(30)  # 系统压力大时多等待
            else:
                await asyncio.sleep(5)   # 正常等待
        
        logger.info("\n=== 并发测试结果总结 ===")  # 输出总结标题
        logger.info(f"最优并发数: {optimal_concurrent}")  # 输出最优并发
        logger.info(f"最大吞吐量: {max_throughput:.2f} tokens/s")  # 输出最大吞吐量
        
        return {  # 返回探索结果
            "optimal_concurrent": optimal_concurrent,  # 最优并发数
            "max_throughput": max_throughput,  # 最大吞吐量
            "all_results": results  # 每轮详细结果
        }  # 结束返回

    async def check_model_exists(self, session: aiohttp.ClientSession) -> bool:  # 检查模型是否存在
        """检查模型是否已经存在"""  # 方法说明
        try:  # 捕获异常
            # 修改为 GET 请求
            async with session.get(f"{self.url}/api/tags") as response:  # 拉取模型列表
                if response.status != 200:  # 非 200 视为失败
                    logger.error(f"获取模型列表失败: {response.status}")  # 记录错误状态码
                    return False  # 返回不存在
                    
                data = await response.json()  # 解析响应为 JSON
                models = data.get("models", [])  # 获取模型数组
                logger.info(f"已安装的模型: {[m['name'] for m in models]}")  # 打印已安装模型
                return any(m["name"] == self.model for m in models)  # 判断目标模型是否存在
        except Exception as e:  # 捕获异常
            logger.error(f"检查模型时出错: {e}")  # 记录错误
            return False  # 返回失败

    async def pull_model(self, session: aiohttp.ClientSession) -> bool:  # 拉取模型
        """拉取模型"""  # 方法说明
        try:  # 捕获异常
            logger.info(f"开始拉取模型: {self.model}")  # 打印模型名
            
            async with session.post(  # 向 /api/pull 发起请求
                f"{self.url}/api/pull",  # 拉取接口地址
                json={  # 请求体
                    "name": self.model,  # 模型名称
                    "stream": False  # 是否流式（当前为 False）
                }
            ) as response:  # 响应对象
                if response.status != 200:  # 拉取失败
                    logger.error(f"拉取模型失败: {response.status}")  # 输出错误码
                    return False  # 返回失败
                
                # 读取流式响应
                async for line in response.content:  # 逐行读取响应内容
                    if not line:  # 空行跳过
                        continue  # 继续下一行
                    try:  # 尝试解析 JSON
                        data = json.loads(line)  # 解析一行 JSON
                        status = data.get("status", "")  # 获取状态字段
                        
                        if "downloading" in status:  # 下载中状态
                            # 显示下载进度
                            total = data.get("total", 0)  # 总字节数
                            completed = data.get("completed", 0)  # 已完成字节数
                            if total > 0:  # 有总量才计算进度
                                progress = (completed / total) * 100  # 计算进度百分比
                                logger.info(f"下载进度: {progress:.1f}% ({completed}/{total} bytes)")  # 打印进度
                        else:  # 非下载阶段
                            logger.info(f"模型拉取状态: {status}")  # 打印状态
                            
                        if status == "success":  # 拉取成功
                            logger.info(f"模型 {self.model} 拉取成功")  # 打印成功
                            return True  # 返回成功
                            
                    except json.JSONDecodeError:  # 非 JSON 内容忽略
                        continue  # 继续读取
                        
                return False  # 响应未包含成功事件视为失败
                
        except Exception as e:  # 捕获异常
            logger.error(f"拉取模型时出错: {e}")  # 记录错误
            return False  # 返回失败

    async def ensure_model_available(self) -> bool:  # 确保模型可用（存在或成功拉取）
        """确保模型可用"""  # 方法说明
        async with aiohttp.ClientSession() as session:  # 创建会话
            # 检查模型是否存在
            if await self.check_model_exists(session):  # 已存在则直接返回
                logger.info(f"模型 {self.model} 已存在")  # 输出提示
                return True  # 返回可用
                
            # 拉取模型
            logger.info(f"模型 {self.model} 不存在，开始拉取")  # 输出提示
            return await self.pull_model(session)  # 拉取并返回结果

    async def unload_model(self, session: aiohttp.ClientSession) -> bool:  # 卸载模型
        """通过设置 keep_alive=0 来卸载模型"""  # 方法说明
        try:  # 捕获异常
            logger.info(f"准备卸载模型: {self.model}")  # 提示卸载
            
            # 发送一个 keep_alive=0 的请求来卸载模型
            async with session.post(  # 使用 generate 接口触发卸载
                f"{self.url}/api/generate",  # 接口地址
                json={  # 请求体
                    "model": self.model,  # 模型名称
                    "prompt": "",  # 可以直接发送空字符串
                    "stream": False,  # 非流式
                    "keep_alive": 0,  # 使用完立即卸载
                }
            ) as response:  # 响应对象
                if response.status == 200:  # 状态 200 视为成功
                    logger.info(f"模型 {self.model} 已卸载")  # 打印卸载成功
                    return True  # 返回成功
                else:  # 非 200 视为失败
                    logger.error(f"卸载模型失败: {response.status}")  # 记录错误
                    return False  # 返回失败
                    
        except Exception as e:  # 捕获异常
            logger.error(f"卸载模型时出错: {e}")  # 记录错误
            return False  # 返回失败

async def main():
    benchmark = OllamaBenchmark(
        url="http://localhost:11434",  # 这里替换成实际的ollama endpoint
        model="deepseek-r1:1.5b"             # 这里替换成实际要进行测试的模型名称
    )
    
    try:
        # 确保模型可用
        if not await benchmark.ensure_model_available():
            logger.error("模型准备失败，退出测试")
            return
            
        # 先检查系统状态
        is_healthy, metrics = await benchmark.check_system_health()
        if not is_healthy:
            logger.error("系统资源不足，无法开始测试")
            return
        # 输出本次健康检查的主要指标
        cpu = metrics.get("cpu_percent", None)
        mem = metrics.get("memory_percent", None)
        gpu_infos = metrics.get("gpu_info", [])
        gpu_summary = ", ".join(
            [
                f"GPU{id}: {info.get('memory_percent', 0):.1f}% 显存占用"
                for info in gpu_infos
                for id in [info.get('id', '?')]
            ]
        ) if gpu_infos else "无 GPU 信息"
        logger.info(
            f"系统健康指标 | CPU: {cpu:.1f}% | 内存: {mem:.1f}% | {gpu_summary}"
        )
        
        # 1. 测试单个请求的基准性能
        logger.info("\n=== 开始单请求性能测试 ===")
        single_results = await benchmark.test_single_request(num_tests=3)
        
        # 使用保守的并发测试参数
        concurrency_results = await benchmark.find_max_concurrency(
            start_concurrent=2,          # 从2开始
            max_concurrent=5,            # 最多只测到5个并发
            requests_per_test=10,         # 每轮只测10个请求
            success_rate_threshold=0.95,  # 成功率要求提高到95%
            latency_threshold=5.0        # 延迟阈值降低到5秒
        )
        
        
        # 保存结果
        results = {
            "test_info": {
                "timestamp": datetime.now().isoformat(),
                "model": benchmark.model,
                "server": benchmark.url
            },
            "single_request_performance": single_results,
            "concurrency_test": concurrency_results
        }
        
        filename = f"logs/benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n测试结果已保存到: {filename}")

    finally:

        
        # 测试完成后卸载模型
        async with aiohttp.ClientSession() as session:
            await benchmark.unload_model(session)

        # 测试完成后删除
        # async with aiohttp.ClientSession() as session:
        #     try:
        #         await session.delete(f"{benchmark.url}/api/delete", 
        #                            json={"name": benchmark.model})
        #         logger.info(f"已卸载模型: {benchmark.model}")
        #     except Exception as e:
        #         logger.error(f"卸载模型时出错: {e}"

if __name__ == "__main__":
    asyncio.run(main()) 
