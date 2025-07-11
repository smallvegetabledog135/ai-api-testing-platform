"""
通知服务类 - 负责发送测试分析报告邮件
"""
import sys
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Dict, List
from datetime import datetime
from configs import config
from app import celery, global_logger
from typing import Dict, List, Optional

@celery.task(name='services.notification_service.send_email_task')
def send_email_task(subject, recipients, html_content, attachments=None, **kwargs):
    """发送邮件任务

    Args:
        subject (str): 邮件主题
        recipients (list): 收件人列表
        html_content (str): HTML格式的邮件内容
        attachments (list, optional): 附件列表，每个附件是包含path和filename的字典
        **kwargs: 其他可能的参数，如 batch_info, analysis_data 等
    """
    try:
        global_logger.info(f"开始处理邮件发送任务，收件人: {recipients}")

        # 记录额外参数
        if kwargs:
            global_logger.info(f"收到额外参数: {', '.join(kwargs.keys())}")

        # 获取SMTP配置 - 从kwargs中获取或使用默认配置
        smtp_config = kwargs.get('smtp_config', {})
        smtp_server = smtp_config.get('server', config.SMTP_SERVER)
        smtp_port = smtp_config.get('port', config.SMTP_PORT)
        smtp_user = smtp_config.get('user', config.SMTP_USER)
        smtp_password = smtp_config.get('password', config.SMTP_PASSWORD)
        from_email = smtp_config.get('from_email', config.FROM_EMAIL)

        global_logger.info(f"SMTP配置: 服务器={smtp_server}, 端口={smtp_port}, 用户={smtp_user}, 发件人={from_email}")

        # 创建邮件
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = ', '.join(recipients)

        # 添加HTML内容
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # 添加附件
        if attachments:
            for attachment in attachments:
                with open(attachment['path'], 'rb') as f:
                    attach = MIMEApplication(f.read())
                    attach.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
                    msg.attach(attach)

        # 连接SMTP服务器并发送
        try:
            global_logger.info(f"连接SMTP服务器: {smtp_server}:{smtp_port}")

            # 使用SSL连接
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)

            # 登录
            global_logger.info(f"登录SMTP服务器，用户名: {smtp_user}")
            server.login(smtp_user, smtp_password)

            # 发送邮件
            global_logger.info(f"发送邮件，发件人: {from_email}, 收件人: {recipients}")
            server.sendmail(from_email, recipients, msg.as_string())

            # 关闭连接
            server.quit()

            global_logger.info("邮件发送成功")
            return True

        except Exception as e:
            global_logger.error(f"SMTP操作异常: {str(e)}")
            global_logger.error(traceback.format_exc())
            # 邮件发送失败但不影响整体流程
            return False

    except Exception as e:
        global_logger.error(f"邮件发送任务异常: {str(e)}")
        global_logger.error(traceback.format_exc())
        # 邮件发送失败但不影响整体流程
        return False
def build_email_content(analysis_data: Dict, batch_info: Dict) -> str:
    """
    构建邮件HTML内容

    Args:
        analysis_data: 分析数据
        batch_info: 批次信息

    Returns:
        str: HTML内容
    """
    # 这里实现你的邮件内容构建逻辑
    # 如果原来是在NotificationService类中实现的，把代码复制过来

    html = f"""  
    <html>  
    <head>  
        <style>  
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}  
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}  
            h1 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }}  
            h2 {{ color: #3498db; margin-top: 20px; }}  
            .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}  
            .success {{ color: green; }}  
            .failure {{ color: red; }}  
            .warning {{ color: orange; }}  
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}  
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}  
            th {{ background-color: #f2f2f2; }}  
            .footer {{ margin-top: 30px; font-size: 12px; color: #777; border-top: 1px solid #eee; padding-top: 10px; }}  
        </style>  
    </head>  
    <body>  
        <div class="container">  
            <h1>API测试报告 - {batch_info.get('interface_name', '未知接口')}</h1>  

            <div class="summary">  
                <h2>测试摘要</h2>  
                <p><strong>批次名称:</strong> {batch_info.get('name', '未知批次')}</p>  
                <p><strong>应用ID:</strong> {batch_info.get('app_id', '未知应用')}</p>  
                <p><strong>执行时间:</strong> {analysis_data['summary'].get('execution_time', '未知')}</p>  
                <p><strong>测试用例总数:</strong> {analysis_data['summary'].get('total_cases', 0)}</p>  
                <p><strong>通过数量:</strong> <span class="success">{analysis_data['summary'].get('success_count', 0)}</span></p>  
                <p><strong>失败数量:</strong> <span class="failure">{analysis_data['summary'].get('failed_count', 0)}</span></p>  
                <p><strong>通过率:</strong> {analysis_data['summary'].get('success_rate', 0):.1f}%</p>  
                <p><strong>整体状态:</strong> <span class="{analysis_data['summary'].get('overall_status', 'FAIL').lower()}">{analysis_data['summary'].get('overall_status', 'FAIL')}</span></p>  
                <p><strong>风险等级:</strong> <span class="warning">{analysis_data['summary'].get('risk_level', 'HIGH')}</span></p>  
            </div>  

            <h2>关键发现</h2>  
            <ul>  
                {' '.join([f'<li>{finding}</li>' for finding in analysis_data.get('key_findings', [])])}  
            </ul>  
    """

    # 添加失败分析部分（如果有）
    if analysis_data.get('failure_analysis'):
        html += f"""  
            <h2>失败分析</h2>  
            <ul>  
                {' '.join([f'<li>{reason}</li>' for reason in analysis_data.get('failure_analysis', [])])}  
            </ul>  
        """

        # 添加建议部分
    html += f"""  
            <h2>建议</h2>  
            <ul>  
                {' '.join([f'<li>{recommendation}</li>' for recommendation in analysis_data.get('recommendations', [])])}  
            </ul>  

            <h2>后续步骤</h2>  
            <ul>  
                {' '.join([f'<li>{step}</li>' for step in analysis_data.get('next_steps', [])])}  
            </ul>  

            <div class="footer">  
                <p>此邮件由自动化测试系统生成，请勿直接回复。</p>  
            </div>  
        </div>  
    </body>  
    </html>  
    """

    return html

