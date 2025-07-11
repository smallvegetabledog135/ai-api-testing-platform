# services/ai_service.py
import json
import traceback

import requests
from datetime import datetime
from app import global_logger
from configs.ai_config import AI_CONFIG, CONFIG_VALID

import re



class AIService:

    def __init__(self):
        #  详细调试信息
        global_logger.info(" 初始化AI服务...")
        global_logger.info(f" CONFIG_VALID: {CONFIG_VALID}")
        global_logger.info(f" API Key前缀: {AI_CONFIG.api_key[:8]}...")

        self.config = AI_CONFIG
        self.use_mock = not CONFIG_VALID

        global_logger.info(f" 初始模式: {'真实API' if not self.use_mock else '模拟模式'}")

        self._test_connection()

        #  最终确认
        final_mode = "真实API" if not self.use_mock else "模拟模式"
        global_logger.info(f" AI服务启动完成，使用: {final_mode}")

    def _test_connection(self):
        """测试AI API连接"""
        if not CONFIG_VALID:
            global_logger.warning("AI配置无效，使用模拟模式")
            self.use_mock = True
            return

        try:
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }

            # 发送简单的测试请求
            test_payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10
            }

            response = requests.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=test_payload,
                timeout=10
            )

            if response.status_code == 200:
                global_logger.info(" 硅基流动AI API连接成功")
                self.use_mock = False
            else:
                global_logger.warning(f" AI API连接失败: {response.status_code}")
                global_logger.warning(f"错误详情: {response.text}")
                self.use_mock = True

        except Exception as e:
            global_logger.warning(f" AI API连接异常: {e}")
            self.use_mock = True

    def _parse_ai_response(self, response_text, interface_data):
        """解析AI响应，解析失败直接跳过"""
        try:
            global_logger.info(f"AI返回内容长度: {len(response_text)}")

            # 基础清理
            cleaned_text = self._clean_json_response(response_text)

            # 尝试直接解析
            try:
                testcases = json.loads(cleaned_text)
                global_logger.info("JSON解析成功")
                valid_testcases = self._validate_and_fix_testcases(testcases, interface_data)
                global_logger.info(f"成功处理 {len(valid_testcases)} 个测试用例")
                return valid_testcases

            except json.JSONDecodeError as e:
                global_logger.warning(f"JSON解析失败，跳过本次生成: {e}")
                global_logger.info("解析失败，返回空列表")
                return []

        except Exception as e:
            global_logger.error(f"解析AI响应时发生错误，跳过: {e}")
            return []

    def _validate_and_fix_testcases(self, testcases, interface_data):
        """验证和修复测试用例，跳过无效的"""
        if not isinstance(testcases, list):
            global_logger.warning("AI返回的不是数组格式，跳过")
            return []

        valid_testcases = []

        for i, testcase in enumerate(testcases):
            if not isinstance(testcase, dict):
                global_logger.debug(f"跳过无效的测试用例 {i + 1}: 不是对象格式")
                continue

                # 只检查最基本的字段
            if 'name' not in testcase:
                global_logger.debug(f"跳过无效的测试用例 {i + 1}: 缺少name字段")
                continue

                # 修复测试用例
            try:
                fixed_testcase = self._fix_single_testcase(testcase, interface_data)
                if fixed_testcase:
                    valid_testcases.append(fixed_testcase)
                else:
                    global_logger.debug(f"跳过测试用例 {i + 1}: 修复失败")
            except Exception as e:
                global_logger.debug(f"跳过测试用例 {i + 1}: 修复时出错 {e}")
                continue

        global_logger.info(f"从 {len(testcases)} 个测试用例中成功处理了 {len(valid_testcases)} 个")
        return valid_testcases

    def _fix_single_testcase(self, testcase, interface_data):
        """修复单个测试用例，失败直接返回None"""
        try:
            # 必需字段的默认值
            defaults = {
                'name': testcase.get('name', '未命名测试用例'),
                'description': testcase.get('description', '自动生成的测试用例'),
                'priority': self._safe_int(testcase.get('priority'), 1),
                'request_url': testcase.get('request_url', interface_data.get('url', '/')),
                'request_method': testcase.get('request_method', interface_data.get('method', 'POST')),
                'request_headers': self._safe_dict(testcase.get('request_headers'),
                                                   {'Content-Type': 'application/json'}),
                'request_params': self._safe_dict(testcase.get('request_params'), {}),
                'expected_status': self._safe_int(testcase.get('expected_status'), 200),
                'assertions': self._safe_list(testcase.get('assertions'), [
                    {
                        'type': 'status_code',
                        'operator': 'equals',
                        'expected': 200,
                        'description': 'HTTP状态码检查'
                    }
                ]),
                'pre_script': testcase.get('pre_script', ''),
                'post_script': testcase.get('post_script', ''),
                'status': self._safe_int(testcase.get('status'), 1)
            }

            return defaults

        except Exception as e:
            global_logger.debug(f"修复测试用例失败: {e}")
            return None

    def _safe_int(self, value, default):
        """安全转换为整数"""
        try:
            return int(value) if value is not None else default
        except:
            return default

    def _safe_dict(self, value, default):
        """安全转换为字典"""
        return value if isinstance(value, dict) else default

    def _safe_list(self, value, default):
        """安全转换为列表"""
        return value if isinstance(value, list) else default

    def _clean_json_response(self, text):
        """基础清理，只做最必要的处理"""
        try:
            # 去掉markdown代码块标记
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)

            # 去掉前后的说明文字，只保留JSON数组
            start_idx = text.find('[')
            end_idx = text.rfind(']')

            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                text = text[start_idx:end_idx + 1]

            return text.strip()

        except Exception as e:
            global_logger.debug(f"清理JSON响应失败: {e}")
            return text

    def _clean_json_response(self, text):
        """清理AI返回的JSON文本"""
        # 移除可能的markdown标记
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*$', '', text)

        # 移除前后空白
        text = text.strip()

        # 如果不是以[开头，尝试找到JSON数组的开始
        if not text.startswith('['):
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                text = match.group(0)

        return text

    def generate_testcases(self, interface_data, count=10):
        """生成测试用例主方法，简化错误处理"""
        try:
            interface_name = interface_data.get('name', '未知接口')

            global_logger.info(f"开始生成测试用例: {interface_name}")
            global_logger.info(f"生成数量: {count}")
            global_logger.info(f"使用模式: {'模拟模式' if self.use_mock else 'AI模式'}")

            if self.use_mock:
                # 调用模拟生成方法
                testcases = self._generate_mock_testcases(interface_data, count)
            else:
                # 调用AI生成方法
                testcases = self._generate_ai_testcases(interface_data, count)

            if not testcases:
                global_logger.warning("未能生成有效的测试用例")
                return []

            global_logger.info(f"成功生成 {len(testcases)} 个测试用例")
            return testcases

        except Exception as e:
            global_logger.error(f"生成测试用例时发生错误: {e}")
            global_logger.error(f"错误详情: {traceback.format_exc()}")
            return []  # 确保任何异常都返回空列表，而不是抛出异常

    def _generate_ai_testcases(self, interface_data, count=15):
        """ 使用真实AI生成测试用例"""
        try:
            # 构建提示词
            prompt = self._build_prompt(interface_data, count)

            # 准备API请求
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个资深的API测试工程师，拥有10年以上的接口测试经验。  
你擅长根据接口文档设计全面的测试用例，包括：  
1. 正常场景测试  
2. 参数验证测试（必填、格式、类型等）  
3. 边界值测试  
4. 异常场景测试  
5. 安全测试  

