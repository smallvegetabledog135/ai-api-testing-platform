#apis/interface.py

from flask import Blueprint
from flask import current_app as app
from dbutils.pooled_db import PooledDB
from configs import config,format
from app import celery,global_logger

from flask import request
import pymysql.cursors
import json
import time

#创建接口蓝图
interface=Blueprint('interface',__name__)

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

#获取接口列表
@interface.route("/api/interface/list",methods=['GET'])
def list_interface():
    global_logger.info('访问接口列表API')
    app_id=request.args.get('app_id')
    category = request.args.get('category')
    status = request.args.get('status')
    global_logger.info(f'请求参数: app_id={app_id}, category={category}, status={status}')
    # 获取数据库连接
    conn=mysql_pool.connection()
    cursor=conn.cursor()

    #构建查询条件
    conditions=[]
    params=[]

    if app_id:
        conditions.append("app_id=%s")
        params.append(app_id)

    if category:
        conditions.append("category=%s")
        params.append(category)

    if status is not None:
        conditions.append("status=%s")
        params.append(int(status))
#构建where子句
    where_clause="WHERE " + "AND".join(conditions) if conditions else""
    #构建语句
    sql=f"""
    SELECT id,app_id,name,url,method,category,status,create_time
    FROM api_interface
    {where_clause}
    ORDER BY create_time DESC
    """

    global_logger.info(f'执行SQL: {sql}')

    #执行语句
    cursor.execute(sql,params)
    result=cursor.fetchall()

    global_logger.info(f'查询结果数量: {len(result)}')
    #关闭连接
    cursor.close()
    conn.close()

    # 返回结果
    response = format.resp_format_success.copy()
    response["data"] = result
    response["total"] = len(result)
    return response

#获取接口详情
@interface.route("/api/interface/detail",methods=['get'])
def get_interface_detail():
    global_logger.info('获取接口详情API')
    interface_id=request.args.get('id')
    global_logger.info(f'请求参数: id={interface_id}')

    if not interface_id:
        global_logger.warning('请求缺少接口ID参数')
        response = format.resp_format_failed.copy()
        response["message"] = "缺少接口ID"
        return response
    try:
        # 获取数据库连接
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        # 查询接口详情
        sql = """  
            SELECT id, app_id, name, url, method, headers, params,   
                category, description, status, create_time, update_time   
            FROM api_interface   
            WHERE id = %s  
            """
        global_logger.info(f'执行SQL: {sql}')
        cursor.execute(sql, [interface_id])
        interface_data = cursor.fetchone()

        # 接口不存在
        if not interface_data:
            global_logger.warning(f'接口ID {interface_id} 不存在')
            cursor.close()
            conn.close()
            response = format.resp_format_failed.copy()
            response["message"] = "接口不存在"
            return response

        global_logger.info(f'查询到接口: {interface_data["name"]} (ID: {interface_data["id"]})')

        # 解析json字段
        if interface_data['headers']:
            try:
                global_logger.debug('解析headers JSON字段')
                interface_data['headers'] = json.loads(interface_data['headers'])
            except Exception as e:
                global_logger.error(f'解析headers JSON失败: {str(e)}')
                interface_data['headers'] = {}
        else:
            interface_data['headers'] = {}

        if interface_data['params']:
            try:
                global_logger.debug('解析params JSON字段')
                interface_data['params'] = json.loads(interface_data['params'])
            except:
                global_logger.error(f'解析headers JSON失败: {str(e)}')
                interface_data['params'] = {}
        else:
            interface_data['params'] = {}

        # 关闭连接
        cursor.close()
        conn.close()
        global_logger.info('接口详情查询成功')

        # 返回结果
        response = format.resp_format_success.copy()
        response["data"] = interface_data
        response["total"] = 1
        return response
    except Exception as e:
        global_logger.error(f'查询接口详情异常: {str(e)}', exc_info=True)
        response = format.resp_format_failed.copy()
        response["message"] = f"查询失败: {str(e)}"
        return response


    #新增接口
