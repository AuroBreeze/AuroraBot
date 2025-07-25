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

    if [[ ! -f "$file" ]]; then
        echo "command.py 文件不存在: $file"
        return 3
    fi

    if grep -q "$new_cmd1" "$file"; then
        echo "command.py已包含新命令: $new_cmd1"
        return 1
    fi
    if grep -q "$new_cmd2" "$file"; then
        echo "command.py已包含新命令: $new_cmd2"
        return 1
    fi

    local old_cmd1_found=0
    local old_cmd2_found=0
    if grep -q "$old_cmd1" "$file"; then old_cmd1_found=1; fi
    if grep -q "$old_cmd2" "$file"; then old_cmd2_found=1; fi

    if [[ $old_cmd1_found -eq 1 || $old_cmd2_found -eq 1 ]]; then
        cp "$file" "$file.bak"
        if [[ $old_cmd1_found -eq 1 ]]; then
            sed -i "s/$old_cmd1/$new_cmd1/g" "$file"
        fi
        if [[ $old_cmd2_found -eq 1 ]]; then
            sed -i "s/$old_cmd2/$new_cmd2/g" "$file"
        fi

        local success=1
        if [[ $old_cmd1_found -eq 1 ]] && ! grep -q "$new_cmd1" "$file"; then success=0; fi
        if [[ $old_cmd2_found -eq 1 ]] && ! grep -q "$new_cmd2" "$file"; then success=0; fi

        if [[ $success -eq 1 ]]; then
            echo "成功修改command.py: $file"
            return 0
        else
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
    
    # 逐个检查配置项
    local container_matched=0
    local service_matched=0
    local app_matched=0
    local port_matched=0

    if grep -q "container_name: $container_name" "$file"; then
        container_matched=1
    fi
    if grep -q "$service_name:" "$file"; then
        service_matched=1
    fi
    if grep -q "container_name: $app_name" "$file"; then
        app_matched=1
    fi
    if grep -q "${port}:6099" "$file"; then
        port_matched=1
    fi

    if [[ $container_matched -eq 1 && $service_matched -eq 1 && $app_matched -eq 1 && $port_matched -eq 1 ]]; then
        echo "docker-compose.yml已包含所有新配置，跳过修改"
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

# 创建version文件函数（根据遍历顺序递增）
create_version_file() {
    # 避免重复执行：只执行一次递增写入流程
    if [[ -n "$CREATE_VERSION_ONCE" ]]; then
        return 0
    fi
    export CREATE_VERSION_ONCE=1

    # 获取所有 QQbot_* 目录，按名称排序
    BOT_DIRS=( $(find /home -maxdepth 1 -type d -name 'QQbot_*' | sort) )

    local index=1
    for dir in "${BOT_DIRS[@]}"; do
        # 删除旧的 .version 文件
        find "$dir" -maxdepth 1 -name "*.version" -type f -delete

        local version_file="$dir/${index}.version"
        echo "$index" > "$version_file"

        if [[ -f "$version_file" ]]; then
            echo "成功创建version文件: $version_file"
        else
            echo "创建version文件失败: $version_file"
        fi

        ((index++))
    done

    return 0
}

# 删除version文件函数
remove_version_file() {
    local dir="$1"
    # 使用find命令确保删除所有.version文件
    find "$dir" -maxdepth 1 -name "*.version" -type f -delete
    echo "已删除目录 $dir 下的所有.version文件"
}

# 从文件夹名提取端口号
extract_port_from_dir() {
    local dir="$1"
    local port=$(basename "$dir" | grep -oE '[0-9]{4}$')
    echo "${port:-6099}"  # 默认返回6099如果提取不到端口号
}


