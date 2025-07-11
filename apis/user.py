# !/usr/bin/env python3
# -*- coding:utf-8 -*-
from flask import request, jsonify
import json
import time
import re
from flask import Blueprint

app_user = Blueprint("app_user", __name__)

# 模拟用户数据库
USERS_DB = {
    "admin": {
        "password": "admin123",
        "role": "admin",
        "status": "active",
        "login_attempts": 0,
        "locked_until": None
    },
    "testuser": {
        "password": "password123",
        "role": "user",
        "status": "active",
        "login_attempts": 0,
        "locked_until": None
    },
    "user001": {
        "password": "user123456",
        "role": "user",
        "status": "active",
        "login_attempts": 0,
        "locked_until": None
    },
    "lockeduser": {
        "password": "password123",
        "role": "user",
        "status": "locked",
        "login_attempts": 5,
        "locked_until": time.time() + 3600  # 锁定1小时
    },
    "expireduser": {
        "password": "password123",
        "role": "user",
        "status": "expired",
        "login_attempts": 0,
        "locked_until": None
    }
}


def validate_input(username, password):
    """输入参数验证"""
    errors = []

    # 检查必填字段
    if not username:
        errors.append("用户名不能为空")
    if not password:
        errors.append("密码不能为空")

    if not username and not password:
        return ["用户名和密码都不能为空"]

        # 长度验证
    if username and len(username) < 2:
        errors.append("用户名长度不能少于2个字符")
    if username and len(username) > 50:
        errors.append("用户名长度不能超过50个字符")

    if password and len(password) < 6:
        errors.append("密码长度不能少于6个字符")
    if password and len(password) > 100:
        errors.append("密码长度不能超过100个字符")

        # 安全检查 - SQL注入
    if username and any(
            keyword in username.lower() for keyword in ['drop', 'delete', 'insert', 'update', 'select', '--', ';']):
        errors.append("用户名包含非法字符")

        # 安全检查 - XSS
    if username and any(tag in username.lower() for tag in ['<script', '<iframe', '<object', 'javascript:']):
        errors.append("用户名包含非法脚本")

    return errors


def check_user_status(username):
    """检查用户状态"""
    if username not in USERS_DB:
        return False, "用户不存在"

    user = USERS_DB[username]

    # 检查账户是否锁定
    if user["status"] == "locked":
        if user["locked_until"] and time.time() < user["locked_until"]:
            return False, "账户已被锁定，请稍后再试"
        else:
            # 锁定时间已过，解锁账户
            user["status"] = "active"
            user["login_attempts"] = 0
            user["locked_until"] = None

            # 检查账户是否过期
    if user["status"] == "expired":
        return False, "账户已过期，请联系管理员"

    return True, "账户状态正常"


def handle_login_attempt(username, success):
    """处理登录尝试"""
    if username in USERS_DB:
        user = USERS_DB[username]

        if success:
            # 登录成功，重置失败次数
            user["login_attempts"] = 0
        else:
            # 登录失败，增加失败次数
            user["login_attempts"] += 1

            # 超过5次失败，锁定账户30分钟
            if user["login_attempts"] >= 5:
                user["status"] = "locked"
                user["locked_until"] = time.time() + 1800  # 30分钟


@app_user.route("/api/user/login", methods=['POST'])
def login():
    try:
        js_data = request.get_json()
        if not js_data:
            return jsonify({"code": 400, "message": "请求数据不能为空"}), 400

        username = js_data.get('username', '').strip()
        password = js_data.get('password', '').strip()

        # 严格验证空值
        if not username:
            return jsonify({"code": 400, "message": "用户名不能为空"}), 400
        if not password:
            return jsonify({"code": 400, "message": "密码不能为空"}), 400

            # 长度验证
        if len(username) > 50:
            return jsonify({"code": 400, "message": "用户名长度超出限制"}), 400
        if len(password) > 100:
            return jsonify({"code": 400, "message": "密码长度超出限制"}), 400

            # 业务逻辑验证
        if username in USERS_DB and USERS_DB[username]["password"] == password:
            return jsonify({"code": 200, "data": {"token": f"{username}-token"}}), 200
        else:
            return jsonify({"code": 400, "message": "用户名或密码错误"}), 400

    except Exception as e:
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500



@app_user.route("/api/user/info", methods=['GET'])
def info():
    """获取用户信息"""
    try:
        token = request.args.get('token')

        if not token:
            return jsonify({"code": 400, "message": "Token不能为空"}), 400

            # 简单的token验证（实际项目中应该使用JWT等）
        if token.endswith('-token-' + str(int(time.time()))):
            username = token.split('-token-')[0]

            if username in USERS_DB:
                user = USERS_DB[username]
                return jsonify({
                    "code": 200,
                    "data": {
                        "roles": [user["role"]],
                        "introduction": f"I am a {user['role']}",
                        "avatar": "https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif",
                        "name": username,
                        "status": user["status"]
                    }
                }), 200

        return jsonify({"code": 401, "message": "Token无效或已过期"}), 401

    except Exception as e:
        print(f"获取用户信息异常: {str(e)}")
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500

    # 新增：重置用户锁定状态的接口（用于测试）


@app_user.route("/api/user/reset_lock", methods=['POST'])
def reset_lock():
    """重置用户锁定状态（仅用于测试）"""
    try:
        js_data = request.get_json()
        username = js_data.get('username')

        if username in USERS_DB:
            USERS_DB[username]["status"] = "active"
            USERS_DB[username]["login_attempts"] = 0
            USERS_DB[username]["locked_until"] = None

            return jsonify({
                "code": 200,
                "message": f"用户 {username} 锁定状态已重置"
            }), 200
        else:
            return jsonify({"code": 400, "message": "用户不存在"}), 400

    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500