请严格按照用户要求的JSON格式返回测试用例，不要添加任何markdown标记或其他解释文字。"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }

            global_logger.info(" 正在调用硅基流动AI API...")

            # 调用AI API
            response = requests.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                result = response.json()
                ai_content = result['choices'][0]['message']['content']

                global_logger.info(" AI API调用成功")
                global_logger.debug(f"AI响应长度: {len(ai_content)} 字符")

                # 解析AI返回的内容
                testcases = self._parse_ai_response(ai_content, interface_data)

                global_logger.info(f" AI成功生成 {len(testcases)} 个测试用例")
                return testcases

            else:
                global_logger.error(f"AI API调用失败: {response.status_code}")
                global_logger.error(f"错误详情: {response.text}")
                # 降级到模拟模式
                global_logger.info("降级使用模拟模式")
                return self._generate_mock_testcases(interface_data, count)

        except requests.exceptions.Timeout:
            global_logger.error("AI API调用超时")
            return self._generate_mock_testcases(interface_data, count)
        except Exception as e:
            global_logger.error(f"AI生成异常: {str(e)}")
            return self._generate_mock_testcases(interface_data, count)

    def _build_prompt(self, interface_data, count=15):
        """构建更严格的AI提示词"""
        interface_name = interface_data.get('name', '未知接口')
        interface_url = interface_data.get('url', '')
        interface_method = interface_data.get('method', 'POST')
        interface_params = interface_data.get('params', {})
        interface_desc = interface_data.get('description', '')
        prompt = f"""请为以下接口生成{count}个测试用例。  

                接口信息：  
                - 名称：{interface_name}  
                - URL：{interface_url}  
                - 方法：{interface_method}  
                - 描述：{interface_desc}  
                - 参数：{json.dumps(interface_params, ensure_ascii=False, indent=2)}  

                **重要：后端代码逻辑说明**  
                1. 成功登录条件：用户名必须是 "admin" 或 "testuser"，且密码正确  
                2. 后端对参数验证较严格：空值、长度、特殊字符都会返回400  
                3. HTTP状态码始终为200，业务状态码在响应体的code字段中  
                4. 成功：响应体中code=200，失败：响应体中code=400  

                测试用例要求：  
                1. **正常场景（业务状态码: 200）**：  
                   - 用户名为 "admin" 且密码为 "admin123"  
                   - 用户名为 "testuser" 且密码为 "password123"  

                2. **异常场景（业务状态码: 400）**：  
                   - 用户名为空或密码为空  
                   - 用户名不是 "admin" 或 "testuser"（如：包含数字、其他字符串）  
                   - 密码错误（即使用户名正确）  
                   - 用户名或密码长度超出限制  
                   - 用户名或密码包含特殊字符  
                   - 参数缺失或格式错误  

                **特别注意**：  
                - HTTP状态码始终为200  
                - 断言要检查响应体中的code字段，不是HTTP状态码  
                - 用户名包含数字（如"123testuser"）业务状态码应该是400  
                - 只有精确匹配 "admin"/"testuser" 且密码正确才返回业务状态码200  

                严格要求：  
                1. 必须返回标准JSON数组格式  
                2. 不能包含任何注释（//或/* */）  
                3. 不能使用JavaScript语法（null、undefined等）  
                4. 所有字符串必须用双引号包围  
                5. 只返回JSON数组，不要其他解释  

                必须严格按照以下格式返回：  

                [  
                  {{  
                    "name": "正常登录测试-admin",  
                    "description": "测试admin用户能否成功登录",  
                    "priority": 1,  
                    "request_url": "{interface_url}",  
                    "request_method": "{interface_method}",  
                    "request_headers": {{  
                      "Content-Type": "application/json"  
                    }},  
                    "request_params": {{  
                      "username": "admin",  
                      "password": "admin123"  
                    }},  
                    "expected_status": 200,  
                    "assertions": [  
                      {{  
                        "type": "json_path",  
                        "path": "$.code",  
                        "operator": "eq",  
                        "expected": 200,  
                        "description": "检查业务状态码为200"  
                      }}  
                    ],  
                    "pre_script": "",  
                    "post_script": "",  
                    "status": 1  
                  }},  
                  {{  
                    "name": "正常登录测试-testuser",  
                    "description": "测试testuser用户能否成功登录",  
                    "priority": 1,  
                    "request_url": "{interface_url}",  
                    "request_method": "{interface_method}",  
                    "request_headers": {{  
                      "Content-Type": "application/json"  
                    }},  
                    "request_params": {{  
                      "username": "testuser",  
                      "password": "password123"  
                    }},  
                    "expected_status": 200,  
                    "assertions": [  
                      {{  
                        "type": "json_path",  
                        "path": "$.code",  
                        "operator": "eq",  
                        "expected": 200,  
                        "description": "检查业务状态码为200"  
                      }}  
                    ],  
                    "pre_script": "",  
                    "post_script": "",  
                    "status": 1  
                  }},  
                  {{  
                    "name": "用户名为空测试",  
                    "description": "测试用户名为空时的错误处理",  
                    "priority": 2,  
                    "request_url": "{interface_url}",  
                    "request_method": "{interface_method}",  
                    "request_headers": {{  
                      "Content-Type": "application/json"  
                    }},  
                    "request_params": {{  
                      "username": "",  
                      "password": "password123"  
                    }},  
                    "expected_status": 200,  
                    "assertions": [  
                      {{  
                        "type": "json_path",  
                        "path": "$.code",  
                        "operator": "eq",  
                        "expected": 400,  
                        "description": "检查业务状态码为400"  
                      }}  
                    ],  
                    "pre_script": "",  
                    "post_script": "",  
                    "status": 1  
                  }},  
                  {{  
                    "name": "用户名包含数字测试",  
                    "description": "测试用户名包含数字时的错误处理",  
                    "priority": 2,  
                    "request_url": "{interface_url}",  
                    "request_method": "{interface_method}",  
                    "request_headers": {{  
                      "Content-Type": "application/json"  
                    }},  
                    "request_params": {{  
                      "username": "123testuser",  
                      "password": "password123"  
                    }},  
                    "expected_status": 200,  
                    "assertions": [  
                      {{  
                        "type": "json_path",  
                        "path": "$.code",  
                        "operator": "eq",  
                        "expected": 400,  
                        "description": "检查业务状态码为400"  
                      }}  
                    ],  
                    "pre_script": "",  
                    "post_script": "",  
                    "status": 1  
                  }}  
                ]  

                重要：  
                - 所有expected_status都设为200（HTTP状态码）  
                - 断言使用json_path类型检查$.code字段（业务状态码）  
                - 成功场景：断言expected为200，失败场景：断言expected为400  
                - 只返回JSON数组，不要包含markdown标记或其他文字！"""

        return prompt


    def _parse_ai_response(self, ai_content, interface_data):
        """解析AI返回的内容 - 容错版本"""
        try:
            # 清理内容
            content = ai_content.strip()

            # 提取JSON部分
            content = self._extract_json_content(content)

            # 先尝试直接解析
            try:
                testcases = json.loads(content)
                if isinstance(testcases, list):
                    global_logger.info(f"直接解析成功，获得 {len(testcases)} 个测试用例")
                    return self._validate_testcases(testcases, interface_data)
            except json.JSONDecodeError:
                global_logger.info("直接解析失败，尝试分段解析...")

                # 如果直接解析失败，尝试分段解析
            return self._parse_testcases_individually(content, interface_data)

        except Exception as e:
            global_logger.error(f"解析AI响应异常: {e}")
            return []

    def _extract_json_content(self, content):
        """提取JSON内容"""
        import re

        if '```json' in content:
            start = content.find('```json') + 7
            end = content.find('```', start)
            if end != -1:
                return content[start:end].strip()

                # 找到JSON数组的开始和结束
        start = content.find('[')
        end = content.rfind(']')
        if start != -1 and end != -1 and end > start:
            return content[start:end + 1]

        return content.strip()

    def _parse_testcases_individually(self, content, interface_data):
        """逐个解析测试用例"""
        import re

        # 尝试找到所有测试用例块
        # 匹配 { ... } 的完整块
        pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(pattern, content, re.DOTALL)

        if not matches:
            # 如果正则匹配失败，尝试手动分割
            return self._manual_split_testcases(content, interface_data)

        valid_testcases = []
        for i, match in enumerate(matches):
            try:
                # 尝试解析单个测试用例
                testcase = json.loads(match)
                if isinstance(testcase, dict):
                    fixed_testcase = self._fix_testcase(testcase, interface_data, i + 1)
                    if fixed_testcase:
                        valid_testcases.append(fixed_testcase)
                        global_logger.info(f"成功解析第 {i + 1} 个测试用例: {testcase.get('name', '未命名')}")
                    else:
                        global_logger.warning(f"第 {i + 1} 个测试用例验证失败")
                else:
                    global_logger.warning(f"第 {i + 1} 个匹配项不是有效的测试用例对象")
            except json.JSONDecodeError as e:
                global_logger.warning(f"第 {i + 1} 个测试用例解析失败: {e}")
                # 尝试修复这个测试用例
                try:
                    fixed_match = self._fix_single_testcase_json(match)
                    if fixed_match:
                        testcase = json.loads(fixed_match)
                        if isinstance(testcase, dict):
                            fixed_testcase = self._fix_testcase(testcase, interface_data, i + 1)
                            if fixed_testcase:
                                valid_testcases.append(fixed_testcase)
                                global_logger.info(f"修复后成功解析第 {i + 1} 个测试用例")
                except:
                    global_logger.warning(f"第 {i + 1} 个测试用例修复失败，跳过")
                    continue
            except Exception as e:
                global_logger.warning(f"第 {i + 1} 个测试用例处理异常: {e}")
                continue

        global_logger.info(f"分段解析完成，成功获得 {len(valid_testcases)} 个有效测试用例")
        return valid_testcases

    def _manual_split_testcases(self, content, interface_data):
        """手动分割测试用例"""
        valid_testcases = []

        # 移除外层数组括号
        content = content.strip()
        if content.startswith('['):
            content = content[1:]
        if content.endswith(']'):
            content = content[:-1]

            # 按照 },{ 分割，但要小心嵌套对象
        testcase_strings = []
        current_testcase = ""
        brace_count = 0
        in_string = False
        escape_next = False

        for char in content:
            if escape_next:
                current_testcase += char
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                current_testcase += char
                continue

            if char == '"' and not escape_next:
                in_string = not in_string

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

            current_testcase += char

            # 如果找到了完整的对象
            if brace_count == 0 and current_testcase.strip():
                testcase_strings.append(current_testcase.strip().rstrip(','))
                current_testcase = ""

                # 处理最后一个测试用例
        if current_testcase.strip():
            testcase_strings.append(current_testcase.strip().rstrip(','))

            # 逐个解析测试用例
        for i, testcase_str in enumerate(testcase_strings):
            try:
                testcase = json.loads(testcase_str)
                if isinstance(testcase, dict):
                    fixed_testcase = self._fix_testcase(testcase, interface_data, i + 1)
                    if fixed_testcase:
                        valid_testcases.append(fixed_testcase)
                        global_logger.info(f"手动分割成功解析第 {i + 1} 个测试用例")
            except:
                global_logger.warning(f"手动分割第 {i + 1} 个测试用例解析失败")
                continue

        return valid_testcases

    def _fix_single_testcase_json(self, json_str):
        """修复单个测试用例的JSON格式"""
        import re

        # 修复Python字符串连接
        json_str = re.sub(r'"([^"]+)"\s*\+\s*"([^"]+)"', r'"\1\2"', json_str)

        # 修复Python长整型
        json_str = re.sub(r'(\d+)L\b', r'\1', json_str)

        # 修复Python字符串乘法
        json_str = re.sub(r'"([^"]*?)"\s*\*\s*\d+', '"test_very_long_string"', json_str)

        # 修复Python布尔值
        json_str = re.sub(r'\bTrue\b', 'true', json_str)
        json_str = re.sub(r'\bFalse\b', 'false', json_str)
        json_str = re.sub(r'\bNone\b', 'null', json_str)

        return json_str

    def _validate_testcases(self, testcases, interface_data):
        """验证测试用例列表"""
        valid_testcases = []

        for i, testcase in enumerate(testcases):
            try:
                fixed_testcase = self._fix_testcase(testcase, interface_data, i + 1)
                if fixed_testcase:
                    valid_testcases.append(fixed_testcase)
                    global_logger.info(f"第 {i + 1} 个测试用例验证通过: {testcase.get('name', '未命名')}")
                else:
                    global_logger.warning(f"第 {i + 1} 个测试用例验证失败: {testcase.get('name', '未命名')}")
            except Exception as e:
                global_logger.warning(f"第 {i + 1} 个测试用例处理异常: {e}")
                continue

        return valid_testcases

    def _fix_testcase(self, testcase, interface_data, index):
        """修复和验证单个测试用例"""
        try:
            # 补充必要字段
            fixed_testcase = {
                "name": testcase.get("name", f"测试用例{index}"),
                "description": testcase.get("description", ""),
                "priority": testcase.get("priority", 1),
                "request_url": testcase.get("request_url", interface_data.get("url", "")),
                "request_method": testcase.get("request_method", interface_data.get("method", "GET")),
                "request_headers": testcase.get("request_headers", {}),
                "request_params": testcase.get("request_params", {}),
                "expected_status": testcase.get("expected_status", 200),
                "assertions": testcase.get("assertions", []),
                "pre_script": testcase.get("pre_script", ""),
                "post_script": testcase.get("post_script", ""),
                "status": testcase.get("status", 1)
            }

            # 基本验证
            if not fixed_testcase["name"]:
                return None

            if not fixed_testcase["request_url"]:
                return None

                # 确保headers是字典
            if not isinstance(fixed_testcase["request_headers"], dict):
                fixed_testcase["request_headers"] = {}

                # 确保params是字典
            if not isinstance(fixed_testcase["request_params"], dict):
                fixed_testcase["request_params"] = {}

                # 确保assertions是列表
            if not isinstance(fixed_testcase["assertions"], list):
                fixed_testcase["assertions"] = []

                # 如果没有断言，添加默认状态码断言
            if not fixed_testcase["assertions"]:
                fixed_testcase["assertions"] = [{
                    "type": "status_code",
                    "operator": "equals",
                    "expected": fixed_testcase["expected_status"],
                    "description": "HTTP状态码检查"
                }]

            return fixed_testcase

        except Exception as e:
            global_logger.warning(f"修复测试用例失败: {e}")
            return None

    def _fix_json_format(self, content):
        """修复JSON格式问题"""
        import re

        # 1. 修复Python字符串连接表达式 "str1" + "str2"
        content = re.sub(r'"([^"]+)"\s*\+\s*"([^"]+)"', r'"\1\2"', content)

        # 2. 修复Python长整型标记 123L
        content = re.sub(r'(\d+)L\b', r'\1', content)

        # 3. 修复Python字符串乘法 "str" * 10 (简化版，直接替换为固定字符串)
        content = re.sub(r'"([^"]*?)"\s*\*\s*\d+', '"test_very_long_string_value"', content)

        # 4. 修复Python布尔值
        content = re.sub(r'\bTrue\b', 'true', content)
        content = re.sub(r'\bFalse\b', 'false', content)
        content = re.sub(r'\bNone\b', 'null', content)

        return content

    def _try_fix_json(self, content):
        """尝试手动修复JSON格式错误"""
        try:
            import re

            # 修复常见的JSON格式错误
            # 1. 修复孤立的字符串（缺少键名）
            content = re.sub(r'{\s*"test_string",', '{"username": "test_string_value",', content)
            content = re.sub(r',\s*"test_string"\s*}', ', "password": "test_string_value"}', content)

            # 2. 修复 "test_string", 后面跟 "password": 的情况
            content = re.sub(r'"test_string",\s*\n\s*"password":',
                             '"username": "test_string_value",\n      "password":', content)

            # 3. 修复 "username": "testuser", 后面跟 "test_string" 的情况
            content = re.sub(r'"username":\s*"[^"]*",\s*\n\s*"test_string"',
                             '"username": "testuser",\n      "password": "test_string_value"', content)

            # 4. 修复其他可能的格式问题
            content = re.sub(r'"[^"]*"\s*\*\s*\d+', '"test_string_value"', content)

            return content

        except Exception as e:
            global_logger.error(f"手动修复JSON失败: {e}")
            return None

    def _generate_mock_testcases(self, interface_data, count=15):
        """生成模拟测试用例（备用方案）"""
        global_logger.info("使用模拟模式生成测试用例")

        interface_name = interface_data.get('name', '未知接口')
        interface_url = interface_data.get('url', '/api/test')
        interface_method = interface_data.get('method', 'POST')
        interface_params = interface_data.get('params', {})

        # 生成模拟测试用例
        mock_testcases = []

        # 1. 正常场景
        mock_testcases.append({
            "name": f"{interface_name} - 正常场景测试",
            "description": "使用有效参数进行正常场景测试",
            "priority": 1,
            "request_url": interface_url,
            "request_method": interface_method,
            "request_headers": {"Content-Type": "application/json"},
            "request_params": self._generate_valid_params(interface_params),
            "expected_status": 200,
            "assertions": [
                {
                    "type": "status_code",
                    "operator": "equals",
                    "expected": 200,
                    "description": "HTTP状态码应为200"
                }
            ],
            "pre_script": "",
            "post_script": "",
            "status": 1
        })

        # 2. 参数为空测试
        for param_name in interface_params.keys():
            mock_testcases.append({
                "name": f"{interface_name} - {param_name}参数为空测试",
                "description": f"测试{param_name}参数为空时的接口响应",
                "priority": 2,
                "request_url": interface_url,
                "request_method": interface_method,
                "request_headers": {"Content-Type": "application/json"},
                "request_params": self._generate_empty_param(interface_params, param_name),
                "expected_status": 400,
                "assertions": [
                    {
                        "type": "status_code",
                        "operator": "equals",
                        "expected": 400,
                        "description": "参数为空时应返回400状态码"
                    }
                ],
                "pre_script": "",
                "post_script": "",
                "status": 1
            })

            # 3. 参数类型错误测试
            for param_name in interface_params.keys():
                mock_testcases.append({
                    "name": f"{interface_name} - {param_name}参数类型错误测试",
                    "description": f"测试{param_name}参数类型错误时的接口响应",
                    "priority": 2,
                    "request_url": interface_url,
                    "request_method": interface_method,
                    "request_headers": {"Content-Type": "application/json"},
                    "request_params": self._generate_invalid_type_param(interface_params, param_name),
                    "expected_status": 400,
                    "assertions": [
                        {
                            "type": "status_code",
                            "operator": "equals",
                            "expected": 400,
                            "description": "参数类型错误时应返回400状态码"
                        }
                    ],
                    "pre_script": "",
                    "post_script": "",
                    "status": 1
                })

                # 4. 边界值测试
            mock_testcases.extend([
                {
                    "name": f"{interface_name} - 最大长度测试",
                    "description": "测试参数最大长度限制",
                    "priority": 2,
                    "request_url": interface_url,
                    "request_method": interface_method,
                    "request_headers": {"Content-Type": "application/json"},
                    "request_params": self._generate_max_length_params(interface_params),
                    "expected_status": 200,
                    "assertions": [
                        {
                            "type": "status_code",
                            "operator": "equals",
                            "expected": 200,
                            "description": "最大长度参数应正常处理"
                        }
                    ],
                    "pre_script": "",
                    "post_script": "",
                    "status": 1
                },
                {
                    "name": f"{interface_name} - 超长参数测试",
                    "description": "测试超长参数的处理",
                    "priority": 2,
                    "request_url": interface_url,
                    "request_method": interface_method,
                    "request_headers": {"Content-Type": "application/json"},
                    "request_params": self._generate_over_length_params(interface_params),
                    "expected_status": 400,
                    "assertions": [
                        {
                            "type": "status_code",
                            "operator": "equals",
                            "expected": 400,
                            "description": "超长参数应返回400状态码"
                        }
                    ],
                    "pre_script": "",
                    "post_script": "",
                    "status": 1
                }
            ])

            # 5. 特殊字符测试
            mock_testcases.append({
                "name": f"{interface_name} - 特殊字符测试",
                "description": "测试特殊字符的处理",
                "priority": 2,
                "request_url": interface_url,
                "request_method": interface_method,
                "request_headers": {"Content-Type": "application/json"},
                "request_params": self._generate_special_char_params(interface_params),
                "expected_status": 200,
                "assertions": [
                    {
                        "type": "status_code",
                        "operator": "equals",
                        "expected": 200,
                        "description": "特殊字符应正常处理"
                    }
                ],
                "pre_script": "",
                "post_script": "",
                "status": 1
            })

            # 6. 权限测试
            mock_testcases.append({
                "name": f"{interface_name} - 无权限测试",
                "description": "测试无权限访问的处理",
                "priority": 2,
                "request_url": interface_url,
                "request_method": interface_method,
                "request_headers": {"Content-Type": "application/json"},
                "request_params": self._generate_valid_params(interface_params),
                "expected_status": 401,
                "assertions": [
                    {
                        "type": "status_code",
                        "operator": "equals",
                        "expected": 401,
                        "description": "无权限时应返回401状态码"
                    }
                ],
                "pre_script": "",
                "post_script": "",
                "status": 1
            })

            # 7. 安全测试
            mock_testcases.append({
                "name": f"{interface_name} - SQL注入测试",
                "description": "测试SQL注入防护",
                "priority": 3,
                "request_url": interface_url,
                "request_method": interface_method,
                "request_headers": {"Content-Type": "application/json"},
                "request_params": self._generate_sql_injection_params(interface_params),
                "expected_status": 400,
                "assertions": [
                    {
                        "type": "status_code",
                        "operator": "equals",
                        "expected": 400,
                        "description": "SQL注入应被拦截"
                    }
                ],
                "pre_script": "",
                "post_script": "",
                "status": 1
            })

            # 根据count截取相应数量的测试用例
            result_testcases = mock_testcases[:count]

            global_logger.info(f"模拟生成了 {len(result_testcases)} 个测试用例")
            return result_testcases

    def _generate_valid_params(self, interface_params):
        """生成有效的参数"""
        valid_params = {}
        for param_name, param_type in interface_params.items():
            if param_type == 'string':
                valid_params[param_name] = "testvalue"
            elif param_type == 'int' or param_type == 'integer':
                valid_params[param_name] = 123
            elif param_type == 'float':
                valid_params[param_name] = 123.45
            elif param_type == 'bool' or param_type == 'boolean':
                valid_params[param_name] = True
            elif param_type == 'email':
                valid_params[param_name] = "test@example.com"
            elif param_type == 'phone':
                valid_params[param_name] = "13800138000"
            else:
                valid_params[param_name] = "testvalue"
        return valid_params

    def _generate_empty_param(self, interface_params, empty_param_name):
        """生成指定参数为空的参数组合"""
        params = self._generate_valid_params(interface_params)
        params[empty_param_name] = ""
        return params

    def _generate_invalid_type_param(self, interface_params, invalid_param_name):
        """生成指定参数类型错误的参数组合"""
        params = self._generate_valid_params(interface_params)
        param_type = interface_params.get(invalid_param_name, 'string')

        if param_type in ['int', 'integer']:
            params[invalid_param_name] = "not_a_number"
        elif param_type == 'email':
            params[invalid_param_name] = "invalid_email"
        elif param_type == 'phone':
            params[invalid_param_name] = "invalid_phone"
        elif param_type in ['bool', 'boolean']:
            params[invalid_param_name] = "not_boolean"
        else:
            params[invalid_param_name] = 12345  # 字符串类型用数字

        return params

    def _generate_max_length_params(self, interface_params):
        """生成最大长度的参数"""
        params = self._generate_valid_params(interface_params)
        for param_name, param_type in interface_params.items():
            if param_type == 'string':
                params[param_name] = "a" * 50  # 50个字符
        return params

    def _generate_over_length_params(self, interface_params):
        """生成超长参数"""
        params = self._generate_valid_params(interface_params)
        for param_name, param_type in interface_params.items():
            if param_type == 'string':
                params[param_name] = "a" * 1000  # 1000个字符
        return params

    def _generate_special_char_params(self, interface_params):
        """生成包含特殊字符的参数"""
        params = self._generate_valid_params(interface_params)
        special_chars = ["<script>", "'; DROP TABLE users; --", "中文测试", "测试@#$%^&*()"]

        for i, (param_name, param_type) in enumerate(interface_params.items()):
            if param_type == 'string':
                params[param_name] = special_chars[i % len(special_chars)]

        return params

    def _generate_sql_injection_params(self, interface_params):
        """生成SQL注入测试参数"""
        params = self._generate_valid_params(interface_params)
        sql_injection_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "admin'--"
        ]

        for i, (param_name, param_type) in enumerate(interface_params.items()):
            if param_type == 'string':
                params[param_name] = sql_injection_payloads[i % len(sql_injection_payloads)]

        return params

    def get_ai_service_status(self):
        """获取AI服务状态"""
        return {
            "ai_enabled": not self.use_mock,
            "model": self.config.model if hasattr(self.config, 'model') else 'Unknown',
            "base_url": self.config.base_url if hasattr(self.config, 'base_url') else 'Unknown',
            "config_valid": CONFIG_VALID,
            "last_test_time": datetime.now().isoformat()
        }

    def test_ai_connection(self):
        """手动测试AI连接"""
        self._test_connection()
        return self.get_ai_service_status()

# 全局单例实例
_ai_service_instance = None

def get_ai_service():
    """获取AI服务实例（单例模式）"""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance

# 兼容性别名和函数
ai_service = get_ai_service()

def create_ai_service():
    """创建AI服务实例"""
    return AIService()

def generate_testcases(interface_data, count=15):
    """全局函数版本的测试用例生成"""
    service = get_ai_service()
    return service.generate_testcases(interface_data, count)