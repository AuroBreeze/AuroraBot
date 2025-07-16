import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

class CommodityVisualizer:
    """商品信息可视化生成器"""

    def __init__(self):
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei']
        plt.rcParams['axes.unicode_minus'] = False
        colors = ["#1a1a1a", "#2d2d2d", "#1a1a1a"]
        self.cmap = LinearSegmentedColormap.from_list("custom_dark", colors, N=256)

    def generate_commodity_list(self, commodities, title="上架商品列表"):
        df = pd.DataFrame({
            "名称": [c["name"] for c in commodities],
            "备注": [c.get("notes", "无") for c in commodities],
            "价格": [f"{c['price']:.2f}" for c in commodities],
            "福利": ["是" if c.get("is_welfare", False) else "否" for c in commodities]
        })

        # 行高和标题高度设定
        row_height = 0.5
        title_height = 0.2 if len(df) == 1 else 0.1
        fig_height = max(row_height * len(df) + 1.2, row_height * len(df) + title_height + 0.5)

        fig = plt.figure(figsize=(12, fig_height), facecolor='#0C0C0C')
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')

        # 绘制标题
        title_table = plt.table(
            cellText=[[title]],
            colWidths=[1.0],
            loc='upper center',
            cellLoc='center',
            bbox=[0, 1 - title_height, 1, title_height]
        )
        title_cell = title_table[0, 0]
        title_cell.set_text_props(color='#FFCC00', weight='bold', fontsize=18)
        title_cell.set_facecolor('#222222')
        title_cell.set_edgecolor('#444444')

        # 绘制数据表格
        table_bbox = [0, 0, 1, 1 - title_height]
        table = plt.table(
            cellText=df.values,
            colLabels=df.columns,
            cellLoc='center',
            colColours=['#333333'] * len(df.columns),
            cellColours=[
                [self.cmap(0.3)] * len(df.columns)
            ] + [
                [self.cmap(0.2)] * len(df.columns) for _ in range(len(df) - 1)
            ],
            bbox=table_bbox
        )
        self._style_table(table)
        return fig

    def generate_user_info(self, user_data, title="用户信息"):
        stats_df = pd.DataFrame({
            "名称": ["总消费金额", "持有商品数"],
            "值": [f"{user_data['total_spent']:.2f}", str(user_data['plugin_count'])]
        })
        plugin_list = user_data.get("plugins", [])
        plugin_df = pd.DataFrame({
            "名称": [p["name"] for p in plugin_list],
            "备注": [p.get("notes", "无") for p in plugin_list],
            "价格": [f"{p['price']:.2f}" for p in plugin_list],
            "福利": ["是" if p.get("is_welfare", False) else "否" for p in plugin_list]
        })

        # 动态高度与归一化处理
        row_height = 0.6  # 绝对行高inch
        title_height_ratio = 0.2 if (len(stats_df) + len(plugin_df) == 1) else 0.1
        total_rows = len(stats_df) + len(plugin_df)
        fig_height = max(row_height * total_rows + 1.5, row_height * total_rows + 0.5)

        fig = plt.figure(figsize=(12, fig_height), facecolor='#0C0C0C')
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor('#0C0C0C')
        ax.axis('off')

        # 标题区域
        title_table = plt.table(
            cellText=[[title]],
            colWidths=[1.0],
            cellLoc='center',
            bbox=[0, 1 - title_height_ratio, 1, title_height_ratio]
        )
        title_cell = title_table[0, 0]
        title_cell.set_text_props(color='#FFCC00', weight='bold', fontsize=18)
        title_cell.set_facecolor('#222222')
        title_cell.set_edgecolor('#444444')

        # 计算剩余空间比例
        remaining = 1 - title_height_ratio
        stats_height_ratio = remaining * len(stats_df) / total_rows
        plugin_height_ratio = remaining * len(plugin_df) / total_rows

        # 绘制用户统计表
        stats_bbox = [0, plugin_height_ratio, 1, stats_height_ratio]
        stats_table = plt.table(
            cellText=stats_df.values,
            colLabels=stats_df.columns,
            cellLoc='center',
            colColours=['#444444'] * len(stats_df.columns),
            cellColours=[
                [self.cmap(0.3)] * len(stats_df.columns)
            ] + [
                [self.cmap(0.2)] * len(stats_df.columns) for _ in range(len(stats_df) - 1)
            ],
            bbox=stats_bbox
        )
        self._style_table(stats_table)

        # 绘制插件列表表
        plugin_bbox = [0, 0, 1, plugin_height_ratio]
        plugin_table = plt.table(
            cellText=plugin_df.values,
            colLabels=plugin_df.columns,
            cellLoc='center',
            colColours=['#444444'] * len(plugin_df.columns),
            cellColours=[
                [self.cmap(0.3)] * len(plugin_df.columns)
            ] + [
                [self.cmap(0.2)] * len(plugin_df.columns) for _ in range(len(plugin_df) - 1)
            ],
            bbox=plugin_bbox
        )
        self._style_table(plugin_table)
        return fig

    def _style_table(self, table):
        for (row, col), cell in table.get_celld().items():
            cell.set_text_props(color='#FFFFFF', fontsize=12)
            cell.set_edgecolor('#555555')
            if row == 0:
                cell.set_text_props(weight='bold', color='#FFEE88')
                cell.set_facecolor('#333333')
            else:
                cell.set_facecolor(self.cmap(0.2 + 0.05 * (row % 2)))

    def save_figure(self, fig, filename):
        import os
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(filename)[0]
        new_filename = f"{base_name}_{timestamp}.png"
        os.makedirs("pic", exist_ok=True)
        fig.savefig(f"pic/{new_filename}", dpi=120, facecolor='#0C0C0C', bbox_inches='tight')
        plt.close(fig)
        return f"pic/{new_filename}"


if __name__ == "__main__":
    test_commodities = [
        {"name": "插件1", "notes": "测试插件1", "price": 10.0, "is_welfare": False},
        {"name": "插件2", "notes": "测试插件2", "price": 20.0, "is_welfare": True},
        {"name": "插件3", "notes": "测试插件3", "price": 15.0, "is_welfare": False},
        {"name": "插件4", "notes": "测试插件4", "price": 25.0, "is_welfare": True},
        {"name": "插件5", "notes": "测试插件5", "price": 30.0, "is_welfare": False},
        {"name": "插件6", "notes": "测试插件6", "price": 18.0, "is_welfare": True},
        {"name": "插件7", "notes": "测试插件7", "price": 22.0, "is_welfare": False},
        {"name": "插件8", "notes": "测试插件8", "price": 28.0, "is_welfare": True},
        {"name": "插件9", "notes": "测试插件9", "price": 35.0, "is_welfare": False},
        {"name": "插件10", "notes": "测试插件10", "price": 40.0, "is_welfare": True},
        {"name": "插件11", "notes": "测试插件11", "price": 12.0, "is_welfare": False},
        {"name": "插件12", "notes": "测试插件12", "price": 19.0, "is_welfare": True}
    ]

    test_user = {
        "total_spent": 300.0,
        "plugin_count": 12,
        "plugins": test_commodities[:10]
    }

    visualizer = CommodityVisualizer()
    fig1 = visualizer.generate_commodity_list(test_commodities[:10])
    visualizer.save_figure(fig1, "commodity_list.png")

    fig2 = visualizer.generate_user_info(test_user)
    visualizer.save_figure(fig2, "user_info.png")
