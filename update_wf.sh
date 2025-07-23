#!/bin/bash

# 设置工作目录
WORK_DIR="/home"

# 修改command.py函数
modify_command_py() {
    local file="$1"
    local old_cmd1="$2"
    local new_cmd1="$3"
    local old_cmd2="$4"
    local new_cmd2="$5"
    
    if grep -q "$new_cmd1\|$new_cmd2" "$file"; then
        echo "command.py已包含新命令，跳过修改: $new_cmd1 和 $new_cmd2"
        return 1
    fi
    
    if grep -q "$old_cmd1\|$old_cmd2" "$file"; then
        cp "$file" "$file.bak"
        sed -i "s/$old_cmd1/$new_cmd1/g" "$file"
        sed -i "s/$old_cmd2/$new_cmd2/g" "$file"
        
        if grep -q "$new_cmd1\|$new_cmd2" "$file"; then
            echo "成功修改command.py: $file -> $new_cmd1 和 $new_cmd2"
            return 0
        else
            echo "command.py修改失败: $file"
            mv "$file.bak" "$file"
            return 2
        fi
    else
        echo "command.py文件中未找到目标字符串: $file"
        return 3
    fi
}

# 修改docker-compose.yml函数
modify_docker_compose() {
    local file="$1"
    local container_name="$2"
    local service_name="$3"
    local app_name="$4"
    local port="$5"
    
    if grep -q "$container_name\|$service_name\|$app_name" "$file" && grep -q "${port}:6099" "$file"; then
        echo "docker-compose.yml已包含新配置，跳过修改"
        return 1
    fi
    
    cp "$file" "$file.bak"
    sed -i "s/container_name: Bot/container_name: $container_name/" "$file"
    sed -i "s/aurorabot:/"$service_name:"/" "$file"
    sed -i "s/container_name: AuroraBot/container_name: $app_name/" "$file"
    sed -i "s/- aurorabot/- $service_name/" "$file"
    sed -i "s/- 6099:6099/- ${port}:6099/" "$file"
    
    if grep -q "$container_name\|$service_name\|$app_name" "$file" && grep -q "${port}:6099" "$file"; then
        echo "成功修改docker-compose.yml: $container_name、$service_name、$app_name 和端口 $port"
        return 0
    else
        echo "docker-compose.yml修改失败: $file"
        mv "$file.bak" "$file"
        return 2
    fi
}

# 修改prod.py函数
modify_prod_py() {
    local file="$1"
    local service_name="$2"
    
    if grep -q "$service_name" "$file"; then
        echo "prod.py已包含新配置，跳过修改"
        return 1
    fi
    
    cp "$file" "$file.bak"
    sed -i "s/aurorabot:/$service_name:/" "$file"
    
    if grep -q "$service_name" "$file"; then
        echo "成功修改prod.py中的WS_URL: $service_name"
        return 0
    else
        echo "prod.py修改失败: $file"
        mv "$file.bak" "$file"
        return 2
    fi
}

# 创建version文件函数
create_version_file() {
    local dir="$1"
    local counter="$2"
    local version_file="$dir/${counter}.version"
    
    echo "$counter" > "$version_file"
    if [[ -f "$version_file" ]]; then
        echo "成功创建version文件: $version_file"
        return 0
    else
        echo "创建version文件失败: $version_file"
        return 1
    fi
}

