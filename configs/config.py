# config.py

# 数据库配置
MYSQL_HOST= 'localhost'
MYSQL_PORT = 3306
MYSQL_DATABASE = 'TPMStore'
MYSQL_USER = 'root'
MYSQL_PASSWORD = '123456'


# 邮件配置
SMTP_SERVER = "smtp.qq.com"  # 使用已有的MAIL_HOST
SMTP_PORT = 465                     # 使用已有的MAIL_PORT
SMTP_USER = ""      # 替换为真实的发件人邮箱
SMTP_PASSWORD = ""     # 替换为真实的邮箱密码
FROM_EMAIL = ""     # 发件人邮箱，通常与SMTP_USER相同

# 默认收件人列表
DEFAULT_EMAIL_RECIPIENTS = [
    ""#邮箱
]

# 邮件主题前缀
EMAIL_SUBJECT_PREFIX = "[API测试]"