# 验证文件夹端口号命名是否有效
validate_port_in_dirname() {
    local dir="$1"
    local dirname=$(basename "$dir")
    
    # 检查是否包含端口号
    if ! [[ "$dirname" =~ _[0-9]{4}$ ]]; then
        echo "错误: 文件夹名 '$dirname' 必须以4位端口号结尾 (如 QQbot_6099)"
        return 1
    fi
    
    # 提取端口号
    local port="${dirname##*_}"
    
    # 检查端口号是否重复
    local duplicate_dirs=($(find "$WORK_DIR" -maxdepth 1 -type d -name "*_${port}" | grep -v "$dir"))
    if [[ ${#duplicate_dirs[@]} -gt 0 ]]; then
        echo "错误: 端口号 $port 已存在于其他文件夹: ${duplicate_dirs[@]}"
        return 1
    fi
    
    return 0
}

# need_modify 函数加强文件存在性判断
need_modify() {
    local dir="$1"
    local counter="$2"

    # 先验证文件夹命名
    if ! validate_port_in_dirname "$dir"; then
        return 1
    fi

    local target_file="$dir/app/Proxy_talk/admin/command.py"
    if [[ ! -f "$target_file" ]]; then
        echo "command.py 不存在: $target_file"
        return 0
    fi

    local current_port=$(extract_port_from_dir "$dir")
    if [[ "$current_port" -eq 0 ]]; then return 0; fi

    local new_command="添加文件$counter"
    if grep -q "$new_command" "$target_file"; then return 1; fi

    return 0
}

# modify_configs 函数加入路径输出和防错处理
modify_configs() {
    local dir="$1"
    local counter="$2"
    local success_count="$3"
    local fail_count="$4"

    if ! need_modify "$dir" "$counter"; then
        echo "文件夹已正确配置，跳过: $(basename "$dir")"
        return 0
    fi

    local current_port=$(extract_port_from_dir "$dir")
    local need_rename=0

    local target_file="$dir/app/Proxy_talk/admin/command.py"
    local docker_file="$dir/docker-compose.yml"
    local prod_file="$dir/config/environment/prod.py"

    echo "检查路径: $target_file"

    local new_container_name="Bot_$counter"
    local new_service_name="aurorabot_$counter"
    local new_app_name="AuroraBot_$counter"
    local old_command1="添加文件"
    local new_command1="添加文件$counter"
    local old_command2="更换头像"
    local new_command2="更换头像$counter"

    if [[ -f "$target_file" ]]; then
        modify_command_py "$target_file" "$old_command1" "$new_command1" "$old_command2" "$new_command2"
        case $? in
            0) ((success_count++)) ;;
            2|3) ((fail_count++)) ;;
        esac
    else
        echo "command.py文件不存在: $target_file"
        ((fail_count++))
    fi

    if [[ -f "$docker_file" ]]; then
        local port=$(extract_port_from_dir "$dir")
        modify_docker_compose "$docker_file" "$new_container_name" "$new_service_name" "$new_app_name" "$port"
        if [[ $? -eq 0 ]]; then
            if [[ -f "$prod_file" ]]; then
                modify_prod_py "$prod_file" "$new_service_name"
                if [[ $? -eq 0 ]]; then ((success_count++)); else ((fail_count++)); fi
            else
                echo "prod.py不存在: $prod_file"
                ((fail_count++))
            fi
        else
            ((fail_count++))
        fi
    else
        echo "docker-compose.yml不存在: $docker_file"
        ((fail_count++))
    fi

    # 不再重命名文件夹

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
    
    # 删除复制的txt文件
    local txt_file="$dir/store/file/talk_template.txt"
    if [[ -f "$txt_file" ]]; then
        rm -f "$txt_file"
        echo "已删除txt文件: $txt_file"
    fi
}

# 显示帮助信息
show_help() {
    echo "使用方法:"
    echo "  ./update_wf.sh --modify        执行配置修改"
    echo "  ./update_wf.sh --restore       执行配置还原"
    echo "  ./update_wf.sh --create-version        为所有QQbot文件夹创建version文件"
    echo "  ./update_wf.sh --remove-version        删除所有QQbot文件夹的version文件"
    echo "  ./update_wf.sh --copy-txt           复制/home/txt下的txt文件到所有QQbot目录"
    echo ""
    echo "功能说明:"
    echo "  批量修改/还原QQbot配置文件"
    exit 0
}

# 复制txt文件到所有QQbot目录
copy_txt_files() {
    local txt_dir="/home/txt"
    if [[ ! -d "$txt_dir" ]]; then
        echo "txt目录不存在: $txt_dir"
        return 1
    fi

    # 获取所有txt文件
    local txt_files=($(find "$txt_dir" -maxdepth 1 -type f -name '*.txt' | sort))
    if [ ${#txt_files[@]} -eq 0 ]; then
        echo "未找到任何txt文件"
        return 1
    fi

    # 获取所有QQbot目录
    local bot_dirs=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))
    if [ ${#bot_dirs[@]} -eq 0 ]; then
        echo "未找到任何 QQbot_* 目录"
        return 1
    fi

    local file_index=0
    for bot_dir in "${bot_dirs[@]}"; do
        local target_dir="$bot_dir/store/file"
        mkdir -p "$target_dir"
        
        local source_file="${txt_files[$file_index]}"
        if [[ -z "$source_file" ]]; then
            file_index=0
            source_file="${txt_files[$file_index]}"
        fi

        cp "$source_file" "$target_dir/talk_template.txt"
        echo "已复制文件: $source_file 到 $target_dir/talk_template.txt"
        
        ((file_index++))
    done

    return 0
}

# 主流程
case "$1" in
    "--modify")
        echo "开始执行修改操作..."
        BOT_DIRS=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))
        if [ ${#BOT_DIRS[@]} -eq 0 ]; then
            echo "未找到任何 QQbot_* 目录"
            exit 1
        fi
        
        # 先复制txt文件
        copy_txt_files
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
    "--create-version")
        echo "开始为所有QQbot文件夹创建version文件..."
        BOT_DIRS=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))
        if [ ${#BOT_DIRS[@]} -eq 0 ]; then
            echo "未找到任何 QQbot_* 目录"
            exit 1
        fi
        
        for dir in "${BOT_DIRS[@]}"; do
            create_version_file "$dir" "1"
        done
        echo "version文件创建完成"
        exit 0
        ;;
    "--remove-version")
        echo "开始删除所有QQbot文件夹的version文件..."
        BOT_DIRS=($(find "$WORK_DIR" -maxdepth 1 -type d -name 'QQbot_*' | sort))
        if [ ${#BOT_DIRS[@]} -eq 0 ]; then
            echo "未找到任何 QQbot_* 目录"
            exit 1
        fi
        
        for dir in "${BOT_DIRS[@]}"; do
            remove_version_file "$dir"
        done
        echo "version文件删除完成"
        exit 0
        ;;
    "--copy-txt")
        echo "开始复制txt文件到所有QQbot目录..."
        copy_txt_files
        exit $?
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

    # 为所有文件夹创建新的version文件
    # 先确保删除所有旧的.version文件
    for dir in "${BOT_DIRS[@]}"; do
        remove_version_file "$dir"
    done

    counter=1
    for dir in "${BOT_DIRS[@]}"; do
        version_file="$dir/${counter}.version"
        echo "$counter" > "$version_file"
        if [[ -f "$version_file" ]]; then
            echo "成功创建version文件: $version_file"
        else
            echo "创建version文件失败: $version_file"
        fi
        ((counter++))
    done

    echo "配置修改完成! 成功: $success_count, 失败: $fail_count"
