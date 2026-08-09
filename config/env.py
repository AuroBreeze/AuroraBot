# from config.environment.basic import *
import os

from api import Logger_owner


logs = Logger_owner.Logger(log_name='ENV')
# 运行环境：AURORA_ENV 环境变量控制（Docker 部署设为 prod），默认 dev
current_env = os.getenv('AURORA_ENV', 'dev')

if current_env == 'dev':
    from config.environment.basic import *
else:
    from config.environment.prod import *

# WS_URL 支持环境变量直接覆盖（Docker 部署最稳方式，如 ws://aurorabot:3001）
WS_URL = os.getenv('WS_URL', WS_URL)

try:
    import yaml
    with open("./config/_config.yml", "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        QQ_ADMIN = QQ_ADMIN if QQ_ADMIN else config['basic_settings']['QQbot_admin_account']
except Exception as e:
    logs.error(f"Failed to load config from _config.yml with Error: {e}")
