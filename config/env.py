# from config.environment.basic import *
from api import Logger_owner


logs = Logger_owner.Logger(log_name='ENV')
current_env = 'dev'

if current_env == 'dev':
    from config.environment.basic import *
else:
    from config.environment.prod import *

try:
    import yaml
    with open("./config/_config.yml", "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        QQ_ADMIN = QQ_ADMIN if QQ_ADMIN else config['basic_settings']['QQbot_admin_account']
        QQ_BOT = QQ_BOT if QQ_BOT else config['basic_settings']['QQbot_account']
except Exception as e:
    logs.error(f"Failed to load config from _config.yml with Error: {e}")
    


