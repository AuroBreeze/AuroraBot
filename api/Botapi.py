import asyncio
import json
from api.Logger_owner import Logger

class QQAPI_list:
    def __init__(self,websocket):
        self.websocket = websocket
        self.Logger = Logger("BotAPI")
    async def send_message(self,user_id:str,message:str): #发送私聊消息
        """
        发送私聊消息
        :param user_id: 用户id
        :param message: 消息内容
        :return: None
        """
        json_message = {
            "action": "send_private_msg",
            "params":{
                "user_id": str(user_id),
                "message": [{
                    "type": "text",
                    "data": {
                        "text": message
                    }
                    }],
            }
        }
        await self.websocket.send(json.dumps(json_message))
        self.Logger.info("发送消息:%s,接收者:%s"%(message,user_id))
        # await asyncio.sleep(2)
    async def send_group_message(self,group_id:str,message:str):
        """
        发送群消息

        :param group_id:群号
        :param message:消息
        :return: None
        """

        json_message = {
            "action": "send_group_msg",
            "params":{
                "group_id": group_id,
                "message": [
                    {
                        "type": "text",
                        "data": {
                            "text": message
                        }
                     }
                ]
                }
        }
        await self.websocket.send(json.dumps(json_message))
        self.Logger.info("发送群消息:%s,群号:%s"%(message,group_id))
        # await asyncio.sleep(1.5)
    
    async def send_at_group(self,group_id:str,user_id:str):
        """
        发送群聊at

        :param group_id:群号
        :param user_id:用户id
        :return: None
        """

        json_message = {
            "action": "send_group_msg",
            "params":{
                    "group_id": group_id,
                    "message": [
                        {
                            "type": "at",
                            "data": {
                                "qq": user_id
                            }
                        }
                    ]
                }
        }
        await self.websocket.send(json.dumps(json_message))
        self.logger.info(f"已发送群@消息,@{user_id}")
        # await asyncio.sleep(1.5)
    async def send_at_group_message(self,group_id:str,user_id:str,message:str):
        """
        发送群聊at消息

        :param group_id:群号
        :param user_id:用户id
        :param message:消息
        :return: None
        """

        json_message = {
            "action": "send_group_msg",
            "params":{
                    "group_id": group_id,
                    "message": [
                        {
                            "type": "at",
                            "data": {
                                "qq": user_id
                            }
                        },
                        {
                            "type": "text",
                            "data": {
                                "text": message
                            }
                        }
                    ]
                }
            }
        await self.websocket.send(json.dumps(json_message))
        self.Logger.info(f"已发送群@消息,@{user_id},消息:{message}")
        # await asyncio.sleep(1.5)
    async def send_pic_group(self, group_id: str, pic_path: str):
        """
        发送群聊图片
        :param group_id: 群号
        :param pic_path: 图片本地路径
        """
        import base64
        
        try:
            with open(pic_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            json_message = {
                "action": "send_group_msg",
                "params": {
                    "group_id": str(group_id),
                    "message": [{
                        "type": "image",
                        "data": {
                            "file": f"base64://{encoded_string}",
                            "summary": "[图片]"
                        }
                    }]
                }
            }
            
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已发送群图片,群号:{group_id},图片:{pic_path}")
            # await asyncio.sleep(1.5)
        except Exception as e:
            self.Logger.error(f"发送图片失败: {e}")
            raise
    async def set_group_name(self, group_id: str, group_name: str):
        """
        设置群名称
        """
        try:
            
            json_message = {
                "action": "set_group_name",
                "params": {
                        "group_id": str(group_id),
                        "group_name": str(group_name)
                        }
                }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已设置群名称,群号:{group_id},名称:{group_name}")
            # await asyncio.sleep(1.5)
        except Exception as e:
            self.Logger.error(f"设置群名称失败: {e}")
            raise
    async def set_group_add_request(self, flag: str, approve: bool):
        """
        设置群名称
        """
        try:
            
            json_message = {
                "action": "set_group_add_request",
                "params": {
                        "flag": str(flag),
                        "approve": approve,
                        "reason": "string"
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已设置群添加请求,flag:{flag},approve:{approve}")
            # await asyncio.sleep(1.5)
        except Exception as e:
            self.Logger.error(f"设置群添加请求失败: {e}")
            raise
    async def get_group_list(self, no_cache: bool = False) -> list:
        """
        获取群列表
        返回群组ID列表
        """
        try:
            json_message = {
                "action": "get_group_list",
                "params": {
                        "no_cache": no_cache
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            
            # 等待并处理响应
            response = await self.websocket.recv()
            data = json.loads(response)
            
            if data.get("status") == "ok":
                groups = data.get("data", [])
                return [str(g["group_id"]) for g in groups]
                
            self.Logger.error(f"获取群列表失败: {data.get('message', '未知错误')}")
            return []
        except Exception as e:
            self.Logger.error(f"获取群列表失败: {e}")
            return []
    async def set_group_leave(self, group_id: str, is_dismiss: bool = True):
        """
        退出群聊
        """
        try:
            json_message = {
                "action": "set_group_leave",
                "params": {
                        "group_id": str(group_id),
                        "is_dismiss": is_dismiss
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已退出群聊,群号:{group_id},是否解散:{is_dismiss}")
            # await asyncio.sleep(1.5)
        except Exception as e:
            self.Logger.error(f"退出群聊失败: {e}")
            raise
    
    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = ""):
        """
        处理加好友请求
        """
        try:
            json_message = {
                "action": "set_friend_add_request",
                "params": {
                        "flag": str(flag),
                        "approve": approve,
                        "remark": str(remark)
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已处理加好友请求,flag:{flag},approve:{approve},remark:{remark}")
            # await asyncio.sleep(1.5)
        except Exception as e:
            self.Logger.error(f"处理加好友请求失败: {e}")
            raise

    async def set_group_card(self, group_id: str, user_id: str, card: str = ""):
        """
        设置群名片
        """
        try:
            json_message = {
                "action": "set_group_card",
                "params": {
                        "group_id": str(group_id),
                        "user_id": str(user_id),
                        "card": str(card)
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已设置群名片,群号:{group_id},用户id:{user_id},名片:{card}")
            # await asyncio.sleep(1.5)
            return True
        except Exception as e:
            self.Logger.error(f"设置群名片失败: {e}")
            return False
    
    async def set_self_avatar(self, file_path: str):
        """
        设置自己的头像
        """
        try:
            import base64
            
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            json_message = {
                "action": "set_qq_avatar",
                "params": {
                        "file": f"base64://{encoded_string}"
                        }
                    }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已设置自己的头像,头像路径:{file_path}")
            # await asyncio.sleep(1.5)
            return True
        except Exception as e:
            self.Logger.error(f"设置自己的头像失败: {e}")
            return False
