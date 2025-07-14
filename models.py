from datetime import date
from enum import Enum as pyEnum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLAlchemyEnum, BigInteger, Text, Boolean, Date
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.sql import func
from app.models.database import Base

class TaskStatus(str, pyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class File(Base):
    __tablename__ = "file"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), index=True, nullable=False)  # 指定长度并设置非空
    filename = Column(String(255), index=True)  # 文件名长度限制
    file_size = Column(String(255), index = True)  # 指定长度并设置非空
    prompt_tokens = Column(BigInteger, nullable=False, default=0)
    completion_tokens = Column(BigInteger, nullable=False, default=0)
    sub_files_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    session_task_id = Column(String(255), index=True, nullable=False)  # 指定长度并设置非空
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    project_type = Column(String(255))  # 项目类型
    code_lines = Column(BigInteger, nullable=False, default=0)  # 代码行数
    status = Column(
        SQLAlchemyEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING
    )
    callback_upload_url = Column(String(255), nullable=True)
    callback_chat_url = Column(String(255), nullable=True)
    score = Column(Integer, nullable=False, default=0)
    dependencies_count = Column(Integer, nullable=False, default=0)
    issue_dependencies = Column(Integer, nullable=False, default=0)
    content = Column(MEDIUMTEXT)
    project_language = Column(String(255))

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), index=True, nullable=False)  # 指定长度并设置非空
    status = Column(
        SQLAlchemyEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING
    )
    session_task_id = Column(String(255), index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    result = Column(Text, nullable=True)
    task_type = Column(String(20), nullable=False)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_task_id = Column(String(255), index=True, nullable=False)  # 文件名长度限制
    role = Column(SQLAlchemyEnum("system", "user", "assistant", name="role_enum"))
    content = Column(MEDIUMTEXT)
    created_at = Column(DateTime, server_default=func.now())
    is_true = Column(Boolean, nullable=False, default=False)



class VulnerabilityReport(Base):
    """漏洞报告数据表"""
    __tablename__ = 'vulnerability_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_task_id = Column(String(255), nullable=False, index=True)
    danger_level = Column(SQLAlchemyEnum('高危', '中危', '低危'), nullable=False)
    category = Column(String(255), nullable=False)
    probability = Column(String(255),nullable=False)
    vulnerability_type = Column(String(255), nullable=False)
    vulnerability_code = Column(Text, nullable=False)
    defect_details = Column(Text)
    fix_suggestion = Column(Text, nullable=False)
    language = Column(String(255))
    file_path = Column(String(255), nullable=False)
    code_snippet = Column(String(255))
    defect_type = Column(String(255))
    defect_name = Column(String(255))
    is_issue = Column(String(255), default="未审计")  # 审计后是否是问题
    audit_danger_level = Column(String(255))  # 审计后的危险等级
    audit_remarks = Column(Text, nullable=True)
    detection_time = Column(DateTime(timezone=True))


# 数据库表模型
class GitConfig(Base):
    __tablename__ = "git_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), index=True, nullable=False)  # 指定长度并设置非空
    access_token = Column(String(512), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # 推荐存储密码哈希
    git_type = Column(SQLAlchemyEnum("gitlab", "gitee", "gitea"), nullable=False)
    mode = Column(Boolean, nullable=False)  # 0 表示 False，1 表示 True


class TokenUsage(Base):
    __tablename__ = 'token_usage'
    user_id = Column(String(50), primary_key=True)             # 用户ID
    chat_count = Column(Integer, default=0)             # 聊天数量
    task_input_tokens = Column(Integer, default=0)             # 任务输入 token 数量
    task_output_tokens = Column(Integer, default=0)            # 任务输出 token 数量
    token_limit = Column(Integer, default=500000)  # token 上限
    chat_count_limit = Column(Integer, default=10)  # 聊天次数上限
    expiration_date = Column(Date, default=date.today)  # 使用日期，精确到天
