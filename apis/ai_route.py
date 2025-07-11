# apis/ai_route.py  
import uuid
from flask import Blueprint, request, jsonify, current_app as app
from concurrent.futures import ThreadPoolExecutor
import threading
import requests
import traceback
from datetime import datetime
from app import global_logger
from configs import format, config
import time
import json
from dbutils.pooled_db import PooledDB
from services.notification_service import send_email_task
import pymysql

ai_route = Blueprint('ai_route', __name__)

#获取数据库连接池
mysql_pool=PooledDB(
    creator=pymysql,
    maxconnections=6,
    mincached=2,
    maxcached=5,
    maxshared=3,
    blocking=True,
    maxusage=None,
    setsession=[],
    ping=0,
    host=config.MYSQL_HOST,
    port=config.MYSQL_PORT,
    user=config.MYSQL_USER,
    password=config.MYSQL_PASSWORD,
    database=config.MYSQL_DATABASE,
    cursorclass=pymysql.cursors.DictCursor
)


def execute_query(sql, params=None):
    """执行SQL查询（INSERT, UPDATE, DELETE）"""
    conn = None
    cursor = None
    try:
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()
        global_logger.error(f"执行SQL失败: {e}")
        global_logger.error(f"SQL: {sql}")
        global_logger.error(f"参数: {params}")
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_one(sql, params=None):
    """获取单条记录"""
    conn = None
    cursor = None
    try:
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        result = cursor.fetchone()
        return result

    except Exception as e:
        global_logger.error(f"查询单条记录失败: {e}")
        global_logger.error(f"SQL: {sql}")
        global_logger.error(f"参数: {params}")
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_all(sql, params=None):
    """获取多条记录"""
    conn = None
    cursor = None
    try:
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        results = cursor.fetchall()
        return results

    except Exception as e:
        global_logger.error(f"查询多条记录失败: {e}")
        global_logger.error(f"SQL: {sql}")
        global_logger.error(f"参数: {params}")
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@ai_route.route('/apis/ai_route/ping', methods=['GET'])
def ping():
    global_logger.info("收到Ping请求")
    return jsonify({
        "code": 200,
        "message": "pong",
        "timestamp": datetime.now().isoformat()
    })

