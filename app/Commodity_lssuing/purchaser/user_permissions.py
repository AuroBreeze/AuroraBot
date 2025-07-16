from datetime import datetime, timedelta
from time import sleep
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store import Store
from .. import manage_cfg
from ..sql.store import Store
from ..creat_pic.main import CommodityVisualizer

class UserService_user_API:
    """群组服务层，封装所有user权限群组相关业务逻辑"""
    def __init__(self,websocket, message):
        self.logger = Logger("Commodity_admin_API")
        self.db = Store()
        self.service = UserService(self.db)
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return
        
        judge,msg_or_err = await self.service.list_available_commodities(self.message)
        if msg_or_err is not None:
            #await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)
            await QQAPI_list(self.websocket).send_pic_group(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.get_user_info(self.message)
        if msg_or_err is not None:
            if isinstance(msg_or_err, str) and msg_or_err.endswith('.png'):
                await QQAPI_list(self.websocket).send_pic_group(self.message.get("group_id"), msg_or_err)
            else:
                await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.show_help(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.show_wiki_url(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

class UserService:
    """群组服务层，封装所有群组相关业务逻辑"""
    def __init__(self, db: Store):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.bj_tz = pytz.timezone(manage_cfg.TIMEZONE)

    async def list_available_commodities(self, message: dict) -> tuple[bool, str]:
        """
        列出所有上架商品(用户可查看)
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "#list":
            self.logger.debug("无效的列出商品格式")
            return False, None

        try:
            # 获取所有上架商品
            active_plugins, err = self.db.list_plugins_state("TRUE")
            if err:
                return False, err
            
            if not active_plugins:
                return True, "当前没有上架商品"
            
            # 获取所有商品详细信息
            all_commodities, err = self.db.list_commodities()
            if err:
                return False, err
            
            # 过滤出上架商品
            active_plugin_names = {p["plugin_name"] for p in active_plugins}
            available_commodities = [
                c for c in all_commodities 
                if c["name"] in active_plugin_names
            ]
            
            if not available_commodities:
                return True, "当前没有上架商品"
            
            # 构建表格响应
            table_config = [
                {"header": "名称", "field": "name", "min_width": 15, "align": "<"},
                {"header": "备注", "field": "notes", "min_width": 20, "align": "<", "default": "无"},
                {"header": "价格", "field": "price", "min_width": 8, "align": "<", "format": "{:<8.2f}"},
                {"header": "福利", "field": "is_welfare", "min_width": 6, "align": "<", "format": lambda x: "是" if x else "否"}
            ]
            
            # 生成商品列表图片
            visualizer = CommodityVisualizer()
            fig = visualizer.generate_commodity_list(available_commodities)
            pic_path = visualizer.save_figure(fig, "commodity_list")
            return True, pic_path
        except Exception as e:
            self.logger.error(f"列出上架商品失败: {e}")
            return False, f"列出上架商品失败: {e}"
    
    def _build_commodity_table(self, commodities: list, columns: list) -> str:
        """
        动态构建商品表格
        
        :param commodities: 商品列表
        :param columns: 列配置列表
        :return: 格式化表格字符串
        """
        # 计算各列实际宽度
        col_widths = []
        for col in columns:
            max_val_len = max(len(str(c.get(col["field"], ""))) for c in commodities) if commodities else 0
            col_widths.append(max(max_val_len, len(col["header"]), col["min_width"]))
        
        # 构建表头
        header_parts = []
        for i, col in enumerate(columns):
            header_parts.append(f"{col['header']:{col['align']}{col_widths[i]}}")
        header = "  ".join(header_parts)
        
        # 构建分隔线 - 修改为按列宽动态构建
        separator_parts = []
        for i, width in enumerate(col_widths):
            separator_parts.append("-" * width)
        separator = "  ".join(separator_parts)
        
        # 构建数据行
        rows = []
        for item in commodities:
            row_parts = []
            for i, col in enumerate(columns):
                value = item.get(col["field"])
                
                # 处理空值
                if value is None:
                    value = col.get("default", "")
                
                # 应用格式化
                if "format" in col:
                    if callable(col["format"]):
                        value = col["format"](value)
                    else:
                        value = col["format"].format(value)
                
                row_parts.append(f"{value:{col['align']}{col_widths[i]}}")
            rows.append("  ".join(row_parts))
        
        # 组装完整响应
        return (
            "上架商品列表:\n" +
            separator + "\n" +
            header + "\n" +
            separator + "\n" +
            "\n".join(rows) + "\n" +
            separator
        )
    
    async def show_help(self, message: dict) -> tuple[bool, str]:
        """
        显示帮助信息
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "#help":
            return False, None

        help_text = """可用命令:
        
管理员命令(命令简写):
- #add_commodity(#ac) <名称> <价格> <备注> <是否福利(0/1)> - 添加商品
- #update_commodity(#uc) <名称> <价格> <备注> <是否福利(0/1)> - 更新商品
- #list_commodities_status(#lcs) - 列出商品状态(含福利信息)
- #update_status(#us) <插件ID> <1/0> - 更新插件状态
- #user_info(#ui) <QQ号> - 查看用户信息(含福利信息)
- #delete_commodity(#dc) <名称> - 删除商品
- #ap @群友 <插件名称>
- #wiki <URL> - 设置商品WIKI链接
- ##clean_pics(#cp) - 清理图片缓存

用户命令:
- #list - 列出上架商品(名称、价格和备注)
- #my_info - 查看我的信息(含插件列表)
- #wiki(#wk) - 查看WIKI链接
- #help - 显示本帮助

示例：
#ac 苹果 1.0 无 0
或者 
#add_commodity 苹果 1.0 无 0
"""
        return True, help_text

    async def get_user_info(self, message: dict) -> tuple[bool, str]:
        """
        获取用户信息(消费金额和拥有的插件)
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "#my_info":
            self.logger.debug("无效的用户信息查询格式")
            return False, None

        try:
            qq_id = str(message.get("user_id"))
            # 调用 get_purchase_records 方法时移除 group_id 参数
            user_info, err = self.db.list_user_info(qq_id)
            if err:
                return False, err
            
            if not user_info.get("plugins"):
                return True, "暂无消费记录和插件持有信息"
            
            print(user_info,err)
            
            # 生成用户信息图片
            visualizer = CommodityVisualizer()
            fig = visualizer.generate_user_info({
                "total_spent": user_info["total_spent"],
                "plugin_count": len(user_info["plugins"]),
                "plugins": user_info["plugins"]
            }, title=f"用户 {qq_id} 信息")
            
            pic_path = visualizer.save_figure(fig, "user_info")
            return True, pic_path
        except Exception as e:
            self.logger.error(f"获取用户信息失败: {e}")
            return False, f"获取用户信息失败: {e}"

    async def show_wiki_url(self, message: dict) -> tuple[bool, str]:
        """
        显示WIKI链接
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "#wiki" and msg != "#wk":
            self.logger.debug("无效的WIKI链接查询格式")
            return False, None

        try:
            from .. import manage_cfg
            if not manage_cfg.WIKI_URL:
                return True, "WIKI链接尚未设置"
            
            return True, f"WIKI链接: {manage_cfg.WIKI_URL}"
        except Exception as e:
            self.logger.error(f"获取WIKI链接失败: {e}")
            return False, f"获取WIKI链接失败: {e}"
