import asyncio
import json
import time
from api.Logger_owner import Logger

class QQAPI_list:
    # 进程级共享的 API 响应注册表：任何实例发起的 _call 响应都能被 ws 接收层投递
    _pending: dict[str, asyncio.Future] = {}

    def __init__(self, websocket):
        self.websocket = websocket
        self.Logger = Logger("BotAPI")

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
        type(self)._pending[echo] = fut
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
            type(self)._pending.pop(echo, None)

        if response.get("status") == "ok":
            return True, response.get("data"), ""
        return False, None, response.get("message", "未知错误")

    def dispatch_response(self, echo: str, data: dict) -> None:
        """由消息接收层调用：把带 echo 的响应投递给等待中的 _call（类级共享）"""
        fut = type(self)._pending.get(echo)
        if fut is not None and not fut.done():
            fut.set_result(data)

    async def call_api(self, action: str, params: dict = None) -> dict:
        """通用 API 调用（供上层直接使用）：返回响应 data（失败返回空 dict 并记日志）"""
        ok, data, msg = await self._call(action, params)
        if not ok:
            self.Logger.error(f"API {action} 失败: {msg}")
            return {}
        return data or {}
    async def send_message(self, user_id: str, message: str):
        """
        发送私聊消息
        :param user_id: 用户id
        :param message: 消息内容
        :return: message_id；失败返回 None
        """
        ok, data, msg = await self._call(
            "send_private_msg",
            {"user_id": str(user_id), "message": [{"type": "text", "data": {"text": message}}]},
        )
        if ok:
            self.Logger.info("发送消息:%s,接收者:%s" % (message, user_id))
            return (data or {}).get("message_id")
        self.Logger.error(f"发送私聊消息失败 用户:{user_id}: {msg}")
        return None
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
    
    async def send_at_group(self, group_id: str, user_id: str):
        """
        发送群聊at（无正文，仅 @ 目标）
        :param group_id: 群号
        :param user_id: 用户id
        :return: message_id；失败返回 None
        """
        return await self.send_at_group_message(group_id, user_id, "")

    async def send_at_group_message(self, group_id: str, user_id: str, message: str):
        """
        发送群聊at消息（at 段后带空格，避免与正文粘连/解析异常）
        :param group_id: 群号
        :param user_id: 用户id
        :param message: 消息
        :return: message_id；失败返回 None
        """
        ok, data, msg = await self._call(
            "send_group_msg",
            {
                "group_id": str(group_id),
                "message": [
                    {"type": "at", "data": {"qq": str(user_id)}},
                    {"type": "text", "data": {"text": " "}},
                    {"type": "text", "data": {"text": message}},
                ],
            },
        )
        if ok:
            self.Logger.info(f"已发送群@消息,@{user_id},消息:{message}")
            return (data or {}).get("message_id")
        self.Logger.error(f"发送群@消息失败 群:{group_id} @{user_id}: {msg}")
        return None
    async def send_pic_group(self, group_id: str, pic_path: str):
        """
        发送群聊图片（委托 send_group_img，统一 base64 + _call 通道）
        :param group_id: 群号
        :param pic_path: 图片本地路径
        :return: 是否成功
        """
        return await self.send_group_img(group_id, pic_path)

    async def set_group_name(self, group_id: str, group_name: str) -> bool:
        """设置群名称"""
        ok, _, msg = await self._call("set_group_name", {"group_id": str(group_id), "group_name": str(group_name)})
        if ok:
            self.Logger.info(f"已设置群名称,群号:{group_id},名称:{group_name}")
        else:
            self.Logger.error(f"设置群名称失败: {msg}")
        return ok

    async def set_group_add_request(self, flag: str, approve: bool) -> bool:
        """处理加群申请（同意/拒绝）"""
        ok, _, msg = await self._call(
            "set_group_add_request", {"flag": str(flag), "approve": approve, "reason": "string"}
        )
        if ok:
            self.Logger.info(f"已设置群添加请求,flag:{flag},approve:{approve}")
        else:
            self.Logger.error(f"设置群添加请求失败: {msg}")
        return ok
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
    async def set_group_leave(self, group_id: str, is_dismiss: bool = True) -> bool:
        """退出群聊"""
        ok, _, msg = await self._call(
            "set_group_leave", {"group_id": str(group_id), "is_dismiss": is_dismiss}
        )
        if ok:
            self.Logger.info(f"已退出群聊,群号:{group_id},是否解散:{is_dismiss}")
        else:
            self.Logger.error(f"退出群聊失败: {msg}")
        return ok

    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> bool:
        """处理加好友请求"""
        ok, _, msg = await self._call(
            "set_friend_add_request", {"flag": str(flag), "approve": approve, "remark": str(remark)}
        )
        if ok:
            self.Logger.info(f"已处理加好友请求,flag:{flag},approve:{approve},remark:{remark}")
        else:
            self.Logger.error(f"处理加好友请求失败: {msg}")
        return ok

    async def set_group_card(self, group_id: str, user_id: str, card: str = "") -> bool:
        """设置群名片"""
        ok, _, msg = await self._call(
            "set_group_card", {"group_id": str(group_id), "user_id": str(user_id), "card": str(card)}
        )
        if ok:
            self.Logger.info(f"已设置群名片,群号:{group_id},用户id:{user_id},名片:{card}")
        else:
            self.Logger.error(f"设置群名片失败: {msg}")
        return ok

    async def set_self_avatar(self, file_path: str) -> bool:
        """设置自己的头像"""
        try:
            import base64
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            ok, _, msg = await self._call("set_qq_avatar", {"file": f"base64://{encoded_string}"})
            if ok:
                self.Logger.info(f"已设置自己的头像,头像路径:{file_path}")
            else:
                self.Logger.error(f"设置自己的头像失败: {msg}")
            return ok
        except OSError as e:
            self.Logger.error(f"设置自己的头像失败: {e}")
            return False

    async def send_group_img(self, group_id: str, file_path: str) -> bool:
        """发送群图片（本地文件 → base64 → _call 统一通道）"""
        try:
            import base64
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            ok, _, msg = await self._call(
                "send_group_msg",
                {
                    "group_id": str(group_id),
                    "message": [{"type": "image", "data": {"file": f"base64://{encoded_string}", "summary": "[图片]"}}],
                },
            )
            if ok:
                self.Logger.info(f"已发送群图片,群号:{group_id},图片路径:{file_path}")
            else:
                self.Logger.error(f"发送群图片失败: {msg}")
            return ok
        except OSError as e:
            self.Logger.error(f"发送群图片失败: {e}")
            return False

    async def send_group_message_array(self, group_id: str, message_array: list) -> bool:
        """
        发送群消息数组（图片/文本等，原样透传 message 数组）
        :param group_id: 群号
        :param message_array: 消息数组（OneBot message 段列表）
        :return: 是否成功
        """
        ok, _, msg = await self._call(
            "send_group_msg",
            {"group_id": str(group_id), "message": message_array},
        )
        if ok:
            self.Logger.info(f"已发送群消息数组,群号:{group_id},消息长度:{len(message_array)}")
        else:
            self.Logger.error(f"发送群消息数组失败: {msg}")
        return ok
