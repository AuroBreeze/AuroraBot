import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LinearSegmentedColormap

class CommodityVisualizer:
    """商品信息可视化生成器"""
    
    def __init__(self):
        """初始化基本样式设置"""
        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei'] 
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建自定义深色渐变颜色映射
        colors = ["#1a1a1a", "#2d2d2d", "#1a1a1a"]
        self.cmap = LinearSegmentedColormap.from_list("custom_dark", colors, N=256)
    
    def generate_commodity_list(self, commodities, title="上架商品列表"):
        """
        生成商品列表表格图片
        :param commodities: 商品列表数据 [{"name": str, "notes": str, "price": float, "is_welfare": bool}]
        :param title: 表格标题
        :return: matplotlib Figure对象
        """
        # 准备数据
        data = {
            "名称": [c["name"] for c in commodities],
            "备注": [c.get("notes", "无") for c in commodities],
            "价格": [f"{c['price']:.2f}" for c in commodities],
            "福利": ["是" if c.get("is_welfare", False) else "否" for c in commodities]
        }
        
        df = pd.DataFrame(data)
        
        fig = plt.figure(figsize=(12, 8), facecolor='#0C0C0C')
        ax = plt.subplot(111)
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')
        
        # 绘制表格
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
        
        # 添加标题
        plt.title(title, 
                 fontsize=18, 
                 color='#FF9900',
                 pad=20,
                 fontweight='bold')
        
        plt.subplots_adjust(left=0, right=1, top=0.9, bottom=0)
        return fig
    
    def generate_user_info(self, user_data, title="用户信息"):
        """
        生成用户信息表格图片
        :param user_data: 用户数据 {
            "total_spent": float,
            "plugin_count": int,
            "plugins": [{"name": str, "notes": str, "price": float, "is_welfare": bool}]
        }
        :param title: 表格标题
        :return: matplotlib Figure对象
        """
        # 准备统计数据
        stats = {
            "项目": ["总消费金额", "持有商品数"],
            "值": [f"{user_data['total_spent']:.2f}", str(user_data['plugin_count'])]
        }
        
        # 准备插件数据
        plugins = user_data["plugins"]
        plugin_data = {
            "名称": [p["name"] for p in plugins],
            "备注": [p.get("notes", "无") for p in plugins],
            "价格": [f"{p['price']:.2f}" for p in plugins],
            "福利": ["是" if p.get("is_welfare", False) else "否" for p in plugins]
        }
        
        stats_df = pd.DataFrame(stats)
        plugin_df = pd.DataFrame(plugin_data)
        
        fig = plt.figure(figsize=(12, 10), facecolor='#0C0C0C')
        ax = plt.subplot(111)
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')
        
        # 绘制统计信息表格
        stats_table = plt.table(
            cellText=stats_df.values,
            colLabels=stats_df.columns,
            cellLoc='center',
            loc='top',
            colColours=['#444444']*len(stats_df.columns),
            cellColours=[[self.cmap(0.3)]*len(stats_df.columns)]*len(stats_df),
            bbox=[0.1, 0.8, 0.8, 0.15]
        )
        
        self._style_table(stats_table)
        
        # 绘制插件表格
        if len(plugins) > 0:
            plugin_table = plt.table(
                cellText=plugin_df.values,
                colLabels=plugin_df.columns,
                cellLoc='center',
                loc='center',
                colColours=['#444444']*len(plugin_df.columns),
                cellColours=[[self.cmap(0.3)]*len(plugin_df.columns)]*len(plugin_df),
                bbox=[0.1, 0.15, 0.8, 0.65]
            )
            self._style_table(plugin_table)
        
        # 添加标题
        plt.title(title, 
                 fontsize=18, 
                 color='#FF9900',
                 pad=20,
                 fontweight='bold')
        
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

    def save_figure(self, fig, filename):
        """保存图片到文件"""
        import os
        from datetime import datetime
        
        # 生成时间戳格式文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(filename)[0]
        new_filename = f"{base_name}_{timestamp}.png"
        
        os.makedirs("pic", exist_ok=True)  # 确保pic目录存在
        fig.savefig(f"pic/{new_filename}", dpi=120, facecolor='#0C0C0C')
        plt.close(fig)
        return f"pic/{new_filename}"  # 返回完整文件路径

if __name__ == "__main__":
    # 测试数据
    test_commodities = [
        {"name": "插件1", "notes": "测试插件1", "price": 10.0, "is_welfare": False},
        {"name": "插件2", "notes": "测试插件2", "price": 20.0, "is_welfare": True}
    ]
    
    test_user = {
        "total_spent": 30.0,
        "plugin_count": 2,
        "plugins": test_commodities
    }
    
    # 测试生成图片
    visualizer = CommodityVisualizer()
    
    # 生成商品列表图片
    fig1 = visualizer.generate_commodity_list(test_commodities)
    visualizer.save_figure(fig1, "commodity_list.png")
    
    # 生成用户信息图片
    fig2 = visualizer.generate_user_info(test_user)
    visualizer.save_figure(fig2, "user_info.png")