# 删除version文件函数
remove_version_file() {
    local dir="$1"
    local version_file="$dir"/*.version
    
    if ls $version_file 1> /dev/null 2>&1; then
        rm -f $version_file
        echo "已删除version文件: $version_file"
    fi
}

# 从文件夹名提取端口号
extract_port_from_dir() {
    local dir="$1"
    local port=$(basename "$dir" | grep -oE '[0-9]{4}$')
    echo "${port:-0}"
}

# 重命名文件夹以更新端口号
rename_dir_with_port() {
    local dir="$1"
    local new_port="$2"
    local parent_dir=$(dirname "$dir")
    local dir_name=$(basename "$dir")
    local new_dir="${parent_dir}/${dir_name%_*}_${new_port}"
    
    if [[ "$dir" != "$new_dir" ]]; then
        mv "$dir" "$new_dir"
        echo "已将文件夹重命名为: $(basename "$new_dir")"
        echo "$new_dir"  # 返回新路径
    else
        echo "$dir"  # 返回原路径
    fi
}

# 检查文件夹是否需要修改
need_modify() {
    local dir="$1"
    local counter="$2"
    
    # 计算正确端口号
    local correct_port=$((6069 + counter))
    if [[ $counter -eq 1 ]]; then
        correct_port=6099
    fi
    
    # 检查端口号
    local current_port=$(extract_port_from_dir "$dir")
    if [[ "$current_port" != "$correct_port" ]]; then
        return 0  # 需要修改
    fi
    
    # 检查配置文件是否已修改
    local target_file="$dir/app/Proxy_talk/admin/command.py"
    local new_command="添加文件$counter"
    if grep -q "$new_command" "$target_file"; then
        return 1  # 已修改，跳过
    fi
    
    return 0  # 需要修改
}

# 修改配置主函数
modify_configs() {
    local dir="$1"
    local counter="$2"
    local success_count="$3"
    local fail_count="$4"

    # 先检查是否需要修改
    if ! need_modify "$dir" "$counter"; then
        echo "文件夹已正确配置，跳过: $(basename "$dir")"
        return 0
    fi

    # 计算正确端口号
    local correct_port=$((6069 + counter))
    if [[ $counter -eq 1 ]]; then
        correct_port=6099
    fi
    
    # 检查并更新文件夹端口号
    local current_port=$(extract_port_from_dir "$dir")
    if [[ "$current_port" != "$correct_port" ]]; then
        echo "检测到端口不匹配: 当前${current_port}, 应为${correct_port}"
        dir=$(rename_dir_with_port "$dir" "$correct_port")
    fi

    local target_file="$dir/app/Proxy_talk/admin/command.py"
    local docker_file="$dir/docker-compose.yml"
    local prod_file="$dir/config/environment/prod.py"
    
    local new_container_name="Bot_$counter"
    local new_service_name="aurorabot_$counter"
    local new_app_name="AuroraBot_$counter"
    local old_command1="添加文件1"
    local new_command1="添加文件$counter"
    local old_command2="更新头像"
    local new_command2="更新头像$counter"

    # 修改command.py
    if [[ -f "$target_file" ]]; then
        modify_command_py "$target_file" "$old_command1" "$new_command1" "$old_command2" "$new_command2"
        case $? in
            0) ((success_count++)) ;;
            2) ((fail_count++)) ;;
            3) ((fail_count++)) ;;
        esac
    else
        echo "command.py文件不存在: $target_file"
        ((fail_count++))
    fi

    # 修改docker-compose.yml
    if [[ -f "$docker_file" ]]; then
        local port=$((6069 + counter))  # 第一个是6099(例外)，第二个6070，第三个6071...
        if [[ $counter -eq 1 ]]; then
            port=6099  # 第一个文件夹保持6099不变
        fi
        modify_docker_compose "$docker_file" "$new_container_name" "$new_service_name" "$new_app_name" "$port"
        case $? in
            0) 
                # 修改prod.py
                if [[ -f "$prod_file" ]]; then
                    modify_prod_py "$prod_file" "$new_service_name"
                    case $? in
                        0) ((success_count++)) ;;
                        2) ((fail_count++)) ;;
                    esac
                else
                    echo "prod.py不存在: $prod_file"
                    ((fail_count++))
                fi
                ;;
            2) ((fail_count++)) ;;
        esac
    else
        echo "docker-compose.yml不存在: $docker_file"
        ((fail_count++))
    fi

    # 创建version文件
    create_version_file "$dir" "$counter"
    case $? in
        0) ((success_count++)) ;;
        1) ((fail_count++)) ;;
    esac

    return $((success_count + fail_count))
}

# 还原配置函数
restore_configs() {
    local dir="$1"
    
    # 还原command.py
    if [[ -f "$dir/app/Proxy_talk/admin/command.py.bak" ]]; then
        rm -f "$dir/app/Proxy_talk/admin/command.py"
        mv "$dir/app/Proxy_talk/admin/command.py.bak" "$dir/app/Proxy_talk/admin/command.py"
        echo "已还原command.py: $dir/app/Proxy_talk/admin/command.py"
    fi

    # 还原docker-compose.yml
    if [[ -f "$dir/docker-compose.yml.bak" ]]; then
        rm -f "$dir/docker-compose.yml"
        mv "$dir/docker-compose.yml.bak" "$dir/docker-compose.yml"
        echo "已还原docker-compose.yml: $dir/docker-compose.yml"
    fi

    # 还原prod.py
    if [[ -f "$dir/config/environment/prod.py.bak" ]]; then
        rm -f "$dir/config/environment/prod.py"
        mv "$dir/config/environment/prod.py.bak" "$dir/config/environment/prod.py"
        echo "已还原prod.py: $dir/config/environment/prod.py"
    fi
    
    # 删除version文件
    remove_version_file "$dir"
}

# 显示帮助信息
show_help() {
    echo "使用方法:"
    echo "  ./update_wf.sh --modify    执行配置修改"
    echo "  ./update_wf.sh --restore   执行配置还原"
    echo ""
    echo "功能说明:"
    echo "  批量修改/还原QQbot配置文件"
    exit 0
}

# 主流程
case "$1" in
    "--modify")
        echo "开始执行修改操作..."
        ;;
    "--restore")
        echo "开始执行还原操作..."
        BOT_DIRS=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))
        for dir in "${BOT_DIRS[@]}"; do
            restore_configs "$dir"
        done
        echo "还原操作完成"
        exit 0
        ;;
    *)
        show_help
        ;;
esac

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
    echo "正在检查: $(basename "$dir")"
    modify_configs "$dir" "$counter" "$success_count" "$fail_count"
    ((counter++))
done

echo "处理完成! 成功: $success_count, 失败: $fail_count"
