from flask import Blueprint, request
from flask import current_app as app
import pymysql.cursors
import json
import time
import uuid
from dbutils.pooled_db import PooledDB
from configs import config, format
from app import celery, global_logger

# 创建蓝图
testcase = Blueprint('testcase', __name__)

# 获取数据库连接池
db_pool = PooledDB(
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


@testcase.route('/api/testcase/add', methods=['POST'])
def add_testcase():
    global_logger.info('访问添加测试用例API')
    data = request.json


    # 检查必要参数
    required_fields = ['interface_id', 'app_id', 'name', 'request_url',
                       'request_method', 'assertions', 'creator_id', 'creator_name']
    for field in required_fields:
        if field not in data or not data[field]:
            response = format.resp_format_failed.copy()
            response["message"] = f"缺少必要参数: {field}"
            return response

            # 生成唯一ID
    testcase_id = str(uuid.uuid4()).replace('-', '')

    # 处理JSON字段
    request_headers = json.dumps(data.get('request_headers', {})) if data.get('request_headers') else None
    request_params = json.dumps(data.get('request_params', {})) if data.get('request_params') else None
    assertions = json.dumps(data.get('assertions', [])) if data.get('assertions') else '[]'

    # 设置时间戳
    current_time = int(time.time())

    try:
        # 构建插入数据
        conn = db_pool.connection()
        cursor = conn.cursor()

        sql = """  
        INSERT INTO api_testcase (  
            id, interface_id, app_id, name, priority, request_url, request_method,   
            request_headers, request_params, expected_status, assertions, pre_script,   
            post_script, description, status, creator_id, creator_name, create_time, update_time  
        ) VALUES (  
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s  
        )  
        """

        params = (
            testcase_id,
            data['interface_id'],
            data['app_id'],
            data['name'],
            data.get('priority', 2),
            data['request_url'],
            data['request_method'],
            request_headers,
            request_params,
            data.get('expected_status'),
            assertions,
            data.get('pre_script'),
            data.get('post_script'),
            data.get('description', ''),
            data.get('status', 1),
            data['creator_id'],
            data['creator_name'],
            current_time,
            current_time
        )

        cursor.execute(sql, params)
        conn.commit()
        cursor.close()
        conn.close()
        response = format.resp_format_success.copy()
        response["message"] = "测试用例添加成功"
        response["data"] = {"id": testcase_id}
        return response

    except Exception as e:
        global_logger.error(f"添加测试用例异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


@testcase.route('/api/testcase/list', methods=['GET'])
def get_testcase_list():
    try:
        global_logger.info('访问测试用例列表API')
        response = format.resp_format_success.copy()

        # 获取查询参数
        interface_id = request.args.get('interface_id')
        app_id = request.args.get('app_id')
        priority = request.args.get('priority')
        page = int(request.args.get('page', 1))
        size = int(request.args.get('size', 10))

        # 计算偏移量
        offset = (page - 1) * size

        # 连接数据库
        conn = db_pool.connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 构建查询条件
        query_conditions = []
        query_params = []

        if interface_id:
            query_conditions.append("interface_id = %s")
            query_params.append(interface_id)

        if app_id:
            query_conditions.append("app_id = %s")
            query_params.append(app_id)

        if priority is not None:
            query_conditions.append("priority = %s")
            query_params.append(int(priority))

            # 构建SQL语句
        where_clause = " WHERE " + " AND ".join(query_conditions) if query_conditions else ""

        count_sql = f"SELECT COUNT(*) as total FROM api_testcase{where_clause}"
        query_sql = f"""  
            SELECT id, interface_id, app_id, name, priority, request_url, request_method,   
                   expected_status, status, creator_id, creator_name,   
                   create_time, update_time, description  
            FROM api_testcase  
            {where_clause}  
            ORDER BY update_time DESC, create_time DESC  
            LIMIT %s, %s  
        """

        # 获取总数
        cursor.execute(count_sql, query_params)
        total = cursor.fetchone()['total']

        # 获取数据列表
        query_params.extend([offset, size])
        cursor.execute(query_sql, query_params)
        results = cursor.fetchall()

        # 处理结果
        for result in results:
            result['create_time'] = int(result['create_time'])
            result['update_time'] = int(result['update_time'])

        cursor.close()
        conn.close()

        response["message"] = "获取测试用例列表成功"
        response["data"] = results
        response["total"] = total
        return response

    except Exception as e:
        global_logger.error(f"获取测试用例列表异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


@testcase.route('/api/testcase/detail', methods=['GET'])
def get_testcase_detail():
    try:
        global_logger.info('访问测试用例详情API')
        response = format.resp_format_success.copy()

        # 获取查询参数
        testcase_id = request.args.get('id')

        if not testcase_id:
            response = format.resp_format_failed.copy()
            response["message"] = "缺少ID参数"
            return response

            # 连接数据库
        conn = db_pool.connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 查询数据
        sql = """  
            SELECT * FROM api_testcase WHERE id = %s  
        """

        cursor.execute(sql, (testcase_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if not result:
            response = format.resp_format_failed.copy()
            response["message"] = "测试用例不存在"
            return response

            # 转换JSON字段
        if result['request_headers']:
            result['request_headers'] = json.loads(result['request_headers'])
        else:
            result['request_headers'] = {}

        if result['request_params']:
            result['request_params'] = json.loads(result['request_params'])
        else:
            result['request_params'] = {}

        if result['assertions']:
            result['assertions'] = json.loads(result['assertions'])
        else:
            result['assertions'] = []

            # 转换时间戳
        result['create_time'] = int(result['create_time'])
        result['update_time'] = int(result['update_time'])

        response["message"] = "获取测试用例详情成功"
        response["data"] = result
        return response

    except Exception as e:
        global_logger.error(f"获取测试用例详情异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


@testcase.route('/api/testcase/update', methods=['POST'])
def update_testcase():
    try:
        global_logger.info('访问更新测试用例API')
        response = format.resp_format_success.copy()

        data = request.json

        # 检查必要参数
        if 'id' not in data or not data['id']:
            response = format.resp_format_failed.copy()
            response["message"] = "缺少ID参数"
            return response

            # 准备更新的字段
        update_fields = []
        update_params = []

        # 可更新的字段列表
        updatable_fields = [
            'name', 'priority', 'request_url', 'request_method',
            'expected_status', 'pre_script', 'post_script',
            'description', 'status'
        ]

        # 处理普通字段
        for field in updatable_fields:
            if field in data and data[field] is not None:
                update_fields.append(f"{field} = %s")
                update_params.append(data[field])

                # 处理JSON字段
        if 'request_headers' in data:
            update_fields.append("request_headers = %s")
            update_params.append(json.dumps(data['request_headers']))

        if 'request_params' in data:
            update_fields.append("request_params = %s")
            update_params.append(json.dumps(data['request_params']))

        if 'assertions' in data:
            update_fields.append("assertions = %s")
            update_params.append(json.dumps(data['assertions']))

            # 添加更新时间
        update_fields.append("update_time = %s")
        current_time = int(time.time())
        update_params.append(current_time)

        # 如果没有需要更新的字段
        if not update_fields:
            response = format.resp_format_failed.copy()
            response["message"] = "没有提供需要更新的字段"
            return response

            # 构建SQL语句
        update_sql = f"""  
            UPDATE api_testcase   
            SET {', '.join(update_fields)}  
            WHERE id = %s  
        """
        update_params.append(data['id'])

        # 执行更新
        conn = db_pool.connection()
        cursor = conn.cursor()
        cursor.execute(update_sql, update_params)
        affected_rows = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        if affected_rows == 0:
            response = format.resp_format_failed.copy()
            response["message"] = "测试用例不存在"
            return response

        response["message"] = "更新测试用例成功"
        response["data"] = {"affected_rows": affected_rows}
        return response

    except Exception as e:
        global_logger.error(f"更新测试用例异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


@testcase.route('/api/testcase/delete', methods=['POST'])
def delete_testcase():
    try:
        global_logger.info('访问删除测试用例API')
        response = format.resp_format_success.copy()

        data = request.json

        # 检查必要参数
        if 'id' not in data or not data['id']:
            response = format.resp_format_failed.copy()
            response["message"] = "缺少ID参数"
            return response

            # 执行删除
        conn = db_pool.connection()
        cursor = conn.cursor()

        sql = "DELETE FROM api_testcase WHERE id = %s"
        cursor.execute(sql, (data['id'],))
        affected_rows = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        if affected_rows == 0:
            response = format.resp_format_failed.copy()
            response["message"] = "测试用例不存在"
            return response

        response["message"] = "删除测试用例成功"
        response["data"] = {"affected_rows": affected_rows}
        return response

    except Exception as e:
        global_logger.error(f"删除测试用例异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response


@testcase.route('/api/testcase/copy', methods=['POST'])
def copy_testcase():
    try:
        global_logger.info('访问复制测试用例API')
        response = format.resp_format_success.copy()

        data = request.json

        # 检查必要参数
        if 'id' not in data or not data['id']:
            response = format.resp_format_failed.copy()
            response["message"] = "缺少源用例ID参数"
            return response

            # 获取源测试用例
        conn = db_pool.connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        sql = "SELECT * FROM api_testcase WHERE id = %s"
        cursor.execute(sql, (data['id'],))
        source_testcase = cursor.fetchone()

        if not source_testcase:
            cursor.close()
            conn.close()
            response = format.resp_format_failed.copy()
            response["message"] = "源测试用例不存在"
            return response

            # 生成新ID
        new_id = str(uuid.uuid4()).replace('-', '')

        # 设置新名称
        new_name = data.get('name', f"复制 - {source_testcase['name']}")

        # 设置时间戳
        current_time = int(time.time())

        # 执行复制
        insert_sql = """  
        INSERT INTO api_testcase (  
            id, interface_id, app_id, name, priority, request_url, request_method,   
            request_headers, request_params, expected_status, assertions, pre_script,   
            post_script, description, status, creator_id, creator_name, create_time, update_time  
        ) VALUES (  
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s  
        )  
        """

        cursor.execute(insert_sql, (
            new_id,
            source_testcase['interface_id'],
            source_testcase['app_id'],
            new_name,
            source_testcase['priority'],
            source_testcase['request_url'],
            source_testcase['request_method'],
            source_testcase['request_headers'],
            source_testcase['request_params'],
            source_testcase['expected_status'],
            source_testcase['assertions'],
            source_testcase['pre_script'],
            source_testcase['post_script'],
            source_testcase['description'],
            source_testcase['status'],
            source_testcase['creator_id'],
            source_testcase['creator_name'],
            current_time,
            current_time
        ))

        conn.commit()
        cursor.close()
        conn.close()

        response["message"] = "复制测试用例成功"
        response["data"] = {"id": new_id}
        return response

    except Exception as e:
        global_logger.error(f"复制测试用例异常: {str(e)}")
        response = format.resp_format_failed.copy()
        response["message"] = f"系统异常: {str(e)}"
        return response