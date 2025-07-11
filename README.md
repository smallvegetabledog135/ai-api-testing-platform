# AI接口测试平台

基于AI的智能接口测试平台，支持AI生成测试用例、批量执行、智能结果分析和邮件通知。

## 技术栈

- **后端框架**: Flask + Blueprint模块化设计
- **消息队列**: RabbitMQ (任务分发)
- **缓存系统**: Redis (结果存储 + 缓存)
- **异步任务**: Celery (后台任务处理)
- **数据库**: MySQL (业务数据持久化)
- **监控系统**: Prometheus (性能监控)
- **AI集成**: DeepSeek API (智能分析)
- **开发语言**: Python 3.7+

## 业务流程

### AI驱动的测试流程
```
用户创建接口 → AI根据接口内容生成测试用例 →提交批量执行 → Celery异步处理任务 → RabbitMQ任务分发 → 并发执行HTTP请求 → 结果存储Redis → AI分析测试结果 →生成智能报告 → 邮件通知用户
```

### 核心业务模块
用户管理、应用管理、接口管理、AI用例生成、测试执行、AI结果分析、报告生成、邮件通知

## 数据库表结构
每张表的创建sql文件全部已经导出
[测试平台SQL.zip](https://github.com/user-attachments/files/21174481/SQL.zip)


### 核心业务表说明

**apps（应用管理）**：存储应用配置、环境信息、基础URL等应用级别信息

**api_interface（接口管理）**：定义API接口信息、请求参数、响应结构、接口路径和方法

**api_testcase（测试用例）**：存储AI生成的测试用例、断言规则、优先级、请求数据

**api_testbatch（测试批次）**：管理批量执行的批次信息、执行状态、汇总统计

**api_result（执行结果）**：记录每次测试执行的详细结果、响应时间、错误信息

## 日志系统

### 日志文件结构
```
logs/
├── service.log          # 应用日志
```

### 日志级别
- **DEBUG**: 详细调试信息
- **INFO**: 正常业务流程记录
- **WARNING**: 警告信息，如参数异常、性能问题
- **ERROR**: 错误信息，如接口调用失败、数据库连接异常
- **CRITICAL**: 严重错误，系统无法正常运行

## Postman测试脚本

完整的Postman测试集合已导出为JSON文件：
[接口测试脚本.zip](https://github.com/user-attachments/files/21174420/default.zip)

<img width="172" height="191" alt="image" src="https://github.com/user-attachments/assets/bb472b3d-9056-45c0-89bc-a7782b48cbaf" />

包含以下测试场景：
- 用户注册登录
- 应用管理
- 接口定义和管理
- AI生成测试用例
- 批量执行测试
- 查询执行结果
- 获取AI分析报告
- 邮件通知测试

## 快速启动

### 环境准备
```bash
# 系统要求
Python >= 3.7
MySQL >= 8.0
Redis >= 6.0
RabbitMQ >= 3.8

# 安装Python依赖
pip install -r requirements.txt

# 启动基础服务
sudo systemctl start mysql redis-server rabbitmq-server

# 初始化数据库
mysql -u root -p < database/init.sql
```

### 启动命令
```bash
# 1. 启动Celery Worker
celery -A app.celery worker --loglevel=info --detach

# 2. 启动Flask应用
python app.py
```

## 监控地址

- **主应用**: http://localhost:5000
- **Prometheus监控**: http://localhost:9091/metrics
- **RabbitMQ管理**: http://localhost:15672
- **Redis监控**: redis-cli monitor