class NotificationService:
    """通知服务类"""
    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """初始化邮件服务"""
        self.smtp_server = config.SMTP_SERVER
        self.smtp_port = config.SMTP_PORT
        self.smtp_user = config.SMTP_USER
        self.smtp_password = config.SMTP_PASSWORD
        self.from_email = config.FROM_EMAIL
        global_logger.info("通知服务初始化成功")

    def _build_email_content(self, analysis_data: Dict, batch_info: Dict) -> str:
        """构建邮件HTML内容"""
        # 从外部文件加载HTML模板会更好
        # 这里为了简化，仍然使用内联模板，但减少了代码量
        summary = analysis_data.get('summary', {})

        # 确定状态颜色
        status_color = '#28a745' if summary.get('overall_status') == 'PASS' else '#dc3545'
        risk_colors = {'LOW': '#28a745', 'MEDIUM': '#ffc107', 'HIGH': '#dc3545'}
        risk_color = risk_colors.get(summary.get('risk_level', 'MEDIUM'), '#ffc107')

        # 构建基本信息部分
        basic_info = f"""  
        <div class="header">  
            <h1> API测试分析报告</h1>  
            <p>批次：{batch_info.get('name', '未知批次')}</p>  
            <p>生成时间：{summary.get('execution_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</p>  
        </div>  
        """

        # 构建统计信息部分
        stats_info = f"""  
        <div class="summary">  
            <div class="summary-item"><div class="number">{summary.get('total_cases', 0)}</div><div class="label">总用例数</div></div>  
            <div class="summary-item"><div class="number" style="color: #28a745;">{summary.get('success_count', 0)}</div><div class="label">成功数</div></div>  
            <div class="summary-item"><div class="number" style="color: #dc3545;">{summary.get('failed_count', 0)}</div><div class="label">失败数</div></div>  
            <div class="summary-item"><div class="number">{summary.get('success_rate', 0):.1f}%</div><div class="label">成功率</div></div>  
            <div class="summary-item"><span class="status-badge" style="background-color: {status_color};">{summary.get('overall_status', 'UNKNOWN')}</span></div>  
            <div class="summary-item"><span class="status-badge" style="background-color: {risk_color};">风险: {summary.get('risk_level', 'MEDIUM')}</span></div>  
        </div>  
        """

        # 构建各部分内容
        sections = [
            self._build_section(" 关键发现", analysis_data.get('key_findings', [])),
            self._build_section(" 失败原因分析", analysis_data.get('failure_analysis', [])),
            self._build_section(" 改进建议", analysis_data.get('recommendations', [])),
            self._build_section("后续行动", analysis_data.get('next_steps', []))
        ]

        # 构建页脚
        footer = f"""  
        <div class="footer">  
            <p>此报告由AI自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>  
            <p>如有疑问，请联系测试团队</p>  
        </div>  
        """

        # 组合HTML
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>API测试报告</title>  
        <style>  
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}  
            .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}  
            .header {{ text-align: center; border-bottom: 3px solid #007bff; padding-bottom: 20px; margin-bottom: 30px; }}  
            .header h1 {{ color: #007bff; margin: 0; font-size: 28px; }}  
            .summary {{ background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin-bottom: 25px; }}  
            .summary-item {{ display: inline-block; margin: 10px 20px; text-align: center; }}  
            .summary-item .number {{ font-size: 24px; font-weight: bold; color: #007bff; }}  
            .summary-item .label {{ font-size: 14px; color: #666; }}  
            .status-badge {{ padding: 6px 12px; border-radius: 20px; color: white; font-weight: bold; }}  
            .section {{ margin-bottom: 25px; }}  
            .section h3 {{ color: #333; border-left: 4px solid #007bff; padding-left: 15px; }}  
            .list-item {{ background-color: #f8f9fa; margin: 8px 0; padding: 12px; border-radius: 4px; border-left: 3px solid #007bff; }}  
            .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px; }}  
        </style></head>  
        <body><div class="container">{basic_info}{stats_info}{''.join(sections)}{footer}</div></body></html>  
        """

        return html

    def _build_section(self, title: str, items: List[str]) -> str:
        """构建报告中的一个部分"""
        items_html = self._format_list_items(items)
        return f'<div class="section"><h3>{title}</h3>{items_html}</div>'

    def _format_list_items(self, items: List[str]) -> str:
        """格式化列表项为HTML"""
        if not items:
            return '<div class="list-item">暂无数据</div>'

        return ''.join([f'<div class="list-item">{item}</div>' for item in items])

    def send_analysis_report(self, analysis_data: Dict, batch_info: Dict, recipients: List[str]) -> Optional[str]:
        """
        发送分析报告邮件 - 异步方式

        Args:
            analysis_data: 分析数据
            batch_info: 批次信息
            recipients: 收件人列表

        Returns:
            str: 任务ID，如果失败则返回None
        """
        try:
            # 构建邮件内容
            html_content = self._build_email_content(analysis_data, batch_info)
            subject = f"API测试分析报告 - {batch_info.get('name', '未知批次')}"

            # 准备SMTP配置
            smtp_config = {
                'server': self.smtp_server,
                'port': self.smtp_port,
                'user': self.smtp_user,
                'password': self.smtp_password,
                'from_email': self.from_email
            }

            # 调用Celery任务
            task = send_email_task.delay(
                subject=subject,
                recipients=recipients,
                html_content=html_content,
                smtp_config=smtp_config,
                batch_info=batch_info,
                analysis_data=analysis_data
            )

            global_logger.info(f"邮件发送任务已提交，任务ID: {task.id}")
            return task.id

        except Exception as e:
            global_logger.error(f"邮件发送任务提交失败: {str(e)}")
            global_logger.error(f"异常堆栈: {traceback.format_exc()}")
            return None

    def send_test_email_directly(self, recipient: str) -> bool:
        """
        直接发送测试邮件（不使用Celery）

        Args:
            recipient: 收件人邮箱

        Returns:
            bool: 是否发送成功
        """
        try:
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = recipient
            msg['Subject'] = Header("测试邮件 - 请忽略", 'utf-8')

            # 添加纯文本内容
            text = "这是一封测试邮件，用于验证SMTP设置是否正确。"
            msg.attach(MIMEText(text, 'plain', 'utf-8'))

            # 添加HTML内容
            html = """  
            <html>  
              <body>  
                <h1>测试邮件</h1>  
                <p>这是一封测试邮件，用于验证SMTP设置是否正确。</p>  
                <p>如果您收到此邮件，说明邮件服务配置正常。</p>  
              </body>  
            </html>  
            """
            msg.attach(MIMEText(html, 'html', 'utf-8'))

            # 连接SMTP服务器并发送
            global_logger.info(f"尝试连接SMTP服务器: {self.smtp_server}:{self.smtp_port}")
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                global_logger.info(f"尝试登录SMTP服务器，用户名: {self.smtp_user}")
                server.login(self.smtp_user, self.smtp_password)
                global_logger.info(f"尝试发送邮件从 {self.from_email} 到 {recipient}")
                server.sendmail(self.from_email, [recipient], msg.as_string())

            global_logger.info(f"测试邮件已直接发送至 {recipient}")
            return True

        except Exception as e:
            global_logger.error(f"测试邮件发送失败: {str(e)}")
            global_logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False

        # 定义Celery任务


# 简化的获取服务实例函数
def get_notification_service():
    """获取通知服务实例"""
    return NotificationService.get_instance()