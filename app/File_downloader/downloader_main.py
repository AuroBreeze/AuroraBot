# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import re
import asyncio
import json
from typing import Tuple, Optional

from api.Logger_owner import Logger
from . import config as fd_cfg
from api.Botapi import QQAPI_list


class FileDownloader:
    def __init__(self, websocket, message: dict):
        self.logger = Logger(log_name='FileDownloader')
        self.websocket = websocket
        self.message = message if isinstance(message, dict) else json.loads(str(message))

    async def handle_event(self):
        """
        事件入口（静默模式）：
        - 设置群下载目录: "设置群下载目录 <绝对或相对路径>" 或 "#gsetdir <path>"（不回消息）
        - 自动收录：任何群成员发送含有图片/文件 URL 的段，自动保存到该群目录（不回消息）
        """
        try:
            # 示例：读取 app 其他目录（演示跨模块导入/读取）
            self.example_read_other_app()

            raw_msg = str(self.message.get('raw_message', '')).strip()
            group_id = str(self.message.get('group_id', ''))
            user_id = str(self.message.get('user_id', ''))

            # 仅处理群聊消息：如果不是群聊则直接返回（不做任何处理）
            msg_type = self.message.get('message_type')
            if msg_type is not None and msg_type != 'group':
                return
            if not group_id:
                return

            # 管理员菜单：展示文件收录功能菜单
            if raw_msg in ("#fd menu", "菜单", "FD菜单") and fd_cfg.is_admin(user_id):
                menu_text = (
                    "[FileDownloader 菜单]\n"
                    "1) 设置群下载目录 <路径>  或  #gsetdir <path>  [管理员]\n"
                    "2) 设置默认根目录 <路径>  或  #fd setroot <path>  [管理员]\n"
                    "3) 开启下载 / 关闭下载  或  #fd on / #fd off  [管理员]\n"
                    "4) 自动静默收录群内图片/文件到本地目录（非阻塞）\n"
                    "5) 仅处理群聊消息；设置目录/开关/根目录仅管理员可用\n"
                    f"当前状态: {'已开启' if fd_cfg.DOWNLOAD_ENABLED else '已关闭'}\n"
                )
                try:
                    await QQAPI_list(self.websocket).send_group_message(group_id, menu_text)
                except Exception:
                    pass
                return

            # 0) 管理员控制总开关（保留，不回消息）
            await self.toggle_global_switch(user_id, raw_msg)

            # 0.5) 管理员设置全局默认根目录（影响未自定义目录的群）
            await self.set_default_root_dir(user_id, raw_msg)

            # 1) 设置群下载目录（仅管理员，静默）
            await self.set_group_download_dir(user_id, group_id, raw_msg)

            # 2) 自动收录（静默）：开启时或默认均尝试
            force = True if fd_cfg.DOWNLOAD_ENABLED else False  # 总是尝试自动收录
            await self.try_download_incoming(user_id, group_id, force=force)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.logger.error(f"FileDownloader 处理异常: {e}")

    def example_read_other_app(self):
        """
        示例：读取 app 其他目录的内容（安全演示，不依赖其存在的具体变量）
        - 尝试导入 `app.Proxy_talk.proxy_cfg` 并读取其属性名列表
        仅做日志演示，不影响主流程
        """
        try:
            from app.Proxy_talk import proxy_cfg  # 跨目录读取示例
            attrs = dir(proxy_cfg)
            self.logger.debug(f"跨目录读取示例: 已读取 proxy_cfg 中 {len(attrs)} 个属性")
        except Exception as _:
            # 不影响主流程
            pass

    async def set_group_download_dir(self, user_id: str, group_id: str, raw_msg: str) -> None:
        """
        解析并设置群下载目录（静默）
        支持指令：
        - 设置群下载目录 <path>
        - #gsetdir <path>
        不返回提示，不发消息
        """
        if not raw_msg:
            return
        # 仅管理员可设置
        if not fd_cfg.is_admin(str(user_id)):
            return
        m = None
        if raw_msg.startswith('设置群下载目录 '):
            m = raw_msg.split(' ', 1)
        elif raw_msg.startswith('#gsetdir '):
            m = raw_msg.split(' ', 1)
        if not m or len(m) != 2:
            return

        input_path = m[1].strip().strip('"')
        if not input_path:
            return

        if os.path.isabs(input_path):
            target_dir = input_path
        else:
            target_dir = os.path.normpath(os.path.join(fd_cfg.DEFAULT_ROOT, input_path))

        try:
            os.makedirs(target_dir, exist_ok=True)
            fd_cfg.group_download_dirs[str(group_id)] = target_dir
            self.logger.info(f"为群{group_id}设置下载目录: {target_dir}")
        except Exception as e:
            self.logger.error(f"创建目录失败: {e}")


    async def toggle_global_switch(self, user_id: str, raw_msg: str) -> Optional[str]:
        """
        仅管理员可用：开启/关闭 全局自动下载开关（静默，不回消息）
        - 开启下载 / #fd on
        - 关闭下载 / #fd off
        返回提示或 None（供未来扩展）
        """
        if raw_msg not in ("开启下载", "关闭下载", "#fd on", "#fd off"):
            return None
        if not fd_cfg.is_admin(user_id):
            return None
        if raw_msg in ("开启下载", "#fd on"):
            fd_cfg.DOWNLOAD_ENABLED = True
            self.logger.info("全局自动下载：开启")
            return None
        else:
            fd_cfg.DOWNLOAD_ENABLED = False
            self.logger.info("全局自动下载：关闭")
            return None

    async def set_default_root_dir(self, user_id: str, raw_msg: str) -> None:
        """
        仅管理员：设置全局默认下载根目录（影响所有未单独设置目录的群）
        指令：
        - 设置默认下载目录 <path>
        - 设置默认根目录 <path>
        - #fd setroot <path>
        静默执行，不回消息
        """
        if not raw_msg:
            return
        if not fd_cfg.is_admin(str(user_id)):
            return
        prefixes = ("设置默认下载目录 ", "设置默认根目录 ", "#fd setroot ")
        matched = None
        for p in prefixes:
            if raw_msg.startswith(p):
                matched = raw_msg[len(p):].strip().strip('"')
                break
        if not matched:
            return
        new_root = matched
        # 允许绝对或相对路径；相对路径保持相对项目根
        try:
            target = os.path.normpath(new_root)
            os.makedirs(target, exist_ok=True)
            fd_cfg.DEFAULT_ROOT = target
            fd_cfg.DEFAULT_ROOT_SET = True
            self.logger.info(f"已设置全局默认下载根目录: {fd_cfg.DEFAULT_ROOT}")
        except Exception as e:
            self.logger.error(f"设置默认下载目录失败: {e}")

    async def try_download_incoming(self, user_id: str, group_id: str, force: bool = False) -> Tuple[bool, Optional[str]]:
        """
        自动收录：当消息包含图片/文件 URL，则保存到群目录（静默）。
        支持 segment 类型：image（data.url），以及尽量兼容其他包含url的段。
        返回 (是否触发了下载流程, 提示信息或None)
        """
        # 自动模式下总是尝试解析图片/文件 URL

        msg = self.message.get('message')
        if not msg or not isinstance(msg, list):
            return False, None

        # 查找第一个可下载的 URL
        url = None
        filename_hint = None
        for seg in msg:
            try:
                seg_type = seg.get('type')
                data = seg.get('data') or {}
                if seg_type == 'image' and data.get('url'):
                    url = data['url']
                    filename_hint = data.get('file') or 'image'
                    break
                # 兼容其他段（若未来OneBot等返回 file 段可以在此扩展）
                if data.get('url'):
                    url = data['url']
                    filename_hint = data.get('file') or seg_type or 'file'
                    break
            except Exception:
                continue

        if not url:
            return False, None

        # 解析群目录：
        # - 若该群有自定义目录，直接使用该目录
        # - 若管理员设置了默认根目录(DEFAULT_ROOT_SET=True)，则不再为每个群创建子目录，直接下载到默认根目录
        # - 否则使用默认根目录下的 group_<group_id>/ 子目录
        target_root = fd_cfg.group_download_dirs.get(str(group_id))
        if not target_root:
            if getattr(fd_cfg, 'DEFAULT_ROOT_SET', False):
                target_root = fd_cfg.DEFAULT_ROOT
            else:
                target_root = os.path.join(fd_cfg.DEFAULT_ROOT, f"group_{group_id}")
        os.makedirs(target_root, exist_ok=True)

        # 生成文件名：优先使用消息中携带的文件名；若缺失，尝试从 ./json/file.json 读取；不主动加时间戳，除非发生重名冲突
        import pathlib
        import json as _json
        orig_name = os.path.basename(filename_hint) if filename_hint else ''
        if not orig_name:
            try:
                with open(os.path.join('.', 'json', 'file.json'), 'r', encoding='utf-8') as jf:
                    jdata = _json.load(jf)
                    arr = jdata.get('message', [])
                    if arr and isinstance(arr, list):
                        d = (arr[0] or {}).get('data', {})
                        cand = d.get('file')
                        if isinstance(cand, str):
                            orig_name = cand
            except Exception:
                pass
        # 兜底扩展名
        if not orig_name:
            # 尝试从 URL 推断扩展名
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            path_name = os.path.basename(parsed.path)
            orig_name = path_name or 'file.bin'

        # 安全化文件名
        safe_name = re.sub(r"[^\w\.-]", "_", orig_name) or 'file.bin'
        save_path = os.path.join(target_root, safe_name)
        # 若重名，则添加序号避免覆盖
        if os.path.exists(save_path):
            base = pathlib.Path(safe_name).stem
            ext = pathlib.Path(safe_name).suffix
            idx = 1
            while True:
                candidate = f"{base}_{idx}{ext}"
                cpath = os.path.join(target_root, candidate)
                if not os.path.exists(cpath):
                    save_path = cpath
                    break
                idx += 1

        # 非阻塞下载：丢到后台线程执行，立即返回
        async def _schedule():
            try:
                await asyncio.to_thread(self._download_and_save, url, save_path)
                self.logger.info(f"文件已保存: {save_path}")
            except Exception as e:
                self.logger.error(f"下载失败: {e}")
        asyncio.create_task(_schedule())
        return True, None

    def _download_and_save(self, url: str, save_path: str) -> None:
        """同步下载保存函数，供后台线程调用"""
        import requests
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        # 确保父目录存在（双保险）
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(resp.content)