@ai_route.route('/apis/ai_route/generate-testcases', methods=['POST'])
def generate_testcases():
    """AI生成测试用例并通过HTTP调用保存"""
    global_logger.info("=== 开始AI生成测试用例 ===")

    try:
        # 参数验证
        interface_data = request.get_json()
        if not interface_data:
            response = format.resp_format_failed.copy()
            response["message"] = "请求体不能为空"
            return response

            # 基础必需参数（放宽要求）
        required_fields = ['app_id', 'name', 'url', 'method']
        missing_fields = [field for field in required_fields if not interface_data.get(field)]
        if missing_fields:
            response = format.resp_format_failed.copy()
            response["message"] = f"缺少必需字段: {', '.join(missing_fields)}"
            return response

            # 设置默认值
        interface_data.setdefault('interface_id', interface_data.get('app_id') + '_default_if')
        interface_data.setdefault('creator_id', 'ai_system')
        interface_data.setdefault('creator_name', 'AI系统')
        interface_data.setdefault('category', interface_data.get('category', '用户管理'))
        interface_data.setdefault('description', interface_data.get('description', 'AI生成的测试用例'))

        global_logger.info(f"处理接口: {interface_data['name']} ({interface_data['method']} {interface_data['url']})")

        # 步骤1：创建AI批次
        global_logger.info("创建AI测试批次...")
        batch_id = str(uuid.uuid4()).replace('-', '')
        batch_name = interface_data.get('batch_name',
                                        f"AI测试-{interface_data['name']}-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        current_time = int(time.time())

        try:
            # 连接数据库创建批次
            conn = mysql_pool.connection()
            cursor = conn.cursor()

            batch_sql = """  
                INSERT INTO api_test_batch (  
                    id, app_id, name, total_cases, passed_cases, failed_cases,  
                    executor_name, create_time, status, ai_generated  
                ) VALUES (  
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s  
                )  
            """

            cursor.execute(batch_sql, [
                batch_id,
                interface_data['app_id'],
                batch_name,
                0,  # total_cases，稍后更新
                0,  # passed_cases
                0,  # failed_cases
                interface_data['creator_name'],
                current_time,
                1,  # status：创建中
                1  # ai_generated = 1
            ])

            conn.commit()
            cursor.close()
            conn.close()

            global_logger.info(f"AI批次创建成功，ID: {batch_id}")

        except Exception as e:
            global_logger.error(f"创建AI批次失败: {str(e)}")
            response = format.resp_format_failed.copy()
            response["message"] = f"创建AI批次失败: {str(e)}"
            return response

            # 步骤2：调用AI生成测试用例
        global_logger.info("调用AI服务生成测试用例...")
        from services.ai_service import get_ai_service
        ai_service = get_ai_service()
        global_logger.info(f"AI服务对象: {ai_service}")

        testcases = ai_service.generate_testcases(interface_data, count=10)
        global_logger.info(f"AI生成的测试用例: {testcases}")

        # 修改这里：如果AI生成失败，直接跳过，不报错
        if not testcases:
            global_logger.warning("AI服务返回空测试用例列表，跳过保存步骤")

            # 更新批次状态为完成，但测试用例数为0
            try:
                conn = mysql_pool.connection()
                cursor = conn.cursor()
                update_batch_sql = "UPDATE api_test_batch SET total_cases = %s, status = %s WHERE id = %s"
                cursor.execute(update_batch_sql, [0, 2, batch_id])  # status=2表示完成
                conn.commit()
                cursor.close()
                conn.close()
                global_logger.info(f"批次 {batch_id} 状态更新为完成，测试用例数量为0")
            except Exception as e:
                global_logger.error(f"更新批次状态失败: {str(e)}")

                # 返回成功响应，但说明没有生成测试用例
            response = format.resp_format_success.copy()
            response["message"] = "本次AI生成未产生有效测试用例，请重试或调整参数"
            response["data"] = {
                "total_generated": 0,
                "total_saved": 0,
                "total_failed": 0,
                "testcase_ids": [],
                "batch_id": batch_id,
                "batch_name": batch_name,
                "interface_info": {
                    "interface_id": interface_data['interface_id'],
                    "app_id": interface_data['app_id'],
                    "name": interface_data['name'],
                    "url": interface_data['url'],
                    "method": interface_data['method']
                }
            }
            global_logger.info("=== AI生成测试用例完成（无有效用例生成） ===")
            return response

        global_logger.info(f"AI生成了 {len(testcases)} 个测试用例")

        # 步骤3：通过HTTP调用保存测试用例（带batch_id）
        global_logger.info("通过HTTP调用保存测试用例...")
        saved_testcase_ids = []
        failed_count = 0

        # 获取当前服务的基础URL
        base_url = request.host_url.rstrip('/')
        add_testcase_url = f"{base_url}/api/testcase/add"

        for i, testcase in enumerate(testcases, 1):
            global_logger.info(f"保存第 {i}/{len(testcases)} 个测试用例: {testcase.get('name', '')}")

            # 构建请求数据 - 添加batch_id和ai_generated
            testcase_data = {
                "interface_id": interface_data['interface_id'],
                "app_id": interface_data['app_id'],
                "name": testcase.get('name', f'测试用例_{i}'),
                "priority": testcase.get('priority', 2),
                "request_url": testcase.get('request_url', interface_data['url']),
                "request_method": testcase.get('request_method', interface_data['method']),
                "request_headers": testcase.get('request_headers', {}),
                "request_params": testcase.get('request_params', {}),
                "expected_status": testcase.get('expected_status', 200),
                "assertions": testcase.get('assertions', [{"type": "status_code", "expected": 200}]),
                "pre_script": testcase.get('pre_script', ''),
                "post_script": testcase.get('post_script', ''),
                "description": testcase.get('description', f'AI生成的测试用例 - {testcase.get("name", "")}'),
                "status": testcase.get('status', 1),
                "creator_id": interface_data['creator_id'],
                "creator_name": interface_data['creator_name'],
                "batch_id": batch_id,  # 关键：设置批次ID
                "ai_generated": 1  # 关键：标记为AI生成
            }

            global_logger.info(f"准备保存测试用例数据: {testcase_data}")

            try:
                # 发起HTTP请求
                response_obj = requests.post(
                    add_testcase_url,
                    json=testcase_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )

                global_logger.info(f"HTTP请求状态码: {response_obj.status_code}")
                global_logger.info(f"HTTP响应内容: {response_obj.text}")

                if response_obj.status_code == 200:
                    result = response_obj.json()
                    if result.get('code') in [200, 20000]:
                        testcase_id = result['data']['id']
                        saved_testcase_ids.append(testcase_id)
                        global_logger.info(f"测试用例 {i} 保存成功，ID: {testcase_id}")
                    else:
                        failed_count += 1
                        global_logger.error(f"测试用例 {i} 保存失败: {result.get('message', '未知错误')}")
                else:
                    failed_count += 1
                    global_logger.error(
                        f"测试用例 {i} HTTP请求失败，状态码: {response_obj.status_code}, 响应: {response_obj.text}")

            except Exception as e:
                failed_count += 1
                global_logger.error(f"测试用例 {i} 保存异常: {str(e)}")

                # 步骤4：更新批次的测试用例数量
        try:
            conn = mysql_pool.connection()
            cursor = conn.cursor()

            update_batch_sql = "UPDATE api_test_batch SET total_cases = %s, status = %s WHERE id = %s"
            cursor.execute(update_batch_sql, [len(saved_testcase_ids), 2, batch_id])  # status=2表示完成

            conn.commit()
            cursor.close()
            conn.close()

            global_logger.info(f"批次 {batch_id} 测试用例数量更新为: {len(saved_testcase_ids)}")

        except Exception as e:
            global_logger.error(f"更新批次测试用例数量失败: {str(e)}")

            # 返回结果（包含batch_id）
        response = format.resp_format_success.copy()

        # 根据实际情况调整消息
        if len(saved_testcase_ids) == 0:
            response["message"] = f"AI生成了 {len(testcases)} 个测试用例，但保存时全部失败"
        elif failed_count == 0:
            response["message"] = f"AI生成测试用例完成，成功保存 {len(saved_testcase_ids)} 个"
        else:
            response["message"] = f"AI生成测试用例完成，成功保存 {len(saved_testcase_ids)} 个，失败 {failed_count} 个"

        response["data"] = {
            "total_generated": len(testcases),
            "total_saved": len(saved_testcase_ids),
            "total_failed": failed_count,
            "testcase_ids": saved_testcase_ids,
            "batch_id": batch_id,  # 关键：返回批次ID
            "batch_name": batch_name,  # 返回批次名称
            "interface_info": {
                "interface_id": interface_data['interface_id'],
                "app_id": interface_data['app_id'],
                "name": interface_data['name'],
                "url": interface_data['url'],
                "method": interface_data['method']
            }
        }

        global_logger.info("=== AI生成测试用例完成 ===")
        return response

    except Exception as e:
        global_logger.error(f"AI生成测试用例异常: {str(e)}")
        global_logger.error(f"异常堆栈: {traceback.format_exc()}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response

@ai_route.route('/apis/ai_route/full-test-flow', methods=['POST'])
def full_test_flow():
    """完整的AI测试流程：生成->执行->分析->报告"""
    global_logger.info("=== 开始完整AI测试流程 ===")

    try:
        # 获取请求参数
        flow_data = request.get_json()
        if not flow_data:
            response = format.resp_format_failed.copy()
            response["message"] = "请求体不能为空"
            return response

            # 基础参数验证
        required_fields = ['app_id', 'name', 'url', 'method']
        missing_fields = [field for field in required_fields if not flow_data.get(field)]
        if missing_fields:
            response = format.resp_format_failed.copy()
            response["message"] = f"缺少必需字段: {', '.join(missing_fields)}"
            return response

        interface_id = get_or_create_interface(flow_data)
        flow_data['interface_id'] = interface_id

            # 设置默认值
        flow_data.setdefault('interface_id', flow_data.get('app_id') + '_default_if')
        flow_data.setdefault('creator_id', 'ai_system')
        flow_data.setdefault('creator_name', 'AI系统')
        flow_data.setdefault('environment', 'test')
        flow_data.setdefault('batch_name', f"AI测试-{flow_data['name']}-{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        base_url = request.host_url.rstrip('/')

        # 步骤1：调用生成测试用例接口
        global_logger.info("步骤1: 调用生成测试用例接口...")

        generate_url = f"{base_url}/apis/ai_route/generate-testcases"
        generate_response = requests.post(generate_url, json=flow_data, timeout=180)

        if generate_response.status_code != 200:
            response = format.resp_format_failed.copy()
            response["message"] = f"生成测试用例接口调用失败: HTTP {generate_response.status_code}"
            return response

        generate_result = generate_response.json()
        if generate_result.get('code') not in [200, 20000]:
            response = format.resp_format_failed.copy()
            response["message"] = f"生成测试用例失败: {generate_result.get('message')}"
            return response

        testcase_ids = generate_result['data']['testcase_ids']
        if not testcase_ids:
            response = format.resp_format_failed.copy()
            response["message"] = "没有成功生成测试用例"
            return response

        global_logger.info(f"步骤1完成: 生成了 {len(testcase_ids)} 个测试用例")

        # 步骤2：调用批量执行接口
        global_logger.info("步骤2: 调用批量执行接口...")

        batch_execute_url = f"{base_url}/api/testexec/batch_execute"

        batch_data = {
            "name": flow_data['batch_name'],
            "app_id": flow_data['app_id'],
            "testcase_ids": testcase_ids,
            "environment": flow_data['environment'],
            "variables": flow_data.get('variables', {}),
            "test_request_id": flow_data.get('test_request_id', ""),
            "batch_id": generate_result['data']['batch_id']  # 传递batch_id
        }

        batch_response = requests.post(batch_execute_url, json=batch_data, timeout=60)

        if batch_response.status_code != 200:
            response = format.resp_format_failed.copy()
            response["message"] = f"批量执行接口调用失败: HTTP {batch_response.status_code}"
            return response

        batch_result = batch_response.json()
        if batch_result.get('code') not in [200, 20000]:
            response = format.resp_format_failed.copy()
            response["message"] = f"批量执行失败: {batch_result.get('message')}"
            return response

        batch_id = batch_result['data']['batch_id']
        global_logger.info(f"步骤2完成: 批量执行ID = {batch_id}")

        # 步骤3：等待执行完成并获取结果
        global_logger.info("步骤3: 等待执行完成并获取结果...")
        # 等待批次完成
        batch_completed = wait_for_batch_completion(batch_id)
        if not batch_completed:
            global_logger.warning("批次可能未完全执行完成，但继续生成报告")

            # 然后再获取结果
        global_logger.info("开始获取测试结果...")

        # 等待批次执行完成（改进版）
        global_logger.info(f"等待批次 {batch_id} 执行完成...")

        # 先等待一段时间让测试开始
        time.sleep(3)

        # 循环检查直到有结果
        max_wait_time = 120  # 最大等待2分钟
        wait_interval = 5  # 每5秒检查一次
        waited_time = 0

        test_results = []
        while waited_time < max_wait_time:
            try:
                conn = mysql_pool.connection()
                cursor = conn.cursor()

                # 检查是否有测试结果
                check_sql = "SELECT COUNT(*) FROM api_result WHERE batch_id = %s"
                global_logger.info(f"执行SQL: {check_sql}, 参数: {batch_id}")
                cursor.execute(check_sql, [batch_id])

                result_row = cursor.fetchone()
                global_logger.info(f"查询结果: {result_row}")

                #处理字典格式的返回结果
                if result_row:
                    if isinstance(result_row, dict):
                        result_count = result_row.get('COUNT(*)', 0)  # 字典格式
                    else:
                        result_count = result_row[0]  # 元组格式
                else:
                    result_count = 0
                global_logger.info(f"结果数量: {result_count}")

                global_logger.info(f"等待中... 当前结果数: {result_count}, 已等待: {waited_time}s")
                if result_count > 0:
                    global_logger.info(f"检测到 {result_count} 个测试结果，开始获取详细数据")
                    break

                cursor.close()
                conn.close()

            except Exception as e:
                global_logger.error(f"检查测试结果时出错: {str(e)}")
                if 'cursor' in locals():
                    cursor.close()
                if 'conn' in locals():
                    conn.close()

            time.sleep(wait_interval)
            waited_time += wait_interval

        if waited_time >= max_wait_time:
            global_logger.warning(f"等待超时({max_wait_time}s)，可能测试还在执行中")

            # 最终查询所有结果
        try:
            conn = mysql_pool.connection()
            cursor = conn.cursor()

            result_sql = """  
                SELECT r.id, r.testcase_id, t.name as testcase_name,   
                       r.request_url, r.request_method, r.response_status,   
                       r.is_success, r.execution_time, r.execute_time,  
                       r.error_message, r.request_body, r.response_body  
                FROM api_result r  
                LEFT JOIN api_testcase t ON r.testcase_id = t.id  
                WHERE r.batch_id = %s  
                ORDER BY r.execute_time  
            """

            cursor.execute(result_sql, [batch_id])
            results = cursor.fetchall()

            global_logger.info(f"最终查询到 {len(results)} 个测试结果")

            # 处理查询结果
            for result in results:
                # 将数据库结果转换为字典
                if not isinstance(result, dict):
                    columns = ['id', 'testcase_id', 'testcase_name', 'request_url',
                               'request_method', 'response_status', 'is_success',
                               'execution_time', 'execute_time', 'error_message',
                               'request_body', 'response_body']
                    result_dict = dict(zip(columns, result))
                else:
                    result_dict = result

                    # 添加status字段
                result_dict['status'] = 'PASS' if result_dict.get('is_success') else 'FAIL'

                # 解析JSON字段
                try:
                    if 'request_body' in result_dict and result_dict['request_body']:
                        if isinstance(result_dict['request_body'], str):
                            result_dict['request_body'] = json.loads(result_dict['request_body'])
                    if 'response_body' in result_dict and result_dict['response_body']:
                        if isinstance(result_dict['response_body'], str):
                            result_dict['response_body'] = json.loads(result_dict['response_body'])
                except Exception as e:
                    global_logger.warning(f"解析JSON字段失败: {str(e)}")

                test_results.append(result_dict)

        except Exception as e:
            global_logger.error(f"查询测试结果出错: {str(e)}")
            global_logger.error(traceback.format_exc())
        finally:
            cursor.close()
            conn.close()

        global_logger.info(f"步骤3完成: 获取到 {len(test_results)} 个测试结果")

        # 步骤4-5：并行处理Excel报告和邮件发送
        global_logger.info("步骤4-5: 并行生成Excel报告和发送邮件...")

        # 计算测试结果统计信息（提前计算，供两个任务使用）
        total_cases = len(test_results)
        success_count_by_is_success = sum(1 for result in test_results if result.get('is_success') == True)
        success_count_by_response_status = sum(
            1 for result in test_results if 200 <= result.get('response_status', 0) < 300)

        # 选择最合适的成功数量
        if success_count_by_is_success > 0:
            success_count = success_count_by_is_success
        else:
            success_count = success_count_by_response_status

        failed_count = total_cases - success_count
        success_rate = (success_count / total_cases * 100) if total_cases > 0 else 0

        global_logger.info(
            f"测试统计: 总数={total_cases}, 成功={success_count}, 失败={failed_count}, 成功率={success_rate:.1f}%")

        # 准备共享数据
        shared_data = {
            'batch_id': batch_id,
            'test_results': test_results,
            'total_cases': total_cases,
            'success_count': success_count,
            'failed_count': failed_count,
            'success_rate': success_rate,
            'flow_data': flow_data,
            'base_url': base_url
        }

        # 并行处理Excel和邮件
        report_url = None
        email_task_id = None

        def generate_excel_task(shared_data):
            """生成Excel报告任务"""
            try:
                global_logger.info("开始生成Excel报告...")
                export_url = f"{shared_data['base_url']}/api/testexec/export_report?batch_id={shared_data['batch_id']}"
                global_logger.info(f"Excel报告生成完成: {export_url}")
                return export_url
            except Exception as e:
                global_logger.error(f"生成Excel报告失败: {str(e)}")
                return None

        def send_email_task(shared_data):
            """发送邮件任务 - AI增强版"""
            try:
                global_logger.info("开始发送邮件报告...")

                # 🔧 重新查询数据库获取测试结果
                test_results = []
                try:
                    conn = mysql_pool.connection()
                    cursor = conn.cursor()

                    result_sql = """  
                        SELECT r.id, r.testcase_id, t.name as testcase_name,   
                               r.request_url, r.request_method, r.response_status,   
                               r.is_success, r.execution_time, r.execute_time,  
                               r.error_message, r.request_body, r.response_body  
                        FROM api_result r  
                        LEFT JOIN api_testcase t ON r.testcase_id = t.id  
                        WHERE r.batch_id = %s  
                        ORDER BY r.execute_time  
                    """

                    cursor.execute(result_sql, [shared_data['batch_id']])
                    results = cursor.fetchall()

                    global_logger.info(f"邮件任务重新查询到 {len(results)} 条结果")

                    # 处理查询结果
                    for result in results:
                        if not isinstance(result, dict):
                            columns = ['id', 'testcase_id', 'testcase_name', 'request_url',
                                       'request_method', 'response_status', 'is_success',
                                       'execution_time', 'execute_time', 'error_message',
                                       'request_body', 'response_body']
                            result_dict = dict(zip(columns, result))
                        else:
                            result_dict = result

                        result_dict['status'] = 'PASS' if result_dict.get('is_success') else 'FAIL'
                        test_results.append(result_dict)

                except Exception as e:
                    global_logger.error(f"邮件任务查询数据库失败: {str(e)}")
                    test_results = []
                finally:
                    cursor.close()
                    conn.close()

                    # 重新计算统计信息
                total_cases = len(test_results)
                success_count = sum(1 for result in test_results if result.get('is_success') == True)
                failed_count = total_cases - success_count
                success_rate = (success_count / total_cases * 100) if total_cases > 0 else 0

                global_logger.info(f"邮件任务统计: 总数={total_cases}, 成功={success_count}, 失败={failed_count}")

                # 确定整体状态和风险级别
                overall_status = 'PASS' if failed_count == 0 else 'FAIL'
                risk_level = 'LOW' if success_rate >= 90 else ('MEDIUM' if success_rate >= 70 else 'HIGH')

                # 🔥 AI智能分析
                ai_analysis = None
                analysis_type = 'RULE_BASED'

                try:
                    if failed_count > 0:  # 只有存在失败时才进行AI分析
                        global_logger.info("开始AI智能分析失败原因...")
                        ai_analysis = _ai_analyze_failures(test_results, shared_data['flow_data'])
                        if ai_analysis:
                            analysis_type = 'AI_ENHANCED'
                            global_logger.info("AI分析完成")
                        else:
                            global_logger.warning("AI分析返回空结果，使用规则分析")
                    else:
                        global_logger.info("所有测试通过，跳过AI分析")
                except Exception as e:
                    global_logger.error(f"AI分析失败，使用规则分析: {str(e)}")

                    # 准备分析数据
                analysis_data = {
                    'summary': {
                        'total_cases': total_cases,
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'success_rate': success_rate,
                        'overall_status': overall_status,
                        'risk_level': risk_level,
                        'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'analysis_type': analysis_type
                    },
                    'key_findings': [
                        f"接口 {shared_data['flow_data']['name']} 测试完成，共执行 {total_cases} 个测试用例",
                        f"成功率: {success_rate:.1f}%，通过 {success_count} 个，失败 {failed_count} 个"
                    ],
                    'failure_analysis': [],
                    'recommendations': [],
                    'next_steps': [
                        "查看详细测试报告以了解更多信息",
                        f"访问报告链接: {shared_data['base_url']}/api/testexec/export_report?batch_id={shared_data['batch_id']}"
                    ]
                }

                # 🔥 集成AI分析结果
                if ai_analysis and analysis_type == 'AI_ENHANCED':
                    global_logger.info("集成AI分析结果到邮件报告")

                    # 添加AI分析标识
                    analysis_data['ai_insights'] = ai_analysis
                    analysis_data['analysis_powered_by'] = 'AI + 规则分析'

                    # 使用AI生成的内容
                    if ai_analysis.get('failure_analysis'):
                        analysis_data['failure_analysis'] = ai_analysis['failure_analysis']

                    if ai_analysis.get('recommendations'):
                        analysis_data['recommendations'] = ai_analysis['recommendations']

                    if ai_analysis.get('key_findings'):
                        analysis_data['key_findings'].extend(ai_analysis['key_findings'])

                        # 添加AI专业洞察
                    if ai_analysis.get('root_cause'):
                        analysis_data['root_cause_analysis'] = ai_analysis['root_cause']

                    if ai_analysis.get('risk_assessment'):
                        analysis_data['ai_risk_assessment'] = ai_analysis['risk_assessment']

                else:
                    # 使用原有的规则分析
                    analysis_data['analysis_powered_by'] = '规则分析'

                    if failed_count > 0:
                        failure_reasons = []
                        for result in test_results:
                            if not result.get('is_success'):
                                reason = result.get('error_message', '未知错误')
                                testcase_name = result.get('testcase_name',
                                                           f"用例ID: {result.get('testcase_id', 'unknown')}")
                                failure_reasons.append(f"{testcase_name}: {reason}")

                        analysis_data['failure_analysis'] = failure_reasons
                        analysis_data['recommendations'] = [
                            "检查接口参数验证逻辑",
                            "确认接口返回值是否符合预期",
                            "验证边界条件和异常场景处理"
                        ]
                    else:
                        analysis_data['recommendations'] = [
                            "继续保持良好的接口质量",
                            "考虑添加更多边界条件测试"
                        ]

                        # 批次信息
                batch_info = {
                    'name': shared_data['flow_data']['batch_name'],
                    'id': shared_data['batch_id'],
                    'interface_name': shared_data['flow_data']['name'],
                    'app_id': shared_data['flow_data']['app_id']
                }

                # 获取收件人列表
                recipients = shared_data['flow_data'].get('email_recipients', [])
                if not recipients and hasattr(config, 'DEFAULT_EMAIL_RECIPIENTS'):
                    recipients = config.DEFAULT_EMAIL_RECIPIENTS

                    # 发送邮件
                if recipients:
                    from services.notification_service import get_notification_service
                    notification_service = get_notification_service()

                    # 发送测试邮件
                    try:
                        test_recipient = "邮箱"
                        global_logger.info(f"发送测试邮件到 {test_recipient}...")
                        test_result = notification_service.send_test_email_directly(test_recipient)
                        global_logger.info(f"测试邮件发送结果: {test_result}")
                    except Exception as e:
                        global_logger.error(f"发送测试邮件异常: {str(e)}")

                        # 发送AI增强的分析报告
                    task_id = notification_service.send_analysis_report(
                        analysis_data=analysis_data,
                        batch_info=batch_info,
                        recipients=recipients
                    )

                    global_logger.info(f"AI增强邮件发送任务已提交，任务ID: {task_id}")
                    return task_id
                else:
                    global_logger.info("未指定收件人，跳过邮件发送")
                    return None

            except Exception as e:
                global_logger.error(f"发送邮件任务失败: {str(e)}")
                global_logger.error(traceback.format_exc())
                return None

        def _ai_analyze_failures(test_results, flow_data):
            """AI分析失败原因"""
            try:
                failed_cases = [r for r in test_results if not r.get('is_success')]

                if not failed_cases:
                    return None

                global_logger.info(f"开始AI分析 {len(failed_cases)} 个失败用例")

                # 构建失败用例详情
                failure_details = []
                for case in failed_cases[:10]:  # 分析前10个失败案例
                    failure_details.append({
                        'testcase_name': case.get('testcase_name', 'Unknown'),
                        'error_message': case.get('error_message', ''),
                        'status_code': case.get('response_status', ''),
                        'request_method': case.get('request_method', ''),
                        'request_url': case.get('request_url', ''),
                        'request_body': case.get('request_body', '')[:500] if case.get('request_body') else '',
                        # 限制长度
                        'response_body': case.get('response_body', '')[:500] if case.get('response_body') else ''
                    })

                    # 计算失败统计
                total_failures = len(failed_cases)
                error_codes = {}
                error_messages = {}

                for case in failed_cases:
                    # 统计状态码
                    status_code = case.get('response_status', 'unknown')
                    error_codes[status_code] = error_codes.get(status_code, 0) + 1

                    # 统计错误消息
                    error_msg = case.get('error_message', 'unknown')
                    error_messages[error_msg] = error_messages.get(error_msg, 0) + 1

                    # 构建AI分析提示
                prompt = f"""  
        作为资深接口测试专家，请分析以下测试失败情况：  

        接口基本信息：  
        - 接口名称：{flow_data['name']}  
        - 接口地址：{flow_data['url']}  
        - 请求方法：{flow_data['method']}  
        - 总失败数：{total_failures}  

        失败统计：  
        状态码分布：{dict(list(error_codes.items())[:5])}  
        错误消息分布：{dict(list(error_messages.items())[:5])}  

        典型失败案例：  
        {json.dumps(failure_details[:5], ensure_ascii=False, indent=2)}  

        请从专业角度分析并提供JSON格式回答，包含以下字段：  
        1. "failure_analysis": [失败原因分析列表]  
        2. "key_findings": [关键发现列表]  
        3. "recommendations": [改进建议列表]  
        4. "root_cause": "根本原因分析"  
        5. "risk_assessment": "风险评估"  

        要求：  
        - 分析要专业、具体、有针对性  
        - 建议要可执行、有优先级  
        - 语言简洁明了，每条不超过50字  
        - 必须返回有效的JSON格式  
        """

                # 调用AI服务
                from services.ai_service import get_ai_service
                ai_service = get_ai_service()

                global_logger.info("正在调用AI服务进行分析...")
                response = ai_service.generate_response(prompt)

                if not response:
                    global_logger.warning("AI服务返回空响应")
                    return None

                global_logger.info(f"AI服务返回响应长度: {len(response)}")

                # 解析AI响应
                try:
                    import json
                    import re

                    # 尝试提取JSON部分
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
                        ai_result = json.loads(json_str)

                        # 验证必要字段
                        required_fields = ['failure_analysis', 'key_findings', 'recommendations']
                        for field in required_fields:
                            if field not in ai_result:
                                ai_result[field] = []

                        global_logger.info("AI分析结果解析成功")
                        return ai_result

                    else:
                        global_logger.warning("未找到有效JSON格式，使用文本解析")
                        return _parse_text_response(response)

                except json.JSONDecodeError as e:
                    global_logger.error(f"JSON解析失败: {str(e)}")
                    return _parse_text_response(response)

            except Exception as e:
                global_logger.error(f"AI分析调用失败: {str(e)}")
                global_logger.error(traceback.format_exc())
                return None

        def _parse_text_response(response):
            """解析AI文本响应为结构化数据"""
            try:
                # 简单的文本解析逻辑
                lines = response.split('\n')

                result = {
                    'failure_analysis': [],
                    'key_findings': [],
                    'recommendations': [],
                    'root_cause': '',
                    'risk_assessment': ''
                }

                current_section = None

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                        # 识别章节
                    if '失败原因' in line or 'failure_analysis' in line or '原因分析' in line:
                        current_section = 'failure_analysis'
                    elif '关键发现' in line or 'key_findings' in line or '主要发现' in line:
                        current_section = 'key_findings'
                    elif '建议' in line or 'recommendations' in line or '改进建议' in line:
                        current_section = 'recommendations'
                    elif '根本原因' in line or 'root_cause' in line or '根因' in line:
                        current_section = 'root_cause'
                    elif '风险评估' in line or 'risk_assessment' in line or '风险分析' in line:
                        current_section = 'risk_assessment'
                    elif line.startswith('-') or line.startswith('•') or line.startswith('*') or line.startswith(
                            '1.') or line.startswith('2.'):
                        # 列表项
                        item = line.lstrip('-•*123456789. ')
                        if current_section in ['failure_analysis', 'key_findings', 'recommendations'] and item:
                            result[current_section].append(item)
                    elif current_section in ['root_cause', 'risk_assessment'] and line:
                        # 单行文本
                        if result[current_section]:
                            result[current_section] += ' ' + line
                        else:
                            result[current_section] = line

                            # 如果解析结果为空，添加默认内容
                if not any(result[key] for key in ['failure_analysis', 'key_findings', 'recommendations']):
                    result['failure_analysis'] = ['AI分析了测试失败情况']
                    result['key_findings'] = ['发现多个测试用例执行失败']
                    result['recommendations'] = ['建议检查接口实现和测试数据']
                    result['root_cause'] = '需要进一步分析失败原因'
                    result['risk_assessment'] = '存在接口质量风险'

                global_logger.info("AI文本响应解析完成")
                return result

            except Exception as e:
                global_logger.error(f"文本解析失败: {str(e)}")
                # 返回基础分析结果
                return {
                    'failure_analysis': ['AI分析遇到问题，请查看详细日志'],
                    'key_findings': ['测试执行存在失败情况'],
                    'recommendations': ['建议人工检查失败原因'],
                    'root_cause': '分析过程中遇到技术问题',
                    'risk_assessment': '需要人工评估风险'
                }

        def _validate_ai_analysis(ai_analysis):
            """验证AI分析结果的完整性"""
            try:
                if not ai_analysis or not isinstance(ai_analysis, dict):
                    return False

                    # 检查必需字段
                required_fields = ['failure_analysis', 'key_findings', 'recommendations']
                for field in required_fields:
                    if field not in ai_analysis:
                        return False
                    if not isinstance(ai_analysis[field], list):
                        return False

                        # 检查是否有实际内容
                has_content = any(
                    len(ai_analysis[field]) > 0
                    for field in required_fields
                )

                return has_content

            except Exception as e:
                global_logger.error(f"AI分析结果验证失败: {str(e)}")
                return False

        def _get_fallback_analysis(test_results, flow_data):
            """获取降级分析结果"""
            try:
                failed_cases = [r for r in test_results if not r.get('is_success')]

                # 统计错误类型
                error_types = {}
                for case in failed_cases:
                    error_msg = case.get('error_message', '未知错误')
                    status_code = case.get('response_status', 'unknown')
                    error_key = f"{status_code}: {error_msg}"
                    error_types[error_key] = error_types.get(error_key, 0) + 1

                    # 构建降级分析
                fallback_analysis = {
                    'failure_analysis': [
                        f"检测到 {len(failed_cases)} 个失败用例",
                        f"主要错误类型: {', '.join(list(error_types.keys())[:3])}"
                    ],
                    'key_findings': [
                        f"失败率: {len(failed_cases) / len(test_results) * 100:.1f}%",
                        f"涉及接口: {flow_data['name']}"
                    ],
                    'recommendations': [
                        "检查接口参数验证逻辑",
                        "确认接口返回值是否符合预期",
                        "验证边界条件和异常场景处理"
                    ],
                    'root_cause': '需要进一步分析具体失败原因',
                    'risk_assessment': '存在接口质量风险，建议及时修复'
                }

                return fallback_analysis

            except Exception as e:
                global_logger.error(f"降级分析失败: {str(e)}")
                return {
                    'failure_analysis': ['分析过程中遇到问题'],
                    'key_findings': ['存在测试失败情况'],
                    'recommendations': ['建议人工检查'],
                    'root_cause': '分析异常',
                    'risk_assessment': '需要人工评估'}


                # 使用线程池并行执行

        with ThreadPoolExecutor(max_workers=2) as executor:
            # 提交任务
            excel_future = executor.submit(generate_excel_task, shared_data)
            email_future = executor.submit(send_email_task, shared_data)

            # 获取结果
            try:
                report_url = excel_future.result(timeout=30)
                global_logger.info(f"Excel任务完成: {report_url}")
            except Exception as e:
                global_logger.error(f"Excel任务失败: {str(e)}")

            try:
                email_task_id = email_future.result(timeout=30)
                global_logger.info(f"邮件任务完成: {email_task_id}")
            except Exception as e:
                global_logger.error(f"邮件任务失败: {str(e)}")

        global_logger.info("步骤4-5完成: Excel报告和邮件发送并行处理完成")

        # 准备返回结果中的收件人信息
        email_recipients = shared_data['flow_data'].get('email_recipients', [])
        if not email_recipients and hasattr(config, 'DEFAULT_EMAIL_RECIPIENTS'):
            email_recipients = config.DEFAULT_EMAIL_RECIPIENTS

            # 返回完整结果
        response = format.resp_format_success.copy()
        response["message"] = "完整AI测试流程执行成功"
        response["data"] = {
            "flow_summary": {
                "interface_name": flow_data['name'],
                "batch_id": batch_id,
                "batch_name": flow_data['batch_name'],
                "testcases_generated": len(testcase_ids),
                "testcases_executed": len(testcase_ids),
                "report_url": report_url
            },
            "generation_result": {
                "testcase_ids": testcase_ids,
                "total_generated": generate_result['data']['total_generated'],
                "total_saved": generate_result['data']['total_saved']
            },
            "execution_result": {
                "batch_id": batch_id,
                "total_cases": batch_result['data']['total_cases']
            },
            "test_results": test_results,
            "report_url": report_url,
            "email_notification": {
                "sent": email_task_id is not None,
                "recipients": email_recipients,  #使用正确的变量
                "task_id": email_task_id
            }
        }

        global_logger.info("=== 完整AI测试流程执行完成 ===")
        return response

    except Exception as e:
        global_logger.error(f"完整AI测试流程异常: {str(e)}")
        global_logger.error(f"异常堆栈: {traceback.format_exc()}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


def get_test_results(batch_id):
    """获取测试结果，直接从数据库获取"""
    global_logger.info(f"获取测试批次 {batch_id} 的测试结果...")

    conn = mysql_pool.connection()
    cursor = conn.cursor()

    try:
        # 查询测试结果
        result_sql = """  
            SELECT r.id, r.testcase_id, t.name as testcase_name,   
                   r.request_url, r.request_method, r.response_status,   
                   r.is_success, r.execution_time, r.execute_time,  
                   r.error_message, r.request_headers, r.request_body,  
                   r.response_headers, r.response_body  
            FROM api_result r  
            LEFT JOIN api_testcase t ON r.testcase_id = t.id  
            WHERE r.batch_id = %s  
            ORDER BY r.execute_time  
        """
        global_logger.info(f'执行SQL: {result_sql}, 参数: [{batch_id}]')
        cursor.execute(result_sql, [batch_id])
        results = cursor.fetchall()

        # 转换结果格式以匹配API返回的格式
        test_results = []
        for result in results:
            # 将数据库结果转换为与API返回相同的格式
            result_item = {
                'id': result['id'],
                'testcase_id': result['testcase_id'],
                'testcase_name': result['testcase_name'],
                'request_url': result['request_url'],
                'request_method': result['request_method'],
                'response_status': result['response_status'],
                'execution_time': result['execution_time'],
                'execute_time': result['execute_time'],
                'error_message': result['error_message'],
                # 添加与API返回格式匹配的字段
                'status': 'PASS' if result['is_success'] else 'FAIL',
            }

            # 处理JSON字段
            try:
                if result['request_headers']:
                    result_item['request_headers'] = json.loads(result['request_headers'])
                if result['request_body']:
                    result_item['request_body'] = json.loads(result['request_body'])
                if result['response_headers']:
                    result_item['response_headers'] = json.loads(result['response_headers'])
                if result['response_body']:
                    result_item['response_body'] = json.loads(result['response_body'])
            except:
                global_logger.warning(f"解析JSON字段失败，测试结果ID: {result['id']}")

            test_results.append(result_item)

        global_logger.info(f"获取到 {len(test_results)} 个测试结果")

        return test_results
    except Exception as e:
        global_logger.error(f"获取测试结果异常: {str(e)}")
        global_logger.error(traceback.format_exc())
        return []
    finally:
        cursor.close()
        conn.close()

def is_batch_completed(batch_id):
    """检查批次是否已经完成"""
    conn = mysql_pool.connection()
    cursor = conn.cursor()
    try:
        sql = "SELECT status FROM api_test_batch WHERE id = %s"
        cursor.execute(sql, [batch_id])
        result = cursor.fetchone()

        # 添加调试日志
        global_logger.info(f"批次 {batch_id} 查询结果: {result}")
        global_logger.info(f"结果类型: {type(result)}")

        if result:
            # 根据不同的返回格式处理
            if isinstance(result, dict):
                status = result.get('status')
            elif isinstance(result, tuple):
                status = result[0]
            else:
                status = result

            global_logger.info(f"批次 {batch_id} 状态: {status}")
            return status == 2
        else:
            global_logger.warning(f"未找到批次 {batch_id}")
            return False

    except Exception as e:
        global_logger.error(f"检查批次状态出错: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()
def wait_for_batch_completion(batch_id):
    """等待批次执行完成"""
    max_wait_time = 300
    wait_interval = 3
    waited_time = 0

    while waited_time < max_wait_time:
        try:
            conn = mysql_pool.connection()
            cursor = conn.cursor()

            # 检查批次状态
            check_sql = """  
            SELECT status, total_cases, passed_cases, failed_cases   
            FROM api_test_batch   
            WHERE id = %s  
            """
            cursor.execute(check_sql, [batch_id])
            batch_info = cursor.fetchone()

            if batch_info:
                status = batch_info.get('status', '')
                total = batch_info.get('total_cases', 0)
                passed = batch_info.get('passed_cases', 0)
                failed = batch_info.get('failed_cases', 0)
                completed = passed + failed

                global_logger.info(f"批次状态: {status}, 进度: {completed}/{total}, 已等待: {waited_time}s")

                # 检查是否完成
                if status == 'completed' or completed >= total:
                    global_logger.info(f"批次执行完成! 状态: {status}, 通过: {passed}, 失败: {failed}")
                    cursor.close()
                    conn.close()
                    return True

            cursor.close()
            conn.close()

        except Exception as e:
            global_logger.error(f"检查批次状态时出错: {str(e)}")

        time.sleep(wait_interval)
        waited_time += wait_interval

    global_logger.warning(f"等待批次完成超时({max_wait_time}s)")
    return False


def get_or_create_interface(flow_data):
    """获取或创建接口记录"""
    try:
        # 查询现有接口 - 使用 fetch_one
        query = """  
            SELECT id FROM api_interface   
            WHERE app_id = %s AND url = %s AND method = %s  
        """
        result = fetch_one(query, (
            flow_data['app_id'],
            flow_data['url'],
            flow_data['method']
        ))

        # 如果找到现有接口，返回ID
        if result:
            global_logger.info(f"找到现有接口: {result['id']}")
            return result['id']

            # 创建新接口
        global_logger.info("创建新接口记录...")
        interface_id = generate_id()
        insert_query = """  
            INSERT INTO api_interface (id, app_id, name, url, method, headers, params, create_time)  
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)  
        """
        execute_query(insert_query, (
            interface_id,
            flow_data['app_id'],
            flow_data['name'],
            flow_data['url'],
            flow_data['method'],
            json.dumps(flow_data.get('headers', {})),
            json.dumps(flow_data.get('params', {})),
            int(time.time() * 1000)
        ))

        global_logger.info(f"新接口创建成功: {interface_id}")
        return interface_id

    except Exception as e:
        global_logger.error(f"获取或创建接口失败: {str(e)}")
        import traceback
        global_logger.error(f"详细错误: {traceback.format_exc()}")

        # 降级到原来的逻辑
        fallback_id = flow_data.get('app_id', 'unknown') + '_default_if'
        global_logger.warning(f"使用降级ID: {fallback_id}")
        return fallback_id