"""
测试用例服务类
负责测试用例数据库操作和执行管理
"""
from flask import current_app as app
import pymysql
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dbutils.pooled_db import PooledDB
from configs import config
from app import global_logger
import traceback

class TestcaseServiceError(Exception):
    """测试用例服务异常"""
    pass

class TestcaseService:
    """测试用例服务类"""

    def __init__(self):
        """初始化服务"""
        self.pool = PooledDB(pymysql, mincached=2, maxcached=5, host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                        user=config.MYSQL_USER, passwd=config.MYSQL_PASSWORD, database=config.MYSQL_DATABASE,
                        cursorclass=pymysql.cursors.DictCursor)
        global_logger.info("测试用例服务初始化成功")

    def create_batch_with_cases(self, testcases: List[Dict], interface_data: Dict) -> int:
        """
        创建批次并保存测试用例

        Args:
            testcases: 测试用例列表
            interface_data: 接口信息

        Returns:
            int: 批次ID
        """
        connection = None
        try:
            global_logger.info(f"开始创建批次并保存 {len(testcases)} 个测试用例")

            connection = self.pool.connection()
            cursor = connection.cursor()

            # 开启事务
            connection.begin()

            # 创建测试批次
            batch_id = str(uuid.uuid4())
            batch_name = f"AI生成-{interface_data.get('name', '未知接口')}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            batch_sql = """  
                INSERT INTO test_batch (id, name, description, environment, status, create_time)  
                VALUES (%s, %s, %s, %s, %s, %s)  
            """
            cursor.execute(batch_sql, (
                batch_id,
                batch_name,
                f"基于接口 {interface_data.get('name')} 的AI生成测试用例",
                'test',
                'created',
                datetime.now()
            ))

            # 批量保存测试用例
            case_sql = """  
                INSERT INTO test_case (id, batch_id, name, priority, request_method, request_url,   
                                     request_headers, request_body, request_params, expected_status,   
                                     assertions, description, create_time)  
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)  
            """

            saved_count = 0
            for testcase in testcases:
                try:
                    case_id = str(uuid.uuid4())
                    cursor.execute(case_sql, (
                        case_id,
                        batch_id,
                        testcase.get('name', '未命名测试用例'),
                        testcase.get('priority', 2),
                        testcase.get('request_method', 'GET'),
                        testcase.get('request_url', '/api/test'),
                        json.dumps(testcase.get('request_headers', {})),
                        json.dumps(testcase.get('request_body', {})),
                        json.dumps(testcase.get('request_params', {})),
                        testcase.get('expected_status', 200),
                        json.dumps(testcase.get('assertions', [])),
                        testcase.get('description', ''),
                        datetime.now()
                    ))
                    saved_count += 1
                except Exception as e:
                    global_logger.error(f"保存测试用例失败: {testcase.get('name', '未知')}, 错误: {e}")
                    continue

                    # 提交事务
                    connection.commit()
                    cursor.close()

                global_logger.info(f"成功创建批次 {batch_name}，保存 {saved_count} 个测试用例")
                return batch_id

        except Exception as e:
            if connection:
                connection.rollback()
            global_logger.error(f"创建批次失败: {traceback.format_exc()}")
            raise TestcaseServiceError(f"创建批次失败: {e}")
        finally:
            if connection:
                connection.close()

    def execute_batch(self, batch_id: str) -> bool:
        """
        执行批次测试 (复用现有执行逻辑)

        Args:
            batch_id: 批次ID

        Returns:
            bool: 执行是否成功启动
        """
        try:
            global_logger.info(f"开始执行批次测试: {batch_id}")

            # 这里调用现有的批次执行逻辑
            # 假设你已有的执行方法是 execute_test_batch
            from apis.testexec import execute_batch_testcases_async

            # 异步执行测试
            from app import celery
            task = execute_batch_testcases_async.delay(batch_id)

            global_logger.info(f"批次测试已提交执行，任务ID: {task.id}")
            return True

        except Exception as e:
            global_logger.error(f"执行批次测试失败: {traceback.format_exc()}")
            raise TestcaseServiceError(f"执行批次测试失败: {e}")

    def get_batch_results(self, batch_id: str) -> Dict:
        """
        获取批次执行结果

        Args:
            batch_id: 批次ID

        Returns:
            Dict: 批次结果信息
        """
        connection = None
        try:
            global_logger.info(f"获取批次结果: {batch_id}")

            connection = self.pool.connection()
            cursor = connection.cursor(pymysql.cursors.DictCursor)

            # 获取批次信息
            batch_sql = """  
                        SELECT id, name, description, environment, status, create_time, update_time  
                        FROM test_batch WHERE id = %s  
                    """
            cursor.execute(batch_sql, (batch_id,))
            batch_info = cursor.fetchone()

            if not batch_info:
                raise TestcaseServiceError(f"批次不存在: {batch_id}")

                # 获取测试结果
            results_sql = """  
                        SELECT tc.name as testcase_name, tc.description,  
                               tr.status, tr.response_status, tr.response_time,  
                               tr.error_message, tr.execute_time,  
                               CASE WHEN tr.status = 'success' THEN 1 ELSE 0 END as is_success  
                        FROM test_case tc  
                        LEFT JOIN test_result tr ON tc.id = tr.testcase_id  
                        WHERE tc.batch_id = %s  
                        ORDER BY tc.create_time  
                    """
            cursor.execute(results_sql, (batch_id,))
            test_results = cursor.fetchall()

            cursor.close()

            return {
                'batch_info': batch_info,
                'test_results': test_results
            }

        except Exception as e:
            global_logger.error(f"获取批次结果失败: {traceback.format_exc()}")
            raise TestcaseServiceError(f"获取批次结果失败: {e}")
        finally:
            if connection:
                connection.close()

    def get_batch_status(self, batch_id: str) -> str:
        """
        获取批次执行状态

        Args:
            batch_id: 批次ID

        Returns:
            str: 批次状态
        """
        connection = None
        try:
            connection = self.pool.connection()
            cursor = connection.cursor()

            sql = "SELECT status FROM test_batch WHERE id = %s"
            cursor.execute(sql, (batch_id,))
            result = cursor.fetchone()

            cursor.close()
            return result[0] if result else 'not_found'

        except Exception as e:
            global_logger.error(f"获取批次状态失败: {e}")
            return 'error'
        finally:
            if connection:
                connection.close()

                # 单例实例


_testcase_service = None


def get_testcase_service() -> TestcaseService:
    """获取测试用例服务实例"""
    global _testcase_service
    if _testcase_service is None:
        try:
            _testcase_service = TestcaseService()
        except Exception as e:
            global_logger.error(f"测试用例服务初始化失败: {e}")
            raise
    return _testcase_service