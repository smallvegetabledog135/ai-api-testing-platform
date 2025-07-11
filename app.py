# -*- coding:utf-8 -*-
from flask import Flask
from apis.user import app_user
from apis.product import app_product
from apis.application import app_application
from apis.testmanager import test_manager
from apis.dashboard import test_dashboard
from flask_cors import CORS
from configs import format
from flask import make_response, render_template
import logging   #python标准库，提供日志功能
from logging.handlers import RotatingFileHandler
from celery import Celery
from utils import metrics
from prometheus_client import start_http_server


def setup_global_logger():
    logger=logging.getLogger('global_logger')
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        handler=RotatingFileHandler('logs/service.log', maxBytes=10485760, backupCount=10)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

app = Flask(__name__)
#setup_logger(app)
global_logger = setup_global_logger()


app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379/0',
    CELERY_RESULT_BACKEND='redis://localhost:6379/0',
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],
    CELERY_RESULT_SERIALIZER='json',
    CELERY_TIMEZONE='UTC',
    CELERY_ENABLE_UTC=True,
    CELERY_TASK_REJECT_ON_WORKER_LOST=False,  # 添加这一行
    CELERY_IMPORTS=['apis.testexec'],
)

celery = make_celery(app)

CORS(app, supports_credentials=True)

app.register_blueprint(app_user)
app.register_blueprint(app_product)
app.register_blueprint(app_application)
app.register_blueprint(test_manager)
app.register_blueprint(test_dashboard)
#app.register_blueprint(interface)
try:
    from apis.interface import interface
    app.register_blueprint(interface)
    print("接口管理蓝图注册成功")
except Exception as e:
    print(f"接口管理蓝图注册失败: {e}")

try:
    from apis.testcase import testcase
    app.register_blueprint(testcase)
    print("用例管理蓝图注册成功")
except Exception as e:
    print(f"用例管理蓝图注册失败: {e}")

try:
    from apis.testexec import testexec
    app.register_blueprint(testexec)
    print("用例执行蓝图注册成功")
except Exception as e:
    print(f"用例执行蓝图注册失败: {e}")

try:
    from apis.ai_route import ai_route
    app.register_blueprint(ai_route)
    print("ai路由蓝图注册成功")
except Exception as e:
    print(f"ai路由执行蓝图注册失败: {e}")


app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

@app.errorhandler(413)
def request_entity_too_large(err):
    '''自定义的处理错误方法'''
    resp_failed = format.resp_format_failed
    resp_failed["message"] = '文件超出大小限制10M'
    return resp_failed

@app.after_request
def after_request(response):
    if response.status_code != 200:
        headers = {'content-type': 'application/json'}
        res = make_response(format.resp_format_failed)
        res.headers = headers
        return res
    return response

@app.route('/')
def index():
    return render_template("index.html")


if __name__ == '__main__':
    # 启动指标服务器
    metrics.init_metrics(port=9091)
    start_http_server(9091)
    print("Prometheus metrics server started on port 9091")
    print("程序启动成功")
    app.run(debug=True)

