# metrics.py
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import threading

# 定义指标
TEST_CASE_TOTAL = Counter('test_case_total', '测试用例总数', ['result'])
TEST_CASE_DURATION = Histogram('test_case_duration_seconds', '测试用例执行时间(秒)',
                               buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120])
QUEUE_LENGTH = Gauge('task_queue_length', '任务队列长度')
ASSERTION_TOTAL = Counter('assertion_total', '断言总数', ['result'])
HTTP_REQUEST_TOTAL = Counter('http_request_total', 'HTTP请求总数', ['method', 'status_code'])
HTTP_REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP请求耗时(秒)',
                                  ['method'], buckets=[0.1, 0.5, 1, 2, 5, 10, 30])


# 启动指标服务器
def start_metrics_server(port=8000):
    """启动Prometheus指标HTTP服务器"""

    def _start_server():
        start_http_server(port)
        print(f"Prometheus metrics server started on port {port}")

        # 在单独的线程中启动，避免阻塞主线程

    thread = threading.Thread(target=_start_server)
    thread.daemon = True
    thread.start()


# 记录测试用例结果
def record_test_result(success, duration_seconds):
    """记录测试用例执行结果"""
    result = 'success' if success else 'failure'
    TEST_CASE_TOTAL.labels(result=result).inc()
    TEST_CASE_DURATION.observe(duration_seconds)


# 记录断言结果
def record_assertion_result(success):
    """记录断言结果"""
    result = 'success' if success else 'failure'
    ASSERTION_TOTAL.labels(result=result).inc()


# 记录HTTP请求
def record_http_request(method, status_code, duration_seconds):
    """记录HTTP请求结果"""
    HTTP_REQUEST_TOTAL.labels(method=method, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=method).observe(duration_seconds)


# 更新队列长度
def update_queue_length(length):
    """更新任务队列长度"""
    QUEUE_LENGTH.set(length)


# 初始化函数，在应用启动时调用
def init_metrics(port=8000):
    """初始化指标收集"""
    start_metrics_server(port)
    print("Prometheus metrics initialized")