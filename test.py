import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LinearSegmentedColormap

class TableImageGenerator:
    """专门用于生成表格图片的类"""
    
    def __init__(self):
        """初始化基本样式设置"""
        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei'] 
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建自定义深色渐变颜色映射
        colors = ["#1a1a1a", "#2d2d2d", "#1a1a1a"]
        self.cmap = LinearSegmentedColormap.from_list("custom_dark", colors, N=256)
    
    def generate_commodity_table(self, data, title="商品信息概览"):
        """
        生成商品列表表格图片
        :param data: 商品数据字典
        :param title: 表格标题
        :return: matplotlib Figure对象
        """
        df = pd.DataFrame(data)
        
        fig = plt.figure(figsize=(12, 10), facecolor='#0C0C0C')
        ax = plt.subplot(111)
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')
        
        # 绘制主表格
        table = plt.table(
            cellText=df.values,
            colLabels=df.columns,
            cellLoc='center',
            loc='center',
            colColours=['#333333']*len(df.columns),
            cellColours=[[self.cmap(0.2)]*len(df.columns)]*len(df),
            bbox=[0, 0, 1, 1]
        )
        
        self._style_table(table)
        
        # 添加标题到最上方
        plt.title(title, 
                 fontsize=18, 
                 color='#FF9900',
                 pad=20,
                 fontweight='bold')
        
        # 调整表格占满整个图片
        plt.subplots_adjust(left=0, right=1, top=0.9, bottom=0)
        return fig
    
    def generate_user_inventory_table(self, data, stats, title="用户持有物品"):
        """
        生成用户持有物品表格图片
        :param data: 物品数据字典
        :param stats: 统计信息字典
        :param title: 表格标题
        :return: matplotlib Figure对象
        """
        df = pd.DataFrame(data)
        stats_df = pd.DataFrame(stats)
        
        fig = plt.figure(figsize=(12, 10), facecolor='#0C0C0C')
        ax = plt.subplot(111)
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')
        
        # 绘制统计信息表格（移到上方）
        stats_table = plt.table(
            cellText=stats_df.values,
            colLabels=stats_df.columns,
            cellLoc='center',
            loc='top',
            colColours=['#444444']*len(stats_df.columns),
            cellColours=[[self.cmap(0.3)]*len(stats_df.columns)]*len(stats_df),
            bbox=[0.1, 0.8, 0.8, 0.15]  # 增加高度并调整垂直位置
        )
        
        self._style_table(stats_table)
        
        # 绘制主表格（调整位置）
        table = plt.table(
            cellText=df.values,
            colLabels=df.columns,
            cellLoc='center',
            loc='center',
            colColours=['#444444']*len(df.columns),
            cellColours=[[self.cmap(0.3)]*len(df.columns)]*len(df),
            bbox=[0.1, 0.15, 0.8, 0.65]  # 增加底部留白并调整高度
        )
        
        self._style_table(table)
        
        # 添加标题到最上方
        plt.title(title, 
                 fontsize=18, 
                 color='#FF9900',
                 pad=20,
                 fontweight='bold')
        
        # 调整整体边距参数
        plt.subplots_adjust(left=0.05, right=0.95, top=0.9, bottom=0.1)
        return fig
    
    def _style_table(self, table):
        """表格样式设置"""
        for key, cell in table.get_celld().items():
            cell.set_text_props(color='#FFFFFF', fontsize=12)
            cell.set_edgecolor('#555555')
            if key[0] == 0:  # 表头行
                cell.set_text_props(weight='bold', color='#FFEE88')
                cell.set_facecolor('#333333')

# 测试数据
commodity_data = {
    "插件名": [
        "DreamAction", "DreamAntiFake", "DreamAntiFly", "DreamCountdown", 
        "DreamExchange", "DreamRecipe", "DreamRobot", "DreamShowcase", 
        "DreamSpawners", "DreamTimer", "Legendinlay", "LegendJewelry", 
        "LegendMaid", "LegendStrengthen", "LegendTalent", "LegendTome",
        "HTAssist", "HTIdentity"
    ],
    "中文名": [
        "梦交互", "梦反压测", "梦飞控", "梦计时", "梦兑换", "梦配方", "梦机器人", 
        "梦展柜(页面)", "梦刷怪点", "梦调度", "传奇宝石", "传奇饰品", "传奇女仆", 
        "传奇强化", "传奇天赋", "传奇图鉴", "喵娃辅助", "喵娃鉴定"
    ],
    "售价": [
        "FL150", "免费", "FL50", "FL300", "FL350", "FL200", "免费", "FL250", 
        "免费", "FL100", "158", "88", "免费", "128", "58", "50", "免费", "128"
    ],
    "绑定信息": [
        "暂未绑定", "暂未绑定", "暂未绑定", "暂未绑定", "暂未绑定", "暂未绑定", 
        "暂未绑定", "电信", "电信", "暂未绑定", "电信", "暂未绑定", "暂未绑定", 
        "暂未绑定", "暂未绑定", "暂未绑定", "暂未绑定", "电信"
    ]
}

user_stats = {
    "项目": ["QQ", "消费额", "贵族等级", "插件数量", "当前排名"],
    "值": ["3014617667", "¥610.0", "5级", "18", "305"]
}

if __name__ == "__main__":
    # 测试商品表格
    generator = TableImageGenerator()
    fig1 = generator.generate_commodity_table(commodity_data)
    fig1.savefig('commodity_table.png', dpi=120, facecolor='#0C0C0C')
    
    # 测试用户持有表格
    fig2 = generator.generate_user_inventory_table(commodity_data, user_stats)
    fig2.savefig('user_inventory.png', dpi=120, facecolor='#0C0C0C')
    
    plt.show()
