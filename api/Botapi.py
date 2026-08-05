import asyncio
import json
import time
from api.Logger_owner import Logger

class QQAPI_list:
    def __init__(self,websocket):
        self.websocket = websocket
        self.Logger = Logger("BotAPI")
        # 统一 API 请求通道：echo -> asyncio.Future（由消息接收层 dispatch_response 投递响应）
        self._pending: dict[str, asyncio.Future] = {}

    # ---------- 统一请求通道 ----------

    async def _call(self, action: str, params: dict = None, timeout: float = 10.0) -> tuple[bool, object, str]:
        """
        统一 OneBot API 调用（OneBot 11 HTTP POST 协议，经 WS 传输）。
        通过唯一 echo 匹配响应，避免被服务器推送的事件抢占 recv 导致错乱。
        :return: (是否成功, data, message)
        """
        echo = f"{time.time_ns()}-{id(self)}"
        payload = {"action": action, "params": params or {}, "echo": echo}
        fut = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        try:
            await self.websocket.send(json.dumps(payload))
            response = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.Logger.error(f"API {action} 响应超时（{timeout}s）")
            return False, None, f"API {action} 响应超时"
        except Exception as e:
            self.Logger.error(f"API {action} 调用失败: {e}")
            return False, None, str(e)
        finally:
            self._pending.pop(echo, None)

        if response.get("status") == "ok":
            return True, response.get("data"), ""
        return False, None, response.get("message", "未知错误")

    def dispatch_response(self, echo: str, data: dict) -> None:
        """由消息接收层调用：把带 echo 的响应投递给等待中的 _call"""
        fut = self._pending.get(echo)
        if fut is not None and not fut.done():
            fut.set_result(data)

    async def call_api(self, action: str, params: dict = None) -> dict:
        """通用 API 调用（供上层直接使用）：返回响应 data（失败返回空 dict 并记日志）"""
        ok, data, msg = await self._call(action, params)
        if not ok:
            self.Logger.error(f"API {action} 失败: {msg}")
            return {}
        return data or {}
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
    async def send_group_message(self, group_id: str, message: str):
        """
        发送群消息；返回 message_id（供回复匹配等使用），失败返回 None
        """
        ok, data, msg = await self._call(
            "send_group_msg",
            {
                "group_id": str(group_id),
                "message": [{"type": "text", "data": {"text": message}}],
            },
        )
        if ok:
            self.Logger.info("发送群消息:%s,群号:%s" % (message, group_id))
            return (data or {}).get("message_id")
        self.Logger.error(f"发送群消息失败 群:{group_id}: {msg}")
        return None
    
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
        ok, data, msg = await self._call("get_group_list", {"no_cache": no_cache})
        if not ok:
            self.Logger.error(f"获取群列表失败: {msg}")
            return []
        return [str(g["group_id"]) for g in (data or [])]

    async def get_group_member_list(self, group_id: str) -> list:
        """
        获取群成员列表（OneBot get_group_member_list）
        成员 dict 含 role 字段: owner=群主, admin=管理员, member=成员
        """
        ok, data, msg = await self._call("get_group_member_list", {"group_id": str(group_id)})
        if not ok:
            self.Logger.error(f"获取群成员列表失败: {msg}")
            return []
        return data or []

    async def get_group_member_info(self, group_id: str, user_id: str, no_cache: bool = False) -> dict:
        """
        获取群成员信息（含 role: owner/admin/member、card 群名片、nickname）
        """
        ok, data, msg = await self._call(
            "get_group_member_info",
            {"group_id": str(group_id), "user_id": str(user_id), "no_cache": no_cache},
        )
        if not ok:
            self.Logger.error(f"获取群成员信息失败: {msg}")
            return {}
        return data or {}

    async def get_group_info(self, group_id: str, no_cache: bool = False) -> dict:
        """获取群信息"""
        ok, data, msg = await self._call("get_group_info", {"group_id": str(group_id), "no_cache": no_cache})
        if not ok:
            self.Logger.error(f"获取群信息失败: {msg}")
            return {}
        return data or {}

    async def set_group_kick_member(self, group_id: str, user_id: str, reject_add_request: bool = False) -> bool:
        """
        踢出群成员（NapCat set_group_kick_members 批量接口，传单成员）
        :param reject_add_request: 是否拒绝该用户再次入群
        """
        ok, _, msg = await self._call(
            "set_group_kick_members",
            {
                "group_id": str(group_id),
                "user_id": [str(user_id)],
                "reject_add_request": reject_add_request,
            },
        )
        if ok:
            self.Logger.info(f"已踢出成员 群:{group_id} 用户:{user_id}")
        else:
            self.Logger.error(f"踢出成员失败 群:{group_id} 用户:{user_id}: {msg}")
        return ok
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
    async def send_group_img(self, group_id: str, file_path: str) -> bool:
        """
        发送群图片
        """
        try:
            import base64
            with open(file_path, "rb") as image_file:
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
            self.Logger.info(f"已发送群图片,群号:{group_id},图片路径:{file_path}")
            # await asyncio.sleep(1.5)
            return True
        except Exception as e:
            self.Logger.error(f"发送群图片失败: {e}")
            return False

    async def send_group_message_array(self, group_id: str, message_array: list) -> bool:
        """
        发送群消息数组(包含图片和文本)
        会自动下载图片并使用base64编码发送
        
        :param group_id: 群号
        :param message_array: 消息数组，格式如:
            [
                {
                    "type": "image",
                    "data": {
                        "url": "https://...",
                        "file": "xxx.jpg"
                    }
                },
                {
                    "type": "text",
                    "data": {
                        "text": "xxx"
                    }
                }
            ]
        :return: 是否成功
        """
        try:
            
            # 发送处理后的消息
            json_message = {
                "action": "send_group_msg",
                "params": {
                    "group_id": str(group_id),
                    "message": message_array
                }
            }
            await self.websocket.send(json.dumps(json_message))
            self.Logger.info(f"已发送群消息数组,群号:{group_id},消息长度:{len(message_array)}")
            return True
            
        except Exception as e:
            self.Logger.error(f"发送群消息数组失败: {e}")
            return False
