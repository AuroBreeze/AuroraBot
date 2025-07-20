
from app.Lssuing.services.auth.auth import AuthManager
from app.Lssuing.services.sql.store_db import Store_db
from api.Logger_owner import Logger


class Auth:
    def __init__(self):
        self.logger = Logger('Proxy_talk.admin.auth')
    def check_cfg(self) -> tuple[bool,str]:
        """
        检查配置文件是否正确
        """
        from ..proxy_cfg import time_interval,add_text
        #print(time_interval,add_text)

        if time_interval <= 0:
            self.logger.debug("定时发送间隔必须大于0")
            return False, "定时发送间隔必须大于0"

        if add_text == "":
            self.logger.debug("定时发送内容不能为空")
            return False, "定时发送内容不能为空"

        return True, None
    def check_msg(self,msg:dict) -> tuple[bool,str]:
        """
        检查消息是否为群组消息

        :param msg: 收到的消息
        :return: 布尔值和字符串
        """
        group_id = str(msg.get('group_id'))
        if not group_id:
            self.logger.debug("非群组消息")
            return False, None
        
        check_judge, check_msg = Store_db().check_group_permission(group_id)
        if not check_judge:
            self.logger.debug(check_msg)
            return False, None
        else:
            return True, None

    def check_auth(self,group_id:str,user_id:str,level:int = 1) -> tuple[bool,str]:
        # 检查用户权限
        check_judge, check_msg = AuthManager().permission_evaluation_and_assessment(group_id, user_id,int(level))
        if not check_judge:
            return False, check_msg
        return True,None