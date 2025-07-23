#!/bin/bash

# 设置工作目录
WORK_DIR="/home"
# 查找所有以 QQbot_ 开头的文件夹
BOT_DIRS=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))

# 检查是否找到任何目录
if [ ${#BOT_DIRS[@]} -eq 0 ]; then
    echo "未找到任何 QQbot_* 目录"
    exit 1
fi

# 初始化计数器
counter=1
success_count=0
fail_count=0

echo "开始处理 ${#BOT_DIRS[@]} 个目录..."

# 遍历所有找到的 QQbot 文件夹
for dir in "${BOT_DIRS[@]}"; do
    # 构建目标文件路径
    target_file="$dir/app/Proxy_talk/admin/command.py"
    
    # 检查文件是否存在
    if [[ -f "$target_file" ]]; then
        # 备份原文件
        cp "$target_file" "$target_file.bak"
        
        # 确定替换字符串（第一个文件为 添加文件1，后续为 #wf2, #wf3...）

        old_command1="添加文件1"
        new_command1="添加文件$counter"
        old_command2="更新头像1"
        new_command2="更新头像$counter"

        fi
        
        # 检查文件中是否包含需要替换的字符串
        if grep -q "$old_command1\|$old_command2" "$target_file"; then
            # 执行替换操作
            sed -i "s/$old_command1/$new_command1/g" "$target_file"
            sed -i "s/$old_command2/$new_command2/g" "$target_file"
            
            # 检查替换结果
            if grep -q "$new_command1\|$new_command2" "$target_file"; then
                echo "成功修改: $target_file -> $new_command1 和 $new_command2"
                ((success_count++))
            else
                echo "修改失败: $target_file"
                # 恢复备份文件
                mv "$target_file.bak" "$target_file"
                ((fail_count++))
            fi
        else
            echo "文件中未找到目标字符串: $target_file"
            # 删除备份文件
            rm "$target_file.bak"
            ((fail_count++))
        fi
        
        # 增加计数器
        ((counter++))
    else
        echo "文件不存在: $target_file"
        ((fail_count++))
    fi
done

echo "处理完成! 成功: $success_count, 失败: $fail_count"