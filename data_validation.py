from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, delete
from app.models.models import File as FileModel, VulnerabilityReport, Message, TaskStatus

from app.models.database import async_get_db  # 导入优化后的异步数据库连接函数
security_issues = {
    "输入验证": [
        "关键状态数据外部可控", "数据真实性验证", "绕过数据净化和验证",
        "在字符串验证前未进行过滤", "对HTTP头Web脚本特殊元素处理", "命令行注入",
        "数据结构控制域安全", "忽略字符串结尾符", "对环境变量长度做出假设",
        "条件比较不充分", "结构体长度", "数值赋值越界", "除零错误", "边界值检查缺失",
        "数据信任边界的违背", "条件语句缺失默认情况", "无法执行的死代码",
        "表达式永真或永假"
    ],
    "输出编码": [
        "密码安全", "随机数安全", "使用安全相关的硬编码"
    ],
    "数据保护": [
        "敏感信息暴露", "个人信息保护"
    ],
    "访问控制": [
        "身份鉴别被绕过", "身份鉴别尝试频率限制", "多因素认证"
    ],
    "口令安全": [
        "登录口令", "明文存储口令"
    ],
    "权限管理": [
        "权限访问控制", "未加限制的外部可访问锁"
    ],
    "日志安全": [
        "对输出日志中特殊元素处理", "信息丢失或遗漏"
    ],
    "面向对象程序安全": [
        "（）和非泛型数据类型", "包含敏感信息类的安全", "类比较",
        "类私有可变成员的引用", "存储不可序列化的对象到磁盘"
    ],
    "并发程序安全": [
        "不同会话间信息泄露", "发布未完成初始化的对象", "共享资源的并发安全",
        "子进程访问父进程敏感资源", "释放线程专有对象"
    ],
    "函数调用安全": [
        "格式化字符串", "对方法或函数参数验证", "参数指定错误", "返回栈变量地址",
        "实现不一致函数", "暴露危险的方法或函数"
    ],
    "异常处理安全": [
        "异常处理安全"
    ],
    "指针安全": [
        "不兼容的指针类型", "利用指针减法确定内存大小", "将固定地址赋值给指针",
        "试图访问非结构体类型指针的数据域", "指针偏移越界", "无效指针使用"
    ],
    "代码生成安全": [
        "编译环境安全", "链接环境安全"
    ],
    "资源管理": [
        "重复释放资源", "资源或变量不安全初始化", "初始化失败后未安全退出",
        "引用计数的更新不正确", "资源不安全清理", "将资源暴露给非授权范围",
        "未经控制的递归", "无限循环", "算法复杂度攻击", "早期放大攻击"
    ],
    "内存管理": [
        "内存分配释放函数成对调用", "堆内存释放", "内存未释放", "访问已释放内存",
        "数据 / 内存布局", "内存缓冲区边界操作", "缓冲区复制造成溢出",
        "使用错误长度访问缓冲区", "堆空间耗尽"
    ],
    "数据库管理": [
        "及时释放数据库资源", "SQL 注入"
    ],
    "文件管理": [
        "过期的文件描述符", "不安全的临时文件", "文件描述符穷尽", "路径遍历",
        "及时释放文件系统资源"
    ],
    "网络传输": [
        "端口多重绑定", "对网络消息容量的控制", "字节序使用", "通信安全",
        "会话过期机制缺失", "会话标识符"
    ]
}

def type_verification(type_dict):
    type_true = {}
    for idx, (key, value) in enumerate(type_dict.items()):
        if key in security_issues:
            if value in security_issues[key]:
                type_true[key] = value
            else:
                type_true[key] = False
        else:
            type_true[key] = False

    return type_true

def snippet_verification(snippet):
    snippet_true = []
    for i in snippet:
        try:
            j = eval(i)
            int_list = [int(item) for item in j]
            snippet_true.append(int_list)
        except:
            int_list = []
            snippet_true.append(int_list)
    return snippet_true

def get_line(value, line_count):
    if len(value) == 1:
        line = value[0]
    else:
        line = value[int(len(value)/2)]
        t = True
        for i in value:
            if line - 10 > i or i >= line + 10:
                t = False
        if not t:
            line = value[1]
    start_line = line - 10
    end_line = line + 10
    if start_line < 0:
        start_line = 0
        end_line = end_line - start_line
        if end_line >= line_count:
            end_line = line_count
    if end_line >= line_count:
        end_line = line_count
        start_line = start_line - (end_line - line_count)
        if start_line < 0:
            start_line = 0
    return start_line, end_line




