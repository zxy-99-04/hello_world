import sys
import os
# 获取当前脚本所在的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
root_dir = os.path.dirname(current_dir)
# 将项目根目录添加到系统路径
sys.path.append(root_dir)
import httpx
import asyncio
import aio_pika
import json
from app.config.settings import token_limit_default, chat_count_limit_default
import logging
from app.models.models import Task, TaskStatus, File as FileModel, TokenUsage
from app.models.database import async_get_db
from sqlalchemy import update, select
from datetime import date
from app.services.history_messages import chat_flow

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


async def chat_token(username: str, chat_url:str, chat_count = 10):
    today = date.today()
    async with async_get_db() as db:
        result = await db.execute(select(TokenUsage).where(TokenUsage.user_id == username))
        usage = result.scalars().first()
        if usage is None:
            new_record = TokenUsage(
                user_id=username
            )
            db.add(new_record)
            await db.commit()
            return True
        elif usage.expiration_date < today:
            usage.expiration_date = today
            usage.task_input_tokens = 0
            usage.task_output_tokens = 0
            usage.chat_count = 0
            usage.chat_count_limit = chat_count_limit_default
            usage.token_limit = token_limit_default
            await db.commit()
            return True
        elif usage.chat_count < usage.chat_count_limit:
            return True
        else:
            async with httpx.AsyncClient() as client:
                content = {
                    "answer": "今日聊天次数已达上限，欢迎明日继续使用 ！"
                }
                content1 = {
                    "end": True
                }
                try:
                    await client.post(chat_url, json=content)
                    response = await client.post(chat_url, json=content1)
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP状态错误，请求 {chat_url} 时，内容: {content}, 错误: {e}")
                except httpx.RequestError as e:
                    logger.error(f"请求错误，请求 {chat_url} 时，内容: {content}, 错误: {e}")
                return False





async def process_file_content(
        task_id,
        session_task_id,
        user_id: str,
        file_path: str,
        task_type: str,
        username: str,
):
    async with async_get_db() as db:
        try:
            file_result = await db.execute(
                select(FileModel).where(FileModel.session_task_id == session_task_id)
            )
            file1 = file_result.scalar_one_or_none()
            can_chat = await chat_token(username, file1.callback_chat_url)
            if can_chat:
                final_result = await chat_flow(
                    session_task_id,
                    file_path,
                    file1.callback_chat_url,
                    user_id
                )
                status = TaskStatus.FAILED if final_result is None else TaskStatus.COMPLETED
                result = '失败' if final_result is None else '成功'
                await update_task_status(db, Task, task_id, status, result=result)
                # 修改TokenUsage表
                await db.execute(
                    update(TokenUsage)
                    .where(TokenUsage.user_id == username)
                    .values(chat_count=TokenUsage.chat_count + 1)
                )
                await db.commit()

        except Exception as e:
            logger.error(f'聊天异常: {str(e)}')
            await update_task_status(db, Task, task_id, TaskStatus.FAILED, result=json.dumps({"error": str(e)}))
            await db.commit()


async def update_task_status(db, model, id, status, result=None):
    """更新任务状态的辅助函数"""
    values = {
        'status': status
        }
    if model == Task and result is not None:
        values['result'] = result

    update_stmt = (
        update(model)
        .where(model.id == id if model == Task else model.session_task_id == id)
        .values(values))
    await db.execute(update_stmt)

async def message_handler(message: aio_pika.IncomingMessage):
    """单条消息处理逻辑"""
    async with message.process(requeue=False):  # 失败时自动重新入队
        async with async_get_db() as db:
            try:
                payload = json.loads(message.body.decode())
                task_id = payload["task_id"]
                user_id = payload["user_id"]
                file_path = payload["file_path"]

                # 异步获取任务（推荐使用 get 方法）
                task = await db.get(Task, task_id)
                file_result = await db.execute(select(FileModel).where(FileModel.session_task_id == task.session_task_id))
                file = file_result.scalar_one_or_none()
                if not task or not file:
                    logger.warning(f"任务 {task_id}或文件数据不存在")
                    return
                # 更新任务状态为处理中
                task.status = TaskStatus.PROCESSING
                await db.commit()
                await process_file_content(task.id, task.session_task_id, user_id, file_path, task.task_type, task.user_id)
            except Exception as e:
                logger.error(f"消息处理异常: {str(e)}")
                try:
                    if task:  # 确保task存在
                        # 统一处理任务失败
                        await update_task_status(db, Task, task_id, TaskStatus.FAILED, result=json.dumps({"error": str(e)}))
                        await db.commit()
                except Exception as db_e:
                    logger.error(f"数据库回滚失败: {str(db_e)}")
                await message.reject(requeue=False)
            else:
            # 在消息处理成功后，确认消息
                await message.ack()





async def run_consumer():
    try:
        # 连接到 RabbitMQ
        connection = await aio_pika.connect_robust(
            "amqp://admin:wanglei135@192.168.4.69:5672/audit_test"
        )

        # 创建通道
        channel = await connection.channel()
        # 声明队列，并持久化
        queue = await channel.declare_queue("chat_tasks", durable=True)

        # 设置QoS，限制消费者一次只处理一个消息
        await channel.set_qos(prefetch_count=1)

        logger.info(' [*] 等待消息中...')

        # 开始消费
        await queue.consume(message_handler)
        # 保持协程运行
        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("消费者任务被取消")
    except Exception as e:
        logger.error(f"消费者发生错误: {e}")
    finally:
        # 确保资源被正确关闭
        if 'connection' in locals() and connection:
            await connection.close()


# 主程序入口
if __name__ == "__main__":
    # 直接运行单个消费者
    asyncio.run(run_consumer())