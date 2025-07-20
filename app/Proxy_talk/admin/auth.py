
from ..sql.store_proxy import StoreProxy
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
        user_id = str(msg.get('user_id'))
        if not user_id:
            self.logger.debug("无效用户ID")
            return False, None
        
        if not StoreProxy().is_authorized(user_id):
            self.logger.debug(f"用户{user_id}未授权")
            return False, None
        return True, None

    def check_auth(self,group_id:str,user_id:str,level:int = 1) -> tuple[bool,str]:
        """
        检查用户授权状态
        
        :param user_id: 用户QQ号
        :return: 已授权返回True，否则返回False
        """
        if not StoreProxy().is_authorized(user_id):
            self.logger.debug(f"用户{user_id}未授权")
            return False, None
        return True, None