@interface.route("/api/interface/add",methods=['POST'])
def add_interface():
    global_logger.info('访问新增接口API')
    #获取请求数据
    data=request.get_json()
    global_logger.info(f'请求数据: {data}')
    #检查必填字段
    required_fields=['app_id','name','url','method']
    for field in required_fields:
        if field not in data or not data[field]:
            global_logger.warning(f'缺少必填字段: {field}')
            response = format.resp_format_failed.copy()
            response["message"]="缺少必填字段：{field}"
            response["total"]=0
            return response
    try:
        # 获取数据库连接
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        # 准备数据
        now = int(time.time())
        headers = json.dumps(data.get('headers', {}))
        params = json.dumps(data.get('params', {}))

        global_logger.debug(f'序列化headers: {headers}')
        global_logger.debug(f'序列化params: {params}')

        # 构建SQL语句
        sql = """  
            INSERT INTO api_interface (  
                app_id, name, url, method, headers, params,   
                category, description, status, create_time, update_time,  
                creator_id, creator_name  
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)  
            """

        global_logger.info(f'执行SQL: {sql}')

        creator_id = data.get('creator_id', 'system')
        creator_name = data.get('creator_name', '系统用户')

    #执行插入

        cursor.execute(sql, [
            data['app_id'],
            data['name'],
            data['url'],
            data['method'],
            headers,
            params,
            data.get('category', '默认分类'),
            data.get('description', ''),
            data.get('status', 1),  # 默认启用
            now,
            now,
            creator_id,
            creator_name
        ])
        #global_logger.debug(f'SQL参数: {sql_params}')
        #获取新输入的ID
        interface_id=cursor.lastrowid
        global_logger.info(f'接口创建成功，ID: {interface_id}')
        #提交事务
        conn.commit()

        #关闭连接
        cursor.close()
        conn.close()

        response=format.resp_format_success.copy()
        response["data"]={'id':interface_id}
        response["total"]=1
        return response

    except Exception as e:
        global_logger.error(f'创建接口异常: {str(e)}', exc_info=True)
        #回滚事务
        conn.rollback()

        #关闭连接
        cursor.close()
        conn.close()

        response = format.resp_format_failed.copy()
        response["message"] = {"创建接口失败：{str(e)}"}
        response["total"] = 0
        return response


# 更新接口
@interface.route("/api/interface/update", methods=['POST'])
def update_interface():
    global_logger.info('访问更新接口API')
    # 获取请求数据
    data = request.get_json()
    global_logger.info(f'请求数据: {data}')

    # 检查接口ID
    interface_id = data.get('id')
    if not interface_id:
        global_logger.warning('缺少接口ID')
        response=format.resp_format_failed
        response["message"]="缺失接口ID"
        return response
    try:
        # 获取数据库连接
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        # 检查接口是否存在
        global_logger.info(f'检查接口ID {interface_id} 是否存在')
        cursor.execute("SELECT id FROM api_interface WHERE id = %s", [interface_id])
        if not cursor.fetchone():
            global_logger.warning(f'接口ID {interface_id} 不存在')
            cursor.close()
            conn.close()
            response = format.resp_format_failed
            response["message"] = "接口不存在"
            return response

            # 构建更新语句
        update_fields = []
        params = []

        # 可更新字段列表
        field_mapping = {
            'name': 'name',
            'url': 'url',
            'method': 'method',
            'category': 'category',
            'description': 'description',
            'status': 'status',
            'app_id': 'app_id'
        }

        # 添加普通字段
        for key, field in field_mapping.items():
            if key in data:
                update_fields.append(f"{field} = %s")
                params.append(data[key])
                global_logger.debug(f'添加更新字段: {field} = {data[key]}')
                # 处理JSON字段
        if 'headers' in data:
            update_fields.append("headers = %s")
            params.append(json.dumps(data['headers']))
            global_logger.debug(f'添加headers更新: {json.dumps(data["headers"])}')

        if 'params' in data:
            update_fields.append("params = %s")
            params.append(json.dumps(data['params']))
            global_logger.debug(f'添加params更新: {json.dumps(data["params"])}')

            # 如果没有要更新的字段
        if not update_fields:
            global_logger.warning('没有要更新的字段')
            cursor.close()
            conn.close()
            response = format.resp_format_failed
            response["message"] = "没有要更新的字段"
            return response

            # 添加更新时间
        update_fields.append("update_time = %s")
        params.append(int(time.time()))
        global_logger.debug(f'添加更新时间: {int(time.time())}')

        # 添加WHERE条件参数
        params.append(interface_id)

        # 构建SQL语句
        sql = f"UPDATE api_interface SET {', '.join(update_fields)} WHERE id = %s"
        global_logger.info(f'执行SQL: {sql}')
        global_logger.debug(f'SQL参数: {params}')


    # 执行更新

        cursor.execute(sql, params)
        affected_rows = cursor.rowcount
        global_logger.info(f'更新成功，影响行数: {affected_rows}')
        conn.commit()

        cursor.close()
        conn.close()
        response = format.resp_format_success
        return response

    except Exception as e:
        global_logger.error(f'更新接口异常: {str(e)}', exc_info=True)

        conn.rollback()

        cursor.close()
        conn.close()
        response = format.resp_format_failed
        response["message"] = "更新接口失败：{str(e)}"
        return response

    # 删除接口


