from config import env
import os

admin_id_list = [env.QQ_ADMIN,"916285843"]
DB_PATH = "./store/db/"# database path 数据库路径
TIMEZONE = 'Asia/Shanghai' # Timezone 时区

WIKI_URL = ""

os.makedirs(DB_PATH, exist_ok=True) # 创建数据库目录