@interface.route("/api/interface/delete", methods=['POST'])
def delete_interface():
    global_logger.info('访问删除接口API')
    # 获取请求数据
    data = request.get_json()
    global_logger.info(f'请求数据: {data}')

    # 检查接口ID
    interface_id = data.get('id')
    if not interface_id:
        global_logger.warning('缺少接口ID')
        response = format.resp_format_failed.copy()
        response["message"] = "缺少接口ID"
        return response
    try:
        # 获取数据库连接
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        # 检查接口是否存在
        global_logger.info(f'检查接口ID {interface_id} 是否存在')
        cursor.execute("SELECT id FROM api_interface WHERE id = %s", [interface_id])
        if not cursor.fetchone():
            global_logger.warning(f'接口ID {interface_id} 不存在')
            cursor.close()
            conn.close()
            response = format.resp_format_failed
            response["message"] = "接口不存在"
            return response

            # 检查是否有关联的测试用例
        global_logger.info(f'检查接口ID {interface_id} 是否有关联的测试用例')
        cursor.execute("SELECT COUNT(*) as count FROM api_testcase WHERE interface_id = %s", [interface_id])
        result = cursor.fetchone()
        if result and result['count'] > 0:
            global_logger.warning(f'接口ID {interface_id} 关联了 {result["count"]} 个测试用例，无法删除')
            cursor.close()
            conn.close()
            response = format.resp_format_failed
            response["message"] = f"该接口关联了{result['count']}个测试用例，无法删除"
            return response

        # 执行删除
        global_logger.info(f'删除接口ID {interface_id}')
        cursor.execute("DELETE FROM api_interface WHERE id = %s", [interface_id])
        affected_rows = cursor.rowcount
        global_logger.info(f'删除成功，影响行数: {affected_rows}')
        conn.commit()

        cursor.close()
        conn.close()
        response = format.resp_format_success.copy()
        return response

    except Exception as e:
        global_logger.error(f'删除接口异常: {str(e)}', exc_info=True)
        conn.rollback()

        cursor.close()
        conn.close()
        response = format.resp_format_failed
        response["message"] = "删除接口失败: {str(e)}"
        return response

    # 获取接口分类列表
@interface.route("/api/interface/categories", methods=['GET'])
def get_categories():
    global_logger.info('访问接口分类列表API')

    app_id = request.args.get('app_id')
    global_logger.info(f'请求参数: app_id={app_id}')
    try:
        # 获取数据库连接
        conn = mysql_pool.connection()
        cursor = conn.cursor()

        # 构建查询条件
        sql = "SELECT DISTINCT category FROM api_interface"
        params = []

        if app_id:
            sql += " WHERE app_id = %s"
            params.append(app_id)

        global_logger.info(f'执行SQL: {sql}')
        global_logger.debug(f'SQL参数: {params}')
        # 执行查询
        cursor.execute(sql, params)
        results = cursor.fetchall()

        # 处理结果
        categories = [row['category'] for row in results if row['category']]
        global_logger.info(f'查询到 {len(categories)} 个分类')
        global_logger.debug(f'分类列表: {categories}')
        # 关闭连接
        cursor.close()
        conn.close()

        # 返回结果
        response = format.resp_format_success.copy()
        response["data"] = categories
        response["total"] = len(categories)
        return response

    except Exception as e:
        global_logger.error(f'查询分类列表异常: {str(e)}', exc_info=True)

        # 关闭连接
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

        response = format.resp_format_failed.copy()  # 使用copy()创建副本
        response["message"] = f"查询分类列表失败: {str(e)}"
        return response













