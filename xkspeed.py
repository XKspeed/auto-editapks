#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import glob
import shutil
import subprocess
import sys
import time
import configparser
import signal
import threading
import re
import difflib
import zlib
import webbrowser

# ==================== 常量定义 ====================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(WORK_DIR, "input")
OUTPUT_DIR_BASE = os.path.join(WORK_DIR, "output")
BUILD_DIR = os.path.join(WORK_DIR, "temp_build")
PATCH_INI_DIR = os.path.join(WORK_DIR, "patch_ini")
PATCH_CLASSES_DIR = os.path.join(WORK_DIR, "patch_classes")
SAVE_DIR = os.path.join(WORK_DIR, "save")

# 程序版本
VERSION = "1.1"
GITHUB_REPO = "XKspeed/auto-editapks"

# INI 配置版本
INI_VERSION = "1.1"
SUPPORTED_INI_VERSIONS = ["1.0", "1.1"]

# 进度估算倍数
DECOMPILE_SIZE_MULTIPLIER = 6
RECOMPILE_SIZE_MULTIPLIER = 1

# 进度更新间隔（秒）
PROGRESS_UPDATE_INTERVAL = 1

# 预览上下文行数
PREVIEW_CONTEXT_LINES = 3

# ANSI 颜色代码
RED = '\033[91m'
GREEN = '\033[92m'
RESET = '\033[0m'
YELLOW = '\033[93m'

# ==================== 全局状态 ====================
print_lock = threading.Lock()
modification_records = []


# ==================== 基础工具函数 ====================

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def cleanup_temp():
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR, ignore_errors=True)


def signal_handler(sig, frame):
    print("\n\n⚠️ 中断，清理中...")
    cleanup_temp()
    print("✅ 已退出")
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)


def format_size(size):
    if size < 1024:
        return f"{int(size)}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    else:
        return f"{size/1024/1024:.1f}MB"


def print_progress(desc, percent, size_str="", speed_str=""):
    with print_lock:
        bar_length = 20
        filled = int(bar_length * percent / 100) if percent > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)
        desc = desc.replace('\n', ' ')
        
        if len(desc) > 50:
            desc = desc[:47] + "..."
        
        if size_str and speed_str:
            progress_str = f"\r\033[2K  {desc} [{bar}] {percent:3d}%  {size_str} ({speed_str}/s)"
        else:
            progress_str = f"\r\033[2K  {desc} [{bar}] {percent:3d}%"
        
        sys.stdout.write(progress_str)
        sys.stdout.flush()
        
        if percent >= 100:
            sys.stdout.write("\n")


def check_q_input(user_input):
    """统一检查 Q 返回（仅小写 q）"""
    if user_input and user_input.strip() == 'q':
        return True
    return False


def check_dependencies():
    deps = {
        "apktool": ["apktool", "--version"],
        "unzip": ["unzip", "-v"],
        "zip": ["zip", "-v"],
        "aapt2": ["aapt2", "version"],
    }

    missing = []

    print("=" * 60)
    print("检查前置依赖")
    print("=" * 60)
    print()

    for name, test_cmd in deps.items():
        try:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"  ✅ {name}")
            else:
                print(f"  ❌ {name}")
                missing.append(name)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"  ❌ {name}")
            missing.append(name)

    if missing:
        print("\n" + "=" * 60)
        print("缺少以下依赖:")
        print("=" * 60)
        for name in missing:
            print(f"\n安装 {name}:")
            print(f"  pkg install {name} -y")

        print("\n" + "=" * 60)
        choice = input("是否现在安装？(y/n): ").strip().lower()
        if choice == 'y':
            for name in missing:
                print(f"\n安装 {name}...")
                subprocess.run(["pkg", "install", name, "-y"])

            print("\n重新检查...")
            still_missing = []
            for name, test_cmd in deps.items():
                try:
                    result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print(f"  ✅ {name}")
                    else:
                        print(f"  ❌ {name}")
                        still_missing.append(name)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    print(f"  ❌ {name}")
                    still_missing.append(name)

            if still_missing:
                print("\n仍有依赖未安装，请手动安装后重试")
                sys.exit(1)
        else:
            print("请手动安装后再运行")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 所有依赖就绪")
    print("=" * 60)
    time.sleep(1)


def find_file(pattern, base):
    files = glob.glob(f"{base}/**/{pattern}", recursive=True)
    return files[0] if files else None


def find_files(pattern, base):
    return sorted(glob.glob(f"{base}/**/{pattern}", recursive=True))


def find_apk_in_project(project_dir):
    apk_files = glob.glob(os.path.join(project_dir, "*.apk"))
    if apk_files:
        return apk_files[0]
    return None


def resolve_file_path(filename, work_subdir):
    """解析 arsc XML 文件路径"""
    if not filename:
        return None
    
    filename = filename.strip()
    
    if '/' in filename or '\\' in filename:
        return find_file(filename, work_subdir)
    
    if filename.endswith('.smali'):
        return find_file(filename, work_subdir)
    
    if '-' in filename:
        base_name, qualifier = filename.split('-', 1)
        xml_filename = f"{base_name}s.xml"
        xml_path = f"res/values-{qualifier}/{xml_filename}"
    else:
        base_name = filename
        xml_filename = f"{base_name}s.xml"
        xml_path = f"res/values/{xml_filename}"
    
    filepath = os.path.join(work_subdir, xml_path)
    if os.path.exists(filepath):
        return filepath
    
    return find_file(xml_path, work_subdir)


def resolve_smali_file(filename, work_subdir, interactive=True):
    """解析 smali 文件路径"""
    if not filename:
        return None
    
    filename = filename.strip()
    
    if filename.endswith('.smali'):
        files = find_files(filename, work_subdir)
        if len(files) == 1:
            return files[0]
        elif len(files) > 1:
            return _select_from_multiple(files, work_subdir, interactive)
        return None
    
    if '/' in filename or '\\' in filename:
        files = find_files(filename, work_subdir)
        if len(files) == 1:
            return files[0]
        elif len(files) > 1:
            return _select_from_multiple(files, work_subdir, interactive)
        return None
    
    if '.' in filename:
        smali_path = filename.replace('.', '/') + '.smali'
        files = find_files(smali_path, work_subdir)
        if len(files) == 1:
            return files[0]
        elif len(files) > 1:
            return _select_from_multiple(files, work_subdir, interactive)
        return None
    
    files = find_files(filename + '.smali', work_subdir)
    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        return _select_from_multiple(files, work_subdir, interactive)
    
    return None


def _select_from_multiple(files, work_subdir, interactive):
    """从多个匹配中选择文件"""
    
    print(f"\n⚠️ 找到 {len(files)} 个匹配文件:")
    for i, f in enumerate(files):
        rel = os.path.relpath(f, work_subdir)
        print(f"  [{i+1}] {rel}")
    
    if not interactive:
        print(f"  ⚠️ 非交互模式，使用第一个匹配")
        return files[0]
    
    print()
    print("  输入数字选择文件")
    print("  输入 0 = 使用最后一个匹配")
    print("  直接回车 = 使用第一个匹配")
    print("  输入 Q = 取消")
    print("-" * 40)
    
    choice = input("> ").strip().lower()
    
    if check_q_input(choice):
        return None
    
    if choice == "0":
        selected = files[-1]
        rel = os.path.relpath(selected, work_subdir)
        print(f"  ✅ 使用最后一个匹配: {rel}")
        return selected
    
    if choice == "":
        selected = files[0]
        rel = os.path.relpath(selected, work_subdir)
        print(f"  ✅ 使用第一个匹配: {rel}")
        return selected
    
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            selected = files[idx]
            rel = os.path.relpath(selected, work_subdir)
            print(f"  ✅ 选择: {rel}")
            return selected
    
    print(f"  ❌ 无效选择，使用第一个匹配")
    return files[0]


# ==================== 唯一辅助定位值查找 ====================

def filter_reliable_lines(lines):
    """过滤可靠行（排除寄存器、跳转等不稳定内容）"""
    reliable = []
    
    for line in lines:
        stripped = line.strip()
        
        # 跳过空行
        if not stripped:
            continue
        
        # 跳过跳转标签
        if stripped.startswith(':'):
            continue
        
        # 跳过 goto/return 等跳转指令
        if re.match(r'^(goto|goto/16|goto/32|return|return-void|return-wide|return-object)', stripped):
            continue
        
        # 跳过 if 跳转指令
        if re.match(r'^if-', stripped):
            continue
        
        # 跳过纯寄存器操作
        if re.match(r'^(move|move-result|move-result-object|move-exception|move-object|move-wide)', stripped):
            continue
        
        # 跳过 const/4, const/16 等简单数值（但保留 const-string）
        if re.match(r'^const/(4|16|high16)\s', stripped):
            continue
        
        # 保留字符串常量
        if 'const-string' in stripped:
            reliable.append(stripped)
            continue
        
        # 保留方法调用（invoke）
        if re.match(r'^invoke-', stripped):
            reliable.append(stripped)
            continue
        
        # 保留字段引用（iget/sget/iput/sput）
        if re.match(r'^(iget|sget|iput|sput)', stripped):
            reliable.append(stripped)
            continue
        
        # 保留类型引用（const-class/new-instance）
        if re.match(r'^(const-class|new-instance)', stripped):
            reliable.append(stripped)
            continue
    
    return reliable


def extract_unique_marker(line):
    """从可靠行中提取唯一标识"""
    
    # 字符串常量
    match = re.search(r'const-string[^,]*,\s*"([^"]+)"', line)
    if match:
        return f'"{match.group(1)}"'
    
    # 方法调用（提取完整签名）
    match = re.search(r'(L[\w/$]+;->[\w$]+\([^)]*\)[^;]*)', line)
    if match:
        return match.group(1)
    
    # 字段引用（提取完整签名）
    match = re.search(r'(L[\w/$]+;->[\w$]+:[^;]+;)', line)
    if match:
        return match.group(1)
    
    # 类型引用
    match = re.search(r'(L[\w/$]+;)', line)
    if match:
        return match.group(1)
    
    return None


def find_unique_assist_content(matches, selected_index, search_range, file_lines):
    """查找唯一辅助定位值"""
    
    target_line = matches[selected_index]
    
    # 提取目标匹配的上下文
    target_start = max(0, target_line - search_range)
    target_end = min(len(file_lines), target_line + search_range + 1)
    target_context = file_lines[target_start:target_end]
    
    # 提取其它匹配的上下文
    other_contexts = []
    for i, match in enumerate(matches):
        if i != selected_index:
            other_start = max(0, match - search_range)
            other_end = min(len(file_lines), match + search_range + 1)
            other_contexts.append(file_lines[other_start:other_end])
    
    # 过滤可靠行
    reliable_lines = filter_reliable_lines(target_context)
    
    # 查找目标独有内容
    for line in reliable_lines:
        is_unique = True
        for other_ctx in other_contexts:
            if line in other_ctx:
                is_unique = False
                break
        
        if is_unique:
            unique_marker = extract_unique_marker(line)
            if unique_marker:
                return unique_marker
    
    return None


def input_assist_search_range():
    """输入辅助定位值搜索范围"""
    print("\n" + "-" * 60)
    print("辅助定位值搜索范围设置")
    print("-" * 60)
    print()
    print("请输入附近辅助定位值的搜索范围（行数）:")
    print("  - 默认 5 行（上下各 5 行）")
    print("  - 直接回车使用默认值")
    print("  - 输入 Q = 返回上一级")
    print()
    
    range_input = input("> ").strip()
    
    if check_q_input(range_input):
        return None
    
    if range_input == "":
        return 5
    
    try:
        search_range = int(range_input)
        if search_range <= 0:
            print("⚠️ 范围必须大于 0，使用默认值 5")
            return 5
        return search_range
    except:
        print("⚠️ 无效输入，使用默认值 5")
        return 5


# ==================== 教程链接打开 ====================

def parse_intent_url(intent_url):
    """解析 intent:// 链接"""
    result = {
        'path': '',
        'scheme': None,
        'package': None,
        'full_url': None,
    }
    
    path_match = re.match(r'intent://([^#]+)', intent_url)
    if path_match:
        result['path'] = path_match.group(1)
    
    params_match = re.search(r'#Intent;(.*);end', intent_url, re.IGNORECASE)
    if params_match:
        params_str = params_match.group(1)
        for param in params_str.split(';'):
            if '=' in param:
                key, value = param.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'scheme':
                    result['scheme'] = value
                elif key == 'package':
                    result['package'] = value
    
    if result['scheme'] and result['path']:
        clean_path = re.sub(r'^www\.', '', result['path'])
        result['full_url'] = f"{result['scheme']}://{clean_path}"
    
    return result


def open_tutorial(url):
    """打开教程链接，支持网页和 APP 链接"""
    import subprocess
    
    print(f"📖 正在打开教程...")
    print()
    
    # 网页链接
    if url.startswith(('http://', 'https://')):
        try:
            webbrowser.open(url)
            print(f"✅ 已在浏览器中打开")
            return True
        except:
            print(f"⚠️ 无法自动打开浏览器，请手动访问: {url}")
            return False
    
    # intent:// 链接
    if url.startswith('intent://'):
        parsed = parse_intent_url(url)
        
        # 尝试方法 1：转换后的 scheme URL
        if parsed.get('full_url'):
            cmd = ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', parsed['full_url']]
            if parsed.get('package'):
                cmd.extend(['-p', parsed['package']])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"✅ 已跳转到 APP")
                    return True
            except:
                pass
        
        # 尝试方法 2：原始 intent:// URI
        cmd = ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ 已跳转到 APP")
                return True
        except:
            pass
    
    # 其他 APP scheme
    if url.startswith(('coolmarket://', 'coolapk://', 'weixin://', 'mqq://', 
                       'alipays://', 'taobao://', 'tmall://', 'bilibili://',
                       'snssdk1128://', 'market://')):
        cmd = ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ 已跳转到 APP")
                return True
        except:
            pass
    
    # termux-open-url 兜底
    try:
        result = subprocess.run(['termux-open-url', url], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ 已打开")
            return True
    except:
        pass
    
    print(f"⚠️ 无法自动打开，请手动访问: {url}")
    return False


def check_update():
    """检查 GitHub Release 是否有新版本"""
    import json
    import urllib.request
    
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        latest = data.get("tag_name", "").replace("v", "").strip()
        if not latest or latest == VERSION:
            return
        
        print("=" * 60)
        print("发现新版本")
        print("=" * 60)
        print()
        print(f"  当前版本: v{VERSION}")
        print(f"  最新版本: v{latest}")
        print()
        print(f"  下载页面: https://github.com/{GITHUB_REPO}/releases/latest")
        print()
        
        choice = input("是否立即更新？(y/n): ").strip().lower()
        if choice != 'y':
            return
        
        # 获取下载地址
        assets = data.get("assets", [])
        if not assets:
            print("⚠️ Release 没有附加文件")
            print(f"请手动下载: https://github.com/{GITHUB_REPO}/releases/latest")
            return
        
        download_url = assets[0].get("browser_download_url", "")
        if not download_url:
            print("⚠️ 无法获取下载地址")
            return
        
        print(f"📥 正在下载...")
        urllib.request.urlretrieve(download_url, __file__ + ".tmp")
        
        # 替换原文件
        import shutil
        shutil.move(__file__ + ".tmp", __file__)
        
        print(f"✅ 更新完成！请重新打开程序")
        sys.exit(0)
    except:
        pass


# ==================== 手动修改 DEX ====================

def manual_edit_dex(work_subdir):
    global modification_records
    
    clear_screen()
    print("=" * 60)
    print("手动修改 dex")
    print("=" * 60)
    print()

    class_input = input("输入类名（如 LayoutParamsUtils / Q 返回）: ").strip()
    if not class_input:
        return
    if check_q_input(class_input):
        return

    filepath = resolve_smali_file(class_input, work_subdir, interactive=True)
    
    if not filepath:
        print(f"❌ 未找到类: {class_input}")
        input("\n按回车返回...")
        return
    
    rel_path = os.path.relpath(filepath, work_subdir)
    pure_class_name = os.path.basename(filepath).replace('.smali', '')
    
    print(f"\n✅ 找到: {rel_path}")

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        class_content = f.read()

    methods = re.findall(r'\.method.*\n', class_content)

    clear_screen()
    print("=" * 60)
    print(f"类: {pure_class_name}")
    print(f"路径: {rel_path}")
    print("=" * 60)
    print()

    print("  [0] 不选择方法，在整个类中搜索修改")
    
    if methods:
        for i, method in enumerate(methods):
            print(f"  [{i+1}] {method.strip()}")
    else:
        print("  (未找到方法)")

    print()
    print("选择方法:")
    print("  - 输入数字选择方法（如：1）")
    print("  - 输入 0 = 整个类中搜索")
    print("  - 或输入方法名搜索")
    print("  - 输入 Q = 返回上一级")
    print("-" * 60)

    method_input = input("> ").strip()
    if check_q_input(method_input):
        return

    method_name = None
    method_range = None
    method_content = None
    method_start_offset = 0

    if method_input == "0":
        method_name = None
        method_range = None
        method_content = class_content
        method_lines = class_content.split('\n')
    elif method_input.isdigit():
        method_idx = int(method_input) - 1
        if method_idx < 0 or method_idx >= len(methods):
            print(f"❌ 无效的选择: {method_input}")
            input("\n按回车返回...")
            return
        
        selected_method_line = methods[method_idx].strip()
        method_match = re.search(re.escape(selected_method_line), class_content)
        
        if not method_match:
            print(f"❌ 无法定位方法: {selected_method_line}")
            input("\n按回车返回...")
            return
        
        method_name_match = re.search(r'\.method\s+.*?\s+(\w+)\s*\(', selected_method_line)
        if method_name_match:
            method_name = method_name_match.group(1)
        else:
            method_name = selected_method_line[:50]
        
        method_start = method_match.start()
        method_end = class_content.find(".end method", method_start)
        if method_end == -1:
            method_end = len(class_content)
        else:
            method_end += len(".end method")
        
        method_content = class_content[method_start:method_end]
        method_lines = method_content.split('\n')
        method_start_offset = class_content[:method_start].count('\n')
        
        # 计算行号范围
        start_line = method_start_offset
        end_line = start_line + len(method_lines)
        method_range = (start_line, end_line)
    else:
        method_name = method_input
        method_pattern = rf'\.method.*{re.escape(method_name)}.*\n'
        method_matches = list(re.finditer(method_pattern, class_content, re.IGNORECASE))
        
        if not method_matches:
            print(f"❌ 未找到方法: {method_name}")
            input("\n按回车返回...")
            return
        
        if len(method_matches) > 1:
            print(f"\n找到 {len(method_matches)} 个匹配方法:")
            for i, m in enumerate(method_matches):
                print(f"  [{i+1}] {m.group().strip()}")
            
            choice = input("\n输入数字选择方法（Q 返回）: ").strip()
            if check_q_input(choice):
                return
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(method_matches):
                    method_match = method_matches[idx]
                else:
                    return
            else:
                return
        else:
            method_match = method_matches[0]
        
        method_start = method_match.start()
        method_end = class_content.find(".end method", method_start)
        if method_end == -1:
            method_end = len(class_content)
        else:
            method_end += len(".end method")
        
        method_content = class_content[method_start:method_end]
        method_lines = method_content.split('\n')
        method_start_offset = class_content[:method_start].count('\n')
        
        start_line = method_start_offset
        end_line = start_line + len(method_lines)
        method_range = (start_line, end_line)

    # 显示方法内容
    if method_name:
        clear_screen()
        print("=" * 60)
        print(f"方法: {method_name}")
        print("=" * 60)
        print()
        print(method_content[:2000])
        print()
        print("-" * 60)
    
    # 输入 anchor
    while True:
        anchor = input("输入定位内容（anchor，Q 返回）: ").strip()
        if check_q_input(anchor):
            return
        if not anchor:
            print("⚠️ anchor 不能为空")
            continue
        break
    
    # 在搜索范围内查找所有匹配
    search_lines = method_lines if method_range else class_content.split('\n')
    search_start_offset = method_start_offset if method_range else 0
    
    anchor_matches = []
    for i, line in enumerate(search_lines):
        if anchor.strip() in line:
            anchor_matches.append(i)
    
    if not anchor_matches:
        scope_name = f"方法 {method_name}" if method_name else "类"
        print(f"❌ {scope_name} 中未找到: {anchor}")
        choice = input("\n是否重新输入定位内容？(y/n/Q): ").strip().lower()
        if choice == 'y':
            # 重新输入 anchor
            return manual_edit_dex(work_subdir)
        else:
            input("\n按回车返回...")
            return
    
    # 处理匹配结果
    selected_match_idx = 0
    assist_content = None
    assist_range = None
    
    if len(anchor_matches) == 1:
        # 唯一匹配
        selected_match_idx = 0
        print(f"\n✅ 定位唯一（第 {anchor_matches[0] + search_start_offset + 1} 行）")
    else:
        # 多个匹配
        print(f"\n⚠️ 定位不唯一！找到 {len(anchor_matches)} 处匹配")
        print("=" * 60)
        
        for i, idx in enumerate(anchor_matches):
            context_start = max(0, idx - 3)
            context_end = min(len(search_lines), idx + 4)
            
            print(f"\n  [{i+1}] 第 {idx + search_start_offset + 1} 行:")
            print("  " + "-" * 50)
            for j in range(context_start, context_end):
                marker = ">>>" if j == idx else "   "
                print(f"  {marker} {j + search_start_offset + 1:4d} | {search_lines[j]}")
            print("  " + "-" * 50)
        
        print()
        print("  输入数字选择匹配项")
        print("  输入 0 = 使用最后一个匹配")
        print("  输入 A = 替换所有匹配")
        print("  直接回车 = 使用第一个匹配")
        print("  输入 Q = 返回上一级")
        print("-" * 40)
        
        choice = input("> ").strip().lower()
        
        if check_q_input(choice):
            return
        
        if choice == "a":
            # 替换所有匹配
            replace_all = True
            selected_match_idx = 0
            target_line = anchor_matches[0]
            print(f"\n✅ 已选择：替换所有 {len(anchor_matches)} 处匹配")
            
            # 输入修改内容
            content = input_modification_content()
            if content is None:
                return
            
            # 替换所有匹配
            new_lines = search_lines.copy()
            for match_idx in anchor_matches:
                original_line = new_lines[match_idx]
                new_lines[match_idx] = original_line.replace(anchor.strip(), content.strip())
            
            # 预览
            if not preview_and_confirm(search_lines, new_lines, anchor_matches[0], search_start_offset):
                return
            
            # 写回文件
            apply_changes_to_file(filepath, search_lines, new_lines, method_range, method_start_offset, class_content)
            
            # 记录修改
            full_class_name = rel_path.replace('.smali', '')
            parts_list = full_class_name.split('/')
            if parts_list and 'smali' in parts_list[0]:
                parts_list = parts_list[1:]
            full_class_name = '.'.join(parts_list)
            
            rule_data = {
                'type': 'smali',
                'name': f"修改{pure_class_name}_{method_name or 'class'}",
                'file': full_class_name,
                'anchor': anchor,
                'content': content,
                'position': 'replace',
                'replace_all': True,
            }
            
            if method_name:
                rule_data['method'] = method_name
            
            modification_records.append(rule_data)
            print(f"\n✅ 修改成功（替换了 {len(anchor_matches)} 处）")
            print(f"📝 修改已记录（共 {len(modification_records)} 条）")
            
            input("\n按回车返回...")
            return
        
        if choice == "0":
            selected_match_idx = len(anchor_matches) - 1
        elif choice == "":
            selected_match_idx = 0
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(anchor_matches):
                selected_match_idx = idx
            else:
                print(f"❌ 无效选择，使用第一个匹配")
                selected_match_idx = 0
        else:
            print(f"❌ 无效选择，使用第一个匹配")
            selected_match_idx = 0
        
        target_line = anchor_matches[selected_match_idx]
        print(f"\n✅ 已选择第 {selected_match_idx + 1} 处匹配（第 {target_line + search_start_offset + 1} 行）")
        
        # 输入辅助定位值搜索范围
        assist_range = input_assist_search_range()
        if assist_range is None:
            return
        
        print(f"\n✅ 搜索范围设置为: 上下各 {assist_range} 行")
        
        # 自动查找唯一辅助定位值
        print(f"\n🔍 正在查找唯一辅助定位值（范围: ±{assist_range} 行）...")
        
        auto_assist = find_unique_assist_content(anchor_matches, selected_match_idx, assist_range, search_lines)
        
        if auto_assist:
            print(f"✅ 找到唯一标识: {auto_assist}")
            assist_content = auto_assist
        else:
            print(f"❌ 未找到唯一辅助定位值")
            print()
            print(f"原因：在 ±{assist_range} 行范围内没有可区分的字符串、方法签名或字段引用")
            print(f"（仅包含寄存器编号或跳转标签等不稳定内容）")
            print()
            
            # 扩大范围重试 / 手动输入 / 跳过
            while True:
                print("-" * 60)
                print("未找到唯一辅助定位值")
                print("-" * 60)
                print()
                print("选择下一步:")
                print("  [1] 扩大搜索范围重试")
                print("  [2] 手动输入辅助定位值")
                print("  [3] 跳过辅助定位，直接使用相对位置")
                print("  [Q] 返回上一级")
                print()
                
                assist_choice = input("> ").strip().lower()
                
                if check_q_input(assist_choice):
                    return
                
                if assist_choice == "1":
                    # 扩大搜索范围
                    print()
                    new_range_input = input(f"请输入新的搜索范围（当前 {assist_range}，Q 返回）: ").strip()
                    if check_q_input(new_range_input):
                        return
                    try:
                        new_range = int(new_range_input)
                        if new_range <= assist_range:
                            print("⚠️ 新范围必须大于当前范围")
                            continue
                        assist_range = new_range
                    except:
                        print("⚠️ 无效输入")
                        continue
                    
                    print(f"\n🔍 正在重新查找唯一辅助定位值（范围: ±{assist_range} 行）...")
                    auto_assist = find_unique_assist_content(anchor_matches, selected_match_idx, assist_range, search_lines)
                    if auto_assist:
                        print(f"✅ 找到唯一标识: {auto_assist}")
                        assist_content = auto_assist
                        break
                    else:
                        print(f"❌ 仍未找到唯一辅助定位值")
                        print()
                        continue
                
                if assist_choice == "3":
                    # 跳过辅助定位
                    assist_content = None
                    assist_range = None
                    break
                
                if assist_choice != "2":
                    continue
                
                print()
                print("请输入附近辅助定位值（Q 返回）: ")
                
                user_assist = input("> ").strip()
                
                if check_q_input(user_assist):
                    return
                
                if not user_assist:
                    continue
                
                assist_content = user_assist
                
                print(f"\n🔍 正在验证辅助定位值 \"{assist_content}\"（范围: ±{assist_range} 行）...")
                
                target_line = anchor_matches[selected_match_idx]
                search_start = max(0, target_line - assist_range)
                search_end = min(len(search_lines), target_line + assist_range + 1)
                
                found = False
                for i in range(search_start, search_end):
                    if assist_content in search_lines[i]:
                        found = True
                        break
                
                if found:
                    print(f"✅ 找到辅助定位值: {assist_content}（第 {target_line + search_start_offset + 1} 行附近）")
                    break
                else:
                    print(f"❌ 未找到 \"{assist_content}\" 在第 {target_line + search_start_offset + 1} 行附近 ±{assist_range} 行范围内")
                    print()
                    
                    retry = input("是否重新输入？(y/n): ").strip().lower()
                    if retry != 'y':
                        print()
                        print("⚠️ 已放弃辅助定位")
                        return manual_edit_dex(work_subdir)
    
    # 定位到目标行
    target_line = anchor_matches[selected_match_idx]
    
    # 显示相对位置视图
    clear_screen()
    print("=" * 60)
    print("定位位置分析")
    print("=" * 60)
    print()
    
    # 确定显示范围
    if assist_content and assist_range:
        display_range = assist_range
    else:
        display_range = PREVIEW_CONTEXT_LINES
    
    context_start = max(0, target_line - display_range)
    context_end = min(len(search_lines), target_line + display_range + 1)
    
    # 查找辅助定位值的行位置
    assist_line_idx = None
    if assist_content:
        for i in range(context_start, context_end):
            if assist_content in search_lines[i]:
                assist_line_idx = i
                break
    
    print("相对位置  行号   代码")
    print("-" * 60)
    
    for i in range(context_start, context_end):
        rel_pos = i - target_line
        abs_line = i + search_start_offset + 1
        
        line_text = search_lines[i]
        
        if assist_line_idx is not None and i == assist_line_idx:
            print(f"  {rel_pos:+3d}     {abs_line:4d}    {YELLOW}{line_text}{RESET}  ← 🟡 辅助定位值")
        elif i == target_line:
            print(f"  {rel_pos:+3d}     {abs_line:4d}    {GREEN}{line_text}{RESET}  ← 🟢 原 anchor")
        else:
            print(f"  {rel_pos:+3d}     {abs_line:4d}    {line_text}")
    
    print("-" * 60)
    print()
    
    if assist_line_idx is not None:
        print(f"  🟡 辅助定位值位置: 相对 {assist_line_idx - target_line:+d} (第 {assist_line_idx + search_start_offset + 1} 行)")
    print(f"  🟢 原 anchor 位置: 相对 +0 (第 {target_line + search_start_offset + 1} 行)")
    
    print()
    print("请选择修改位置：")
    print("  输入 1 个位置编号 = 替换该位置")
    print("  输入 2 个位置编号（用空格分隔）= 在两者之间插入")
    print("  输入 Q = 返回上一级")
    print()
    
    position_choice = input("> ").strip()
    if check_q_input(position_choice):
        return
    
    # 解析用户选择
    parts = position_choice.split()
    
    if len(parts) == 1:
        # 单个位置 = 替换
        try:
            rel_pos = int(parts[0])
            actual_line_idx = target_line + rel_pos
            
            if actual_line_idx < 0 or actual_line_idx >= len(search_lines):
                print(f"❌ 无效位置: {rel_pos}")
                input("\n按回车返回...")
                return
            
            # 替换模式
            print(f"\n✅ 已选择位置: 相对 {rel_pos:+d} (第 {actual_line_idx + search_start_offset + 1} 行)")
            print()
            
            # 选择替换方式
            print("替换方式:")
            print("  [1] 替换指定字符")
            print("  [2] 替换整行")
            print("  [Q] 返回上一级")
            print()
            
            replace_mode = input("选择替换方式（1/2/Q）: ").strip().upper()
            if replace_mode == 'Q':
                return
            
            replace_line = (replace_mode == '2')
            replace_target = None
            
            if not replace_line:
                # 替换指定字符
                current_line = search_lines[actual_line_idx]
                print(f"\n当前行: {current_line}")
                print(f"原 anchor: {anchor}")
                print()
                
                replace_target = input("输入需要被替换的内容（Q 返回）: ").strip()
                if check_q_input(replace_target):
                    return
                
                if not replace_target:
                    print("⚠️ 未输入替换目标，默认使用 anchor")
                    replace_target = anchor
                
                if replace_target not in current_line:
                    print(f"⚠️ 当前行中未找到: {replace_target}")
                    confirm = input("是否继续？(y/n): ").strip().lower()
                    if confirm != 'y':
                        return
            
            # 输入修改内容
            content = input_modification_content()
            if content is None:
                return
            
            # 应用修改
            new_lines = search_lines.copy()
            original_line = new_lines[actual_line_idx]
            
            indent = ''
            for ch in original_line:
                if ch in (' ', '\t'):
                    indent += ch
                else:
                    break
            
            if replace_line:
                content_lines_final = [line.rstrip() for line in content.strip().split('\n') if line.strip()]
                new_lines[actual_line_idx] = indent + content_lines_final[0] if content_lines_final else ""
            else:
                new_lines[actual_line_idx] = original_line.replace(replace_target, content.strip())
            
            # 预览
            if not preview_and_confirm(search_lines, new_lines, actual_line_idx, search_start_offset):
                return
            
            # 写回文件
            apply_changes_to_file(filepath, search_lines, new_lines, method_range, method_start_offset, class_content)
            
            # 记录修改
            full_class_name = rel_path.replace('.smali', '')
            parts_list = full_class_name.split('/')
            if parts_list and 'smali' in parts_list[0]:
                parts_list = parts_list[1:]
            full_class_name = '.'.join(parts_list)
            
            rule_data = {
                'type': 'smali',
                'name': f"修改{pure_class_name}_{method_name or 'class'}",
                'file': full_class_name,
                'anchor': anchor,
                'content': content,
                'position': 'replace',
                'replace_line': replace_line,
                'match_index': selected_match_idx + 1,
            }
            
            if replace_target and replace_target != anchor:
                rule_data['replace_target'] = replace_target
            if method_name:
                rule_data['method'] = method_name
            if assist_content:
                rule_data['assist'] = str(assist_range or 5)
                rule_data['assist_content'] = assist_content
            
            modification_records.append(rule_data)
            print(f"\n✅ 修改成功")
            print(f"📝 修改已记录（共 {len(modification_records)} 条）")
            
            input("\n按回车返回...")
            return
            
        except ValueError:
            print(f"❌ 无效输入: {parts[0]}")
            input("\n按回车返回...")
            return
    
    elif len(parts) == 2:
        # 两个位置 = 插入
        try:
            rel_pos1 = int(parts[0])
            rel_pos2 = int(parts[1])
            
            actual_line1 = target_line + rel_pos1
            actual_line2 = target_line + rel_pos2
            
            if actual_line1 < 0 or actual_line1 >= len(search_lines):
                print(f"❌ 无效位置: {rel_pos1}")
                input("\n按回车返回...")
                return
            if actual_line2 < 0 or actual_line2 >= len(search_lines):
                print(f"❌ 无效位置: {rel_pos2}")
                input("\n按回车返回...")
                return
            
            # 确保 actual_line1 < actual_line2
            if actual_line1 > actual_line2:
                actual_line1, actual_line2 = actual_line2, actual_line1
            
            print(f"\n✅ 已选择范围: 相对 {rel_pos1:+d} 到 {rel_pos2:+d} (第 {actual_line1 + search_start_offset + 1}-{actual_line2 + search_start_offset + 1} 行)")
            print()
            
            # 选择插入位置
            print("请选择插入位置:")
            print("  [1] 在范围之前插入（before）")
            print("  [2] 在范围之后插入（after）")
            print("  [3] 替换整个范围（replace range）")
            print("  [Q] 返回上一级")
            print()
            
            insert_choice = input("选择插入位置（1/2/3/Q）: ").strip().upper()
            if insert_choice == 'Q':
                return
            
            # 输入修改内容
            content = input_modification_content()
            if content is None:
                return
            
            # 应用修改
            new_lines = search_lines.copy()
            content_lines_final = [line.rstrip() for line in content.strip().split('\n') if line.strip()]
            
            if insert_choice == '1':
                # before
                indent = ''
                for ch in new_lines[actual_line1]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                indented = [indent + line for line in content_lines_final]
                new_lines[actual_line1:actual_line1] = indented
                position = 'before'
            elif insert_choice == '2':
                # after
                indent = ''
                for ch in new_lines[actual_line2]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                indented = [indent + line for line in content_lines_final]
                new_lines[actual_line2 + 1:actual_line2 + 1] = indented
                position = 'after'
            elif insert_choice == '3':
                # replace range
                indent = ''
                for ch in new_lines[actual_line1]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                indented = [indent + line for line in content_lines_final]
                new_lines[actual_line1:actual_line2 + 1] = indented
                position = 'replace'
            else:
                print(f"❌ 无效选择")
                input("\n按回车返回...")
                return
            
            # 预览
            if not preview_and_confirm(search_lines, new_lines, actual_line1, search_start_offset):
                return
            
            # 写回文件
            apply_changes_to_file(filepath, search_lines, new_lines, method_range, method_start_offset, class_content)
            
            # 记录修改
            full_class_name = rel_path.replace('.smali', '')
            parts_list = full_class_name.split('/')
            if parts_list and 'smali' in parts_list[0]:
                parts_list = parts_list[1:]
            full_class_name = '.'.join(parts_list)
            
            rule_data = {
                'type': 'smali',
                'name': f"修改{pure_class_name}_{method_name or 'class'}",
                'file': full_class_name,
                'anchor': anchor,
                'content': content,
                'position': position,
                'match_index': selected_match_idx + 1,
            }
            
            if method_name:
                rule_data['method'] = method_name
            if assist_content:
                rule_data['assist'] = str(assist_range or 5)
                rule_data['assist_content'] = assist_content
            
            modification_records.append(rule_data)
            print(f"\n✅ 修改成功")
            print(f"📝 修改已记录（共 {len(modification_records)} 条）")
            
            input("\n按回车返回...")
            return
            
        except ValueError:
            print(f"❌ 无效输入")
            input("\n按回车返回...")
            return
    
    else:
        print(f"❌ 无效输入")
        input("\n按回车返回...")
        return


def input_modification_content():
    """输入修改内容"""
    print("\n" + "=" * 60)
    print("输入修改内容")
    print("=" * 60)
    print()
    print("📝 输入规则:")
    print("  - 每行输入一条内容")
    print("  - 输入 END（大写或小写均可）保存并结束")
    print("  - 输入 Q 返回上一级")
    print()
    print("-" * 60)
    print("开始输入:")
    print("-" * 60)
    
    content_lines = []
    while True:
        try:
            line = input()
        except (KeyboardInterrupt, EOFError):
            print("\n⚠️ 已取消输入")
            return None
        
        if line.strip().upper() == "END":
            break
        if check_q_input(line):
            print("\n↩️ 返回上一级")
            return None
        content_lines.append(line)
    
    if not content_lines:
        print("⚠️ 未输入任何内容，已取消")
        return None
    
    content = '\n'.join(content_lines)
    print(f"\n✅ 修改内容已保存（{len(content_lines)} 行）")
    return content


def preview_and_confirm(old_lines, new_lines, highlight_idx, line_offset=0):
    """预览修改并确认"""
    import difflib
    
    print("\n" + "=" * 60)
    print("修改预览")
    print("=" * 60)
    print()
    
    # 使用 difflib 生成差异
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        lineterm='',
        n=PREVIEW_CONTEXT_LINES
    )
    
    print("图例:")
    print(f"  {RED}红色{RESET} = 删除的行")
    print(f"  {GREEN}绿色{RESET} = 新增的行")
    print()
    print("对比结果:")
    print("-" * 60)
    
    for line in diff:
        if line.startswith('---') or line.startswith('+++'):
            continue
        if line.startswith('@@'):
            print(f"  {line}")
            continue
        
        if line.startswith('-'):
            print(f"  {RED}{line}{RESET}")
        elif line.startswith('+'):
            print(f"  {GREEN}{line}{RESET}")
        else:
            print(f"  {line}")
    
    print("-" * 60)
    print()
    
    print("是否应用此修改？")
    print("  [Y] 确认应用")
    print("  [N] 取消修改")
    print("  [Q] 返回上一级")
    
    confirm = input("> ").strip().upper()
    if confirm == 'Q':
        return False
    if confirm != 'Y':
        print("❌ 已取消修改")
        return False
    
    return True


def apply_changes_to_file(filepath, old_lines, new_lines, method_range, method_start_offset, class_content):
    """将修改写回文件"""
    
    if method_range:
        # 方法内修改
        new_method_content = '\n'.join(new_lines)
        method_start = class_content[:method_start_offset].count('\n')
        # 找到方法在文件中的位置
        file_lines = class_content.split('\n')
        new_file_lines = file_lines[:method_start_offset] + new_lines + file_lines[method_start_offset + len(old_lines):]
        new_class_content = '\n'.join(new_file_lines)
    else:
        # 整个类修改
        new_class_content = '\n'.join(new_lines)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_class_content)


# ==================== INI 相关函数 ====================

def load_ini_metadata(config):
    """加载 INI 元信息"""
    metadata = {
        'author': None,
        'tutorial_url': None,
        'auto_open_tutorial': 'ask',
    }
    
    for section_name in ['元信息', 'metadata']:
        if config.has_section(section_name):
            metadata['author'] = config.get(section_name, 'author', fallback=None)
            metadata['tutorial_url'] = config.get(section_name, 'tutorial_url', fallback=None)
            auto_val = config.get(section_name, 'auto_open_tutorial', fallback='ask').strip().lower()
            if auto_val == 'true':
                metadata['auto_open_tutorial'] = 'true'
            elif auto_val == 'false':
                metadata['auto_open_tutorial'] = 'false'
            else:
                metadata['auto_open_tutorial'] = 'ask'
            break
    
    return metadata


def load_unified_ini(ini_files):
    all_patch_data = []
    all_arsc_rules = []
    outdated_ini_found = False
    
    for ini_path in ini_files:
        config = configparser.ConfigParser()
        config.read(ini_path, encoding='utf-8')
        
        # 加载并显示元信息
        metadata = load_ini_metadata(config)
        
        if metadata['author'] or metadata['tutorial_url']:
            print("=" * 60)
            print("补丁信息")
            print("=" * 60)
            print()
            
            if metadata['author']:
                print(f"👤 作者: {metadata['author']}")
            if metadata['tutorial_url']:
                print(f"🔗 教程: {metadata['tutorial_url']}")
            
            print()
            
            if metadata['tutorial_url']:
                auto_state = metadata.get('auto_open_tutorial', 'ask')
                
                if auto_state == 'true':
                    open_tutorial(metadata['tutorial_url'])
                    for section_name in ['元信息', 'metadata']:
                        if config.has_section(section_name) and config.has_option(section_name, 'auto_open_tutorial'):
                            config.set(section_name, 'auto_open_tutorial', 'ask')
                            with open(ini_path, 'w', encoding='utf-8') as f:
                                config.write(f)
                            break
                elif auto_state == 'false':
                    pass
                else:
                    choice = input("是否打开教程链接？(y/n/Q): ").strip().lower()
                    if choice == 'y':
                        open_tutorial(metadata['tutorial_url'])
            
            print()
        
        for section in config.sections():
            if section in ('元信息', 'metadata'):
                continue
            
            patch_type = config.get(section, 'type', fallback='smali').strip().lower()
            patch_name = config.get(section, 'name', fallback=section)
            description = config.get(section, 'description', fallback='').strip()
            
            # 读取版本号
            if config.has_option(section, 'ver'):
                ver = config.get(section, 'ver').strip()
            else:
                ver = '1.0'
                print(f"⚠️ [{patch_name}] 未检测到版本号，默认为旧版 (ver=1.0)")
                print(f"   此配置已过时，随时可能在后续更新中失效")
                print(f"   请尽快更新 INI 到版本 {INI_VERSION}")
                print()
                outdated_ini_found = True
            
            if ver not in SUPPORTED_INI_VERSIONS:
                print(f"⚠️ [{patch_name}] 不支持的 INI 版本: {ver}")
                continue
            
            if ver == "1.0":
                outdated_ini_found = True
                print(f"⚠️ [{patch_name}] INI 版本过旧 (ver=1.0)")
                print(f"   此配置已过时，随时可能在后续更新中失效")
                print(f"   请尽快更新 INI 到版本 {INI_VERSION}")
                print()
                # 使用 1.0 加载逻辑
                patch_data_list, arsc_rules = load_ini_v1_0(config, section, patch_name, patch_type)
                all_patch_data.extend(patch_data_list)
                all_arsc_rules.extend(arsc_rules)
            elif ver == "1.1":
                # 使用 1.1 加载逻辑
                patch_data_list, arsc_rules = load_ini_v1_1(config, section, patch_name, patch_type)
                all_patch_data.extend(patch_data_list)
                all_arsc_rules.extend(arsc_rules)
    
    if outdated_ini_found:
        print("=" * 60)
        print("⚠️ 检测到过时的 INI 配置 (ver=1.0)")
        print("=" * 60)
        print()
        print("过时的 INI 可能无法充分利用新功能：")
        print("  - 相对位置选择")
        print("  - 辅助定位值自动识别")
        print("  - 多位置插入")
        print()
        print(f"建议更新 INI 到版本 {INI_VERSION}")
        print("更新方法：重新执行手动修改并保存到 INI")
        print()
        input("按回车继续...")
    
    return all_patch_data, all_arsc_rules


def load_ini_v1_0(config, section, patch_name, patch_type):
    """加载 1.0 版本 INI（旧逻辑）"""
    all_patch_data = []
    all_arsc_rules = []
    
    check_marker_value = config.get(section, 'check', fallback=None)
    method_name = config.get(section, 'method', fallback=None)
    filename = config.get(section, 'file', fallback='').strip()
    force_add_dex = config.get(section, 'dex', fallback='').strip()
    
    anchor = config.get(section, 'anchor', fallback='').strip()
    content = config.get(section, 'content', fallback='').strip()
    position = config.get(section, 'position', fallback='before').strip().lower()
    nearby = config.get(section, 'nearby', fallback=None)
    nearby_content = config.get(section, 'nearby_content', fallback=None)
    exclude_content = config.get(section, 'exclude_content', fallback=None)
    replace_line = config.get(section, 'replace_line', fallback='false').strip().lower() == 'true'
    
    steps = []
    
    has_step = False
    for key in config.options(section):
        if re.match(r'^step\d+_', key):
            has_step = True
            break
    
    if has_step:
        step_num = 1
        while True:
            prefix = f"step{step_num}_"
            has_step_file = config.has_option(section, f"{prefix}file")
            has_step_anchor = config.has_option(section, f"{prefix}anchor")
            
            if has_step_file or has_step_anchor:
                step_filename = config.get(section, f"{prefix}file", fallback=filename).strip()
                step_anchor = config.get(section, f"{prefix}anchor", fallback=anchor).strip()
                step_content = config.get(section, f"{prefix}content", fallback=content).strip()
                step_position = config.get(section, f"{prefix}position", fallback=position).strip().lower()
                step_nearby = config.get(section, f"{prefix}nearby", fallback=nearby)
                step_nearby_content = config.get(section, f"{prefix}nearby_content", fallback=nearby_content)
                step_exclude_content = config.get(section, f"{prefix}exclude_content", fallback=exclude_content)
                step_replace_line = config.get(section, f"{prefix}replace_line", fallback=str(replace_line).lower()).strip().lower() == 'true'
                step_method = config.get(section, f"{prefix}method", fallback=method_name)
                
                step = {
                    'filename': step_filename,
                    'anchor': step_anchor,
                    'content': step_content,
                    'position': step_position,
                    'nearby': step_nearby,
                    'nearby_content': step_nearby_content,
                    'exclude_content': step_exclude_content,
                    'replace_line': step_replace_line,
                    'method': step_method,
                }
                steps.append(step)
                step_num += 1
            else:
                break
    else:
        if anchor or content:
            step = {
                'filename': filename,
                'anchor': anchor,
                'content': content,
                'position': position,
                'nearby': nearby,
                'nearby_content': nearby_content,
                'exclude_content': exclude_content,
                'replace_line': replace_line,
                'method': method_name,
            }
            steps.append(step)
    
    if steps:
        all_patch_data.append((patch_name, check_marker_value, method_name, steps, force_add_dex))
    
    return all_patch_data, all_arsc_rules


def load_ini_v1_1(config, section, patch_name, patch_type):
    """加载 1.1 版本 INI（新逻辑）"""
    all_patch_data = []
    all_arsc_rules = []
    
    method_name = config.get(section, 'method', fallback=None)
    check_marker_value = config.get(section, 'check', fallback=None)
    
    # 收集所有修改项编号
    mod_numbers = set()
    for key in config.options(section):
        match = re.match(r'^anchor(\d+)$', key)
        if match:
            mod_numbers.add(int(match.group(1)))
    
    # 加载每个修改项
    n_tags = []
    for n in sorted(mod_numbers):
        n_tag = {
            'anchor': config.get(section, f'anchor{n}', fallback='').strip(),
            'content': config.get(section, f'content{n}', fallback='').strip(),
            'position': config.get(section, f'position{n}', fallback='before').strip(),
            'replace_line': config.get(section, f'replace_line{n}', fallback='false').lower() == 'true',
            'replace_target': config.get(section, f'replace_target{n}', fallback=None),
            'assist': config.get(section, f'assist{n}', fallback=None),
            'assist_content': config.get(section, f'assist_content{n}', fallback=None),
            'exclude_content': config.get(section, f'exclude_content{n}', fallback=None),
            'replace_all': config.get(section, f'replace_all{n}', fallback='false').lower() == 'true',
            'match_index': config.get(section, f'match_index{n}', fallback=None),
        }
        
        if n_tag['anchor'] and n_tag['content']:
            n_tags.append(n_tag)
    
    # 收集 step 文件
    step_files = []
    step_numbers = set()
    for key in config.options(section):
        match = re.match(r'^step(\d+)_file$', key)
        if match:
            step_numbers.add(int(match.group(1)))
    
    if step_numbers:
        for step_num in sorted(step_numbers):
            file = config.get(section, f'step{step_num}_file', fallback='').strip()
            if file:
                step_files.append(file)
    else:
        file = config.get(section, 'file', fallback='').strip()
        if file:
            step_files.append(file)
    
    if n_tags and step_files:
        patch_data = {
            'name': patch_name,
            'method': method_name,
            'check': check_marker_value,
            'n_tags': n_tags,
            'files': step_files,
        }
        all_patch_data.append(patch_data)
    
    return all_patch_data, all_arsc_rules


def apply_patch_data(base, apk_path, patch_data):
    """应用补丁数据"""
    
    # 判断数据类型
    if isinstance(patch_data, dict) and 'n_tags' in patch_data:
        # 1.1 版本数据
        return apply_patch_data_v1_1(base, apk_path, patch_data)
    else:
        # 1.0 版本数据
        return apply_patch_data_v1_0(base, apk_path, patch_data)


def apply_patch_data_v1_0(base, apk_path, patch_data):
    """应用 1.0 版本补丁"""
    
    if len(patch_data) == 5:
        patch_name, check_marker_value, method_name, steps, force_add_dex = patch_data
    else:
        patch_name, check_marker_value, method_name, steps = patch_data
        force_add_dex = ''
    
    if check_marker_value:
        first_filename = steps[0].get('filename', '')
        filepath = resolve_smali_file(first_filename, base, interactive=True)
        if filepath:
            with open(filepath, 'rb') as f:
                content = f.read()
            if check_marker_value.encode('utf-8') in content:
                return patch_name, True, "已打过补丁"
    
    messages = []
    all_success = True
    
    for i, step in enumerate(steps):
        filename = step.get('filename', '')
        anchor = step.get('anchor', '')
        content = step.get('content', '')
        position = step.get('position', 'before')
        nearby = step.get('nearby', None)
        nearby_content = step.get('nearby_content', None)
        exclude_content = step.get('exclude_content', None)
        replace_line = step.get('replace_line', False)
        method = step.get('method', None)
        
        filepath = resolve_smali_file(filename, base, interactive=True)
        if not filepath:
            messages.append(f"step{i+1}: 未找到文件 {filename}")
            all_success = False
            continue
        
        method_range = None
        
        if method:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
            
            method_pattern = rf'\.method.*{re.escape(method)}.*\n'
            method_matches = list(re.finditer(method_pattern, file_content, re.IGNORECASE))
            
            if not method_matches:
                messages.append(f"step{i+1}: 未找到方法 {method}")
                all_success = False
                continue
            
            target_method_match = None
            
            if len(method_matches) == 1:
                target_method_match = method_matches[0]
            else:
                for m in method_matches:
                    method_start = m.start()
                    method_end = file_content.find(".end method", method_start)
                    if method_end == -1:
                        method_end = len(file_content)
                    else:
                        method_end += len(".end method")
                    
                    method_content = file_content[method_start:method_end]
                    if anchor.strip() in method_content:
                        target_method_match = m
                        break
                
                if not target_method_match:
                    messages.append(f"step{i+1}: 多个方法匹配 {method}，但都不包含 anchor")
                    all_success = False
                    continue
            
            method_start = target_method_match.start()
            method_end = file_content.find(".end method", method_start)
            if method_end == -1:
                method_end = len(file_content)
            else:
                method_end += len(".end method")
            
            start_line = file_content[:method_start].count('\n')
            end_line = file_content[:method_end].count('\n') + 1
            method_range = (start_line, end_line)
        
        ok, msg = apply_patch_step_v1_0(
            filepath, anchor, content, position,
            nearby, nearby_content, exclude_content, replace_line,
            auto_confirm=True,
            method_range=method_range
        )
        
        if ok:
            rel = os.path.relpath(filepath, base)
            messages.append(f"step{i+1} [{rel}]: {msg}")
        else:
            messages.append(f"step{i+1}: {msg}")
            all_success = False
    
    return patch_name, all_success, "; ".join(messages)


def apply_patch_data_v1_1(base, apk_path, patch_data):
    """应用 1.1 版本补丁"""
    
    patch_name = patch_data['name']
    method_name = patch_data.get('method', None)
    check_marker_value = patch_data.get('check', None)
    n_tags = patch_data['n_tags']
    files = patch_data['files']
    
    messages = []
    all_success = True
    
    # 检查是否已打过补丁
    if check_marker_value:
        first_filename = files[0] if files else ''
        filepath = resolve_smali_file(first_filename, base, interactive=True)
        if filepath:
            with open(filepath, 'rb') as f:
                file_content = f.read()
            if check_marker_value.encode('utf-8') in file_content:
                return patch_name, True, "已打过补丁"
    
    for filename in files:
        filepath = resolve_smali_file(filename, base, interactive=True)
        if not filepath:
            messages.append(f"未找到文件: {filename}")
            all_success = False
            continue
        
        for i, n_tag in enumerate(n_tags):
            anchor = n_tag['anchor']
            content = n_tag['content']
            position = n_tag['position']
            assist = n_tag.get('assist', None)
            assist_content = n_tag.get('assist_content', None)
            exclude_content = n_tag.get('exclude_content', None)
            replace_line = n_tag.get('replace_line', False)
            replace_target = n_tag.get('replace_target', None)
            replace_all = n_tag.get('replace_all', False)
            match_index = n_tag.get('match_index', None)
            if match_index:
                try:
                    match_index = int(match_index)
                except:
                    match_index = None
            
            method_range = None
            
            if method_name:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                
                method_pattern = rf'\.method.*{re.escape(method_name)}.*\n'
                method_matches = list(re.finditer(method_pattern, file_content, re.IGNORECASE))
                
                if not method_matches:
                    messages.append(f"N{i+1}: 未找到方法 {method_name}")
                    all_success = False
                    continue
                
                target_method_match = None
                
                if len(method_matches) == 1:
                    target_method_match = method_matches[0]
                else:
                    for m in method_matches:
                        method_start = m.start()
                        method_end = file_content.find(".end method", method_start)
                        if method_end == -1:
                            method_end = len(file_content)
                        else:
                            method_end += len(".end method")
                        
                        method_content = file_content[method_start:method_end]
                        if anchor.strip() in method_content:
                            target_method_match = m
                            break
                    
                    if not target_method_match:
                        messages.append(f"N{i+1}: 多个方法匹配 {method_name}，但都不包含 anchor")
                        all_success = False
                        continue
                
                method_start = target_method_match.start()
                method_end = file_content.find(".end method", method_start)
                if method_end == -1:
                    method_end = len(file_content)
                else:
                    method_end += len(".end method")
                
                start_line = file_content[:method_start].count('\n')
                end_line = file_content[:method_end].count('\n') + 1
                method_range = (start_line, end_line)
            
            ok, msg = apply_patch_step_v1_1(
                filepath, anchor, content, position,
                assist, assist_content, exclude_content, replace_line, replace_target,
                auto_confirm=True,
                method_range=method_range,
                replace_all=replace_all,
                match_index=match_index
            )
            
            rel = os.path.relpath(filepath, base)
            if ok:
                messages.append(f"[{rel}] N{i+1}: {msg}")
            else:
                messages.append(f"[{rel}] N{i+1}: {msg}")
                all_success = False
    
    return patch_name, all_success, "; ".join(messages)


def apply_patch_step_v1_0(filepath, anchor, content, position, nearby=None, nearby_content=None, exclude_content=None, replace_line=False, auto_confirm=False, method_range=None):
    """1.0 版本：nearby 二次搜索逻辑"""
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        file_content = f.read()
    
    file_lines = file_content.split('\n')
    target_line_idx = -1
    
    if method_range:
        search_start, search_end = method_range
        search_start = max(0, search_start)
        search_end = min(len(file_lines), search_end)
    else:
        search_start, search_end = 0, len(file_lines)
    
    if nearby and nearby_content:
        anchor_line_indices = []
        for i in range(search_start, search_end):
            if anchor.strip() in file_lines[i]:
                anchor_line_indices.append(i)
        
        if anchor_line_indices:
            for anchor_line_idx in anchor_line_indices:
                try:
                    search_range = int(nearby)
                except:
                    search_range = 5
                
                nearby_start = max(search_start, anchor_line_idx - search_range)
                nearby_end = min(search_end, anchor_line_idx + search_range + 1)
                
                found = False
                for i in range(nearby_start, nearby_end):
                    if not file_lines[i].strip():
                        continue
                    
                    if nearby_content.strip() in file_lines[i]:
                        if exclude_content:
                            exclude_start = max(search_start, i - 5)
                            exclude_end = min(search_end, i + 5)
                            excluded = False
                            for j in range(exclude_start, exclude_end):
                                if exclude_content.strip() in file_lines[j]:
                                    excluded = True
                                    break
                            if excluded:
                                continue
                        target_line_idx = i
                        found = True
                        break
                
                if found:
                    break
    else:
        for i in range(search_start, search_end):
            if anchor.strip() in file_lines[i]:
                if exclude_content:
                    exclude_start = max(search_start, i - 5)
                    exclude_end = min(search_end, i + 5)
                    excluded = False
                    for j in range(exclude_start, exclude_end):
                        if exclude_content.strip() in file_lines[j]:
                            excluded = True
                            break
                    if excluded:
                        continue
                target_line_idx = i
                break
    
    if target_line_idx == -1:
        return False, "未找到定位"
    
    content_lines = [line.rstrip() for line in content.strip().split('\n') if line.strip()]
    new_file_lines = file_lines.copy()
    
    if position == 'replace':
        original_line = new_file_lines[target_line_idx]
        indent = ''
        for ch in original_line:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        
        if replace_line:
            new_file_lines[target_line_idx] = indent + content_lines[0] if content_lines else ""
        else:
            match_text = nearby_content if nearby and nearby_content else anchor
            new_file_lines[target_line_idx] = original_line.replace(match_text.strip(), content.strip())
    elif position == 'before':
        indent = ''
        for ch in new_file_lines[target_line_idx]:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        indented = [indent + line for line in content_lines]
        new_file_lines[target_line_idx:target_line_idx] = indented
    elif position == 'after':
        indent = ''
        for ch in new_file_lines[target_line_idx]:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        indented = [indent + line for line in content_lines]
        new_file_lines[target_line_idx + 1:target_line_idx + 1] = indented
    else:
        return False, "position 错误"
    
    new_content = '\n'.join(new_file_lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True, "修改成功"


def apply_patch_step_v1_1(filepath, anchor, content, position, assist=None, assist_content=None, exclude_content=None, replace_line=False, replace_target=None, auto_confirm=False, method_range=None, replace_all=False, match_index=None):
    """1.1 版本：anchor 定位 + assist 辅助约束"""
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        file_content = f.read()
    
    file_lines = file_content.split('\n')
    
    if method_range:
        search_start, search_end = method_range
        search_start = max(0, search_start)
        search_end = min(len(file_lines), search_end)
    else:
        search_start, search_end = 0, len(file_lines)
    
    # 查找所有 anchor 匹配
    anchor_matches = []
    for i in range(search_start, search_end):
        if anchor.strip() in file_lines[i]:
            if exclude_content:
                exclude_start = max(search_start, i - 5)
                exclude_end = min(search_end, i + 5)
                excluded = False
                for j in range(exclude_start, exclude_end):
                    if exclude_content.strip() in file_lines[j]:
                        excluded = True
                        break
                if excluded:
                    continue
            anchor_matches.append(i)
    
    if not anchor_matches:
        return False, "未找到 anchor"
    
    # 确定目标行
    target_line_idx = None
    
    # 替换所有匹配时不需要确定单行
    if replace_all and position == 'replace':
        target_line_idx = anchor_matches[0]
    
    # 如果指定了 match_index，直接使用
    if target_line_idx is None and match_index and 0 < match_index <= len(anchor_matches):
        target_line_idx = anchor_matches[match_index - 1]
    
    if target_line_idx is None and assist_content:
        try:
            assist_range = int(assist) if assist else 5
        except:
            assist_range = 5
        
        for anchor_idx in anchor_matches:
            assist_start = max(search_start, anchor_idx - assist_range)
            assist_end = min(search_end, anchor_idx + assist_range + 1)
            
            found_assist = False
            for i in range(assist_start, assist_end):
                if assist_content.strip() in file_lines[i]:
                    found_assist = True
                    break
            
            if found_assist:
                target_line_idx = anchor_idx
                break
        
        if target_line_idx is None:
            return False, f"辅助定位值 '{assist_content}' 未在任何 anchor 附近找到"
    elif target_line_idx is None:
        if len(anchor_matches) == 1:
            target_line_idx = anchor_matches[0]
        else:
            return False, f"找到 {len(anchor_matches)} 处匹配，但未提供辅助定位值"
    
    # 执行修改
    content_lines = [line.rstrip() for line in content.strip().split('\n') if line.strip()]
    new_file_lines = file_lines.copy()
    
    # 替换所有匹配
    if replace_all and position == 'replace':
        for match_idx in anchor_matches:
            original_line = new_file_lines[match_idx]
            actual_target = replace_target if replace_target else anchor
            if replace_line:
                indent = ''
                for ch in original_line:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                new_file_lines[match_idx] = indent + content_lines[0] if content_lines else ""
            else:
                new_file_lines[match_idx] = original_line.replace(actual_target.strip(), content.strip())
        
        # 跳过后续处理
        new_content = '\n'.join(new_file_lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True, "修改成功"
    
    if position == 'replace' and not replace_all:
        original_line = new_file_lines[target_line_idx]
        indent = ''
        for ch in original_line:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        
        if replace_line:
            new_file_lines[target_line_idx] = indent + content_lines[0] if content_lines else ""
        else:
            actual_target = replace_target if replace_target else anchor
            new_file_lines[target_line_idx] = original_line.replace(actual_target.strip(), content.strip())
    elif position == 'before':
        indent = ''
        for ch in new_file_lines[target_line_idx]:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        indented = [indent + line for line in content_lines]
        new_file_lines[target_line_idx:target_line_idx] = indented
    elif position == 'after':
        indent = ''
        for ch in new_file_lines[target_line_idx]:
            if ch in (' ', '\t'):
                indent += ch
            else:
                break
        indented = [indent + line for line in content_lines]
        new_file_lines[target_line_idx + 1:target_line_idx + 1] = indented
    else:
        return False, "position 错误"
    
    new_content = '\n'.join(new_file_lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True, "修改成功"


def apply_all_patches(decompiled_dirs, patch_data_list, arsc_rules_list, has_arsc):
    """统一应用所有补丁"""
    
    patch_results = {}
    
    if patch_data_list:
        print(f"\n{'='*60}")
        print("应用 dex/smali 补丁")
        print(f"{'='*60}")
        for d in decompiled_dirs:
            apk_name, work_subdir, apk_path = d[:3]
            patch_results[apk_name] = {}
            
            for patch_data in patch_data_list:
                name, ok, msg = apply_patch_data(work_subdir, apk_path, patch_data)
                patch_results[apk_name][name] = (ok, msg)
                
                status = "✅" if ok else "❌"
                if len(decompiled_dirs) > 1:
                    print(f"  [{apk_name}] {status} {name}: {msg}")
                else:
                    print(f"  {status} {name}: {msg}")
    
    if len(decompiled_dirs) > 1:
        print(f"\n{'='*60}")
        print("批量修改总结")
        print(f"{'='*60}")
        
        success_count = 0
        fail_count = 0
        
        for apk_name, patches in patch_results.items():
            apk_success = all(ok for ok, _ in patches.values())
            if apk_success:
                success_count += 1
                print(f"  ✅ {apk_name}: 全部成功")
            else:
                fail_count += 1
                print(f"  ❌ {apk_name}: 有失败项")
                for patch_name, (ok, msg) in patches.items():
                    if not ok:
                        print(f"      - {patch_name}: {msg}")
        
        print(f"\n  总计: {success_count} 成功, {fail_count} 失败")


def check_patch_compatibility(decompiled_dirs, patch_data_list, arsc_rules_list):
    """检查补丁兼容性"""
    issues = []
    
    for d in decompiled_dirs:
        apk_name, work_subdir, apk_path = d[:3]
        
        for patch_data in patch_data_list:
            if isinstance(patch_data, dict) and 'n_tags' in patch_data:
                # 1.1 版本
                patch_name = patch_data['name']
                method_name = patch_data.get('method', None)
                files = patch_data['files']
                
                for filename in files:
                    filepath = resolve_smali_file(filename, work_subdir, interactive=False)
                    if not filepath:
                        issues.append(f"[{apk_name}] {patch_name}: 文件不存在 {filename}")
                    elif method_name:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        method_pattern = rf'\.method.*{re.escape(method_name)}.*\n'
                        if not re.search(method_pattern, content, re.IGNORECASE):
                            issues.append(f"[{apk_name}] {patch_name}: 方法不存在 {method_name}")
            else:
                # 1.0 版本
                if len(patch_data) == 5:
                    patch_name, check_marker, method_name, steps, force_add_dex = patch_data
                else:
                    patch_name, check_marker, method_name, steps = patch_data
                
                for step in steps:
                    filename = step.get('filename', '')
                    filepath = resolve_smali_file(filename, work_subdir, interactive=False)
                    if not filepath:
                        issues.append(f"[{apk_name}] {patch_name}: 文件不存在 {filename}")
    
    return issues


# ==================== 保存修改到 INI ====================

def save_modifications_to_ini():
    global modification_records
    
    if not modification_records:
        print("⚠️ 没有修改记录")
        return
    
    clear_screen()
    print("=" * 60)
    print("保存修改到 INI")
    print("=" * 60)
    print()
    
    print("修改记录:")
    for i, record in enumerate(modification_records):
        print(f"  [{i+1}] {record.get('name', 'unnamed')}")
    
    print()
    
    ini_name = input("输入 INI 文件名（Q 返回）: ").strip()
    if check_q_input(ini_name):
        return
    
    if not ini_name:
        ini_name = f"patch_{int(time.time())}"
    
    if not ini_name.endswith('.ini'):
        ini_name += '.ini'
    
    ini_path = os.path.join(PATCH_INI_DIR, ini_name)
    
    config = configparser.ConfigParser()
    
    # 添加元信息
    config.add_section('元信息')
    
    author = input("请输入作者署名（直接回车跳过）: ").strip()
    if author:
        config.set('元信息', 'author', author)
    
    tutorial_url = input("请输入教程链接（直接回车跳过）: ").strip()
    if tutorial_url:
        config.set('元信息', 'tutorial_url', tutorial_url)
        
        auto_open = input("是否自动打开教程？(y/n): ").strip().lower() == 'y'
        config.set('元信息', 'auto_open_tutorial', str(auto_open).lower())
    
    # 保存修改记录
    for i, record in enumerate(modification_records):
        section_name = record.get('name', f'patch{i+1}')
        # 如果 section 已存在，添加序号
        if config.has_section(section_name):
            j = 2
            while config.has_section(f"{section_name}_{j}"):
                j += 1
            section_name = f"{section_name}_{j}"
        config.add_section(section_name)
        
        config.set(section_name, 'ver', INI_VERSION)
        config.set(section_name, 'type', record.get('type', 'smali'))
        config.set(section_name, 'file', record.get('file', ''))
        
        if 'method' in record:
            config.set(section_name, 'method', record['method'])
        
        # 使用 anchor1/content1 格式
        config.set(section_name, 'anchor1', record.get('anchor', ''))
        config.set(section_name, 'content1', record.get('content', ''))
        config.set(section_name, 'position1', record.get('position', 'replace'))
        
        if record.get('replace_line'):
            config.set(section_name, 'replace_line1', 'true')
        if record.get('replace_target') and record['replace_target'] != record.get('anchor', ''):
            config.set(section_name, 'replace_target1', record['replace_target'])
        if record.get('replace_all'):
            config.set(section_name, 'replace_all1', 'true')
        if record.get('match_index'):
            config.set(section_name, 'match_index1', str(record['match_index']))
        if record.get('assist'):
            config.set(section_name, 'assist1', str(record['assist']))
        if record.get('assist_content'):
            config.set(section_name, 'assist_content1', record['assist_content'])
        if record.get('exclude_content'):
            config.set(section_name, 'exclude_content1', record['exclude_content'])
    
    with open(ini_path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    print(f"\n✅ 已保存到: {ini_path}")
    print(f"📝 共保存 {len(modification_records)} 条修改记录")
    
    input("\n按回车返回...")


# ==================== 反编译/回编译函数 ====================

def decompile_apk_parallel(apk_path, work_subdir, apk_size, result_holder, mode, progress_dict, lock):
    try:
        apk_name = os.path.basename(apk_path)
        
        if mode == "dex_only":
            cmd = ["apktool", "d", "-r", "-f", apk_path, "-o", work_subdir]
        else:
            cmd = ["apktool", "d", "-f", apk_path, "-o", work_subdir]
        
        stop_event = threading.Event()
        
        def watch():
            start_time = time.time()
            last_update = 0
            
            while not stop_event.is_set():
                now = time.time()
                if now - last_update >= PROGRESS_UPDATE_INTERVAL:
                    last_update = now
                    
                    if os.path.exists(work_subdir):
                        total = 0
                        for root, dirs, files in os.walk(work_subdir):
                            for f in files:
                                try:
                                    total += os.path.getsize(os.path.join(root, f))
                                except:
                                    pass
                        
                        percent = int(total / (apk_size * DECOMPILE_SIZE_MULTIPLIER) * 100) if apk_size > 0 else 0
                        percent = min(percent, 99)
                        
                        size_str = format_size(total)
                        elapsed = now - start_time
                        speed = total / elapsed if elapsed > 0 else 0
                        speed_str = format_size(speed)
                        
                        with lock:
                            progress_dict[apk_name] = {
                                "percent": percent,
                                "size_str": size_str,
                                "speed_str": speed_str,
                            }
                
                time.sleep(0.2)
        
        result_holder["done"] = False
        
        t = threading.Thread(target=watch)
        t.daemon = True
        t.start()
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        stop_event.set()
        t.join(timeout=1)
        
        result_holder["done"] = True
        result_holder["success"] = result.returncode == 0
        result_holder["error"] = result.stderr if result.returncode != 0 else None
        
        if result.returncode == 0:
            with lock:
                progress_dict[apk_name] = {
                    "percent": 100,
                    "size_str": "",
                    "speed_str": "",
                }
    
    except Exception as e:
        result_holder["success"] = False
        result_holder["error"] = str(e)


def recompile_apk(work_subdir, apk_name, apk_path=None):
    output_apk = os.path.join(OUTPUT_DIR_BASE, f"{apk_name}_patched.apk")
    
    print(f"  回编译 {apk_name}...")
    
    os.makedirs(OUTPUT_DIR_BASE, exist_ok=True)
    
    if os.path.exists(output_apk):
        os.remove(output_apk)
    
    target_size = os.path.getsize(apk_path) if apk_path and os.path.exists(apk_path) else 0
    
    cmd = ["apktool", "b", work_subdir, "-o", output_apk, "-f", "--copy-original"]
    success, stdout, stderr = run_with_progress(
        f"回编译 {apk_name}",
        work_subdir,
        target_size,
        cmd,
        cwd=WORK_DIR,
        check_dirs=[os.path.join(work_subdir, "build")],
        size_multiplier=RECOMPILE_SIZE_MULTIPLIER,
    )
    
    if not success:
        if stderr:
            print(f"\n编译错误详情:")
            stderr_lines = stderr.strip().split('\n')
            for line in stderr_lines[-20:]:
                print(f"  {line}")
        return False, "编译失败"
    
    if not os.path.exists(output_apk):
        return False, "编译后 output_apk 不存在"
    
    print_progress(f"回编译 {apk_name}", 100, format_size(os.path.getsize(output_apk)), "")
    
    return True, output_apk


def recompile_all_dirs(decompiled_dirs):
    total = len(decompiled_dirs)
    success_count = 0
    fail_count = 0
    
    for idx, d in enumerate(decompiled_dirs):
        apk_name, work_subdir, apk_path = d[:3]
        print(f"\n[{idx+1}/{total}] 回编译 {apk_name}...")
        ok, result = recompile_apk(work_subdir, apk_name, apk_path)
        if ok:
            print(f"✅ 完成: {result}")
            success_count += 1
        else:
            print(f"❌ {result}")
            fail_count += 1
        
        if idx < total - 1:
            print()
    
    if total > 1:
        print(f"\n{'='*60}")
        print(f"回编译总结: {success_count} 成功, {fail_count} 失败")
        print(f"{'='*60}")


def monitor_progress(desc, work_subdir, target_size, stop_event, check_dirs=None, size_multiplier=6):
    start_time = time.time()
    last_update = 0
    
    if check_dirs is None:
        check_dirs = [work_subdir]
    
    while not stop_event.is_set():
        now = time.time()
        if now - last_update >= PROGRESS_UPDATE_INTERVAL:
            last_update = now
            
            total_size = 0
            file_count = 0
            
            for check_dir in check_dirs:
                if os.path.exists(check_dir):
                    for root, dirs, files in os.walk(check_dir):
                        file_count += len(files)
                        for f in files:
                            try:
                                total_size += os.path.getsize(os.path.join(root, f))
                            except:
                                pass
            
            if target_size > 0:
                percent = min(int(total_size / (target_size * size_multiplier) * 100), 99)
            else:
                percent = 0
            
            elapsed = now - start_time
            speed = total_size / elapsed if elapsed > 0 else 0
            
            if total_size > 0 or file_count > 0:
                print_progress(
                    desc,
                    percent,
                    format_size(total_size),
                    format_size(speed),
                )
        
        time.sleep(0.2)


def run_with_progress(desc, work_subdir, target_size, cmd, cwd=None, check_dirs=None, size_multiplier=6):
    stop_event = threading.Event()
    
    t = threading.Thread(
        target=monitor_progress,
        args=(desc, work_subdir, target_size, stop_event, check_dirs, size_multiplier),
    )
    t.daemon = True
    t.start()
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )
    
    stdout, stderr = process.communicate()
    
    stop_event.set()
    t.join(timeout=1)
    
    return process.returncode == 0, stdout, stderr


# ==================== 添加 dex ====================

def collect_dex_info(apk_path, build_dir):
    """收集原 APK 和 build/apk 目录中的 dex 信息"""
    
    info = {
        'apk_dex_count': 0,
        'apk_dex_crc32': set(),
        'build_dex_count': 0,
        'build_dex_crc32': set(),
        'all_crc32': set(),
        'next_num': 1
    }
    
    if apk_path and os.path.exists(apk_path):
        try:
            import zipfile
            with zipfile.ZipFile(apk_path, 'r') as zf:
                dex_names = [f for f in zf.namelist() if f.endswith('.dex')]
                info['apk_dex_count'] = len(dex_names)
                for dex_name in dex_names:
                    with zf.open(dex_name) as dex_file:
                        crc = format(zlib.crc32(dex_file.read()) & 0xFFFFFFFF, '08x')
                        info['apk_dex_crc32'].add(crc)
                        info['all_crc32'].add(crc)
        except:
            pass
    
    if build_dir and os.path.exists(build_dir):
        dex_files = glob.glob(os.path.join(build_dir, "classes*.dex"))
        info['build_dex_count'] = len(dex_files)
        for dex_path in dex_files:
            try:
                with open(dex_path, 'rb') as f:
                    crc = format(zlib.crc32(f.read()) & 0xFFFFFFFF, '08x')
                    info['build_dex_crc32'].add(crc)
                    info['all_crc32'].add(crc)
            except:
                pass
    
    info['next_num'] = info['apk_dex_count'] + info['build_dex_count'] + 1
    
    return info


def get_next_dex_name(next_num):
    if next_num <= 1:
        return "classes.dex"
    else:
        return f"classes{next_num}.dex"


def add_dex_files(decompiled_dirs, selected_dex):
    """添加 dex 文件"""
    
    total_added = 0
    total_skipped = 0
    
    for d in decompiled_dirs:
        apk_name, work_subdir, apk_path = d[:3]
        build_dir = os.path.join(work_subdir, "build", "apk")
        os.makedirs(build_dir, exist_ok=True)
        
        dex_info = collect_dex_info(apk_path, build_dir)
        all_crc32 = dex_info['all_crc32']
        next_num = dex_info['next_num']
        
        print(f"\n  {apk_name}: 原APK有{dex_info['apk_dex_count']}个dex, build/apk已有{dex_info['build_dex_count']}个")
        
        for dex_file in selected_dex:
            try:
                with open(dex_file, 'rb') as f:
                    dex_crc = format(zlib.crc32(f.read()) & 0xFFFFFFFF, '08x')
            except:
                dex_crc = None
            
            if not dex_crc:
                print(f"  ❌ 无法计算 CRC32: {os.path.basename(dex_file)}")
                total_skipped += 1
                continue
            
            if dex_crc in all_crc32:
                print(f"  ⚠️ {apk_name}: 跳过重复 {os.path.basename(dex_file)} (crc32:{dex_crc} 已存在)")
                total_skipped += 1
                continue
            
            new_dex_name = get_next_dex_name(next_num)
            dest_path = os.path.join(build_dir, new_dex_name)
            shutil.copy2(dex_file, dest_path)
            
            print(f"  ✅ {apk_name}: 添加 {os.path.basename(dex_file)} -> {new_dex_name} (crc32:{dex_crc})")
            
            all_crc32.add(dex_crc)
            next_num += 1
            total_added += 1
    
    return total_added, total_skipped


# ==================== 选择函数 ====================

def select_items(title, items, display_names):
    if not items:
        clear_screen()
        print("=" * 60)
        print(f"❌ {title}: 没有可选项")
        print("=" * 60)
        print()
        
        if "APK" in title:
            print(f"📁 请将 APK 文件放入以下目录:")
            print(f"   {INPUT_DIR}")
        elif "INI" in title:
            print(f"📁 请将 INI 配置文件放入以下目录:")
            print(f"   {PATCH_INI_DIR}")
        elif "DEX" in title:
            print(f"📁 请将 DEX 文件放入以下目录:")
            print(f"   {PATCH_CLASSES_DIR}")
        
        print()
        print("-" * 60)
        input("按回车返回...")
        return None
    
    flags = [False] * len(items)
    
    while True:
        clear_screen()
        print("=" * 60)
        print(title)
        print("=" * 60)
        print()
        
        for i, (name, flag) in enumerate(zip(display_names, flags)):
            status = "✅ 已选" if flag else "❌ 未选"
            print(f"  [{i+1}] {status}  {name}")
        
        print()
        print("输入数字选择/取消对应项（如：1 2 3）")
        print("输入 0 = 全选")
        print("输入 Q = 返回")
        print("直接回车 = 确认")
        print("-" * 60)
        
        try:
            choice = input("> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None
        
        if choice == "":
            break
        if check_q_input(choice):
            return None
        if choice == "0":
            flags = [True] * len(items)
        else:
            parts = choice.split()
            for part in parts:
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < len(items):
                        flags[idx] = not flags[idx]
    
    return [items[i] for i in range(len(items)) if flags[i]]


def select_apks():
    apk_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.apk")))
    return select_items("选择 APK 文件", apk_files, [os.path.basename(f) for f in apk_files])


def select_ini_files():
    ini_files = sorted(glob.glob(os.path.join(PATCH_INI_DIR, "*.ini")))
    return select_items("选择 INI 补丁配置", ini_files, [os.path.basename(f) for f in ini_files])


def select_dex_files():
    dex_files = sorted(glob.glob(os.path.join(PATCH_CLASSES_DIR, "*.dex")))
    return select_items("选择要添加的 DEX 文件", dex_files, [os.path.basename(f) for f in dex_files])


def select_saved_project():
    if not os.path.exists(SAVE_DIR):
        clear_screen()
        print("=" * 60)
        print("❌ save/ 目录不存在")
        print("=" * 60)
        print()
        print(f"📁 保存的工程目录:")
        print(f"   {SAVE_DIR}")
        print()
        input("按回车返回...")
        return None
    
    projects = sorted(glob.glob(os.path.join(SAVE_DIR, "*")))
    if not projects:
        clear_screen()
        print("=" * 60)
        print("❌ 没有已保存的工程")
        print("=" * 60)
        print()
        input("按回车返回...")
        return None
    
    while True:
        clear_screen()
        print("=" * 60)
        print("选择工程")
        print("=" * 60)
        print()
        
        for i, p in enumerate(projects):
            print(f"  [{i+1}] {os.path.basename(p)}")
        
        print()
        print("输入数字选择工程")
        print("输入 Q = 返回")
        print("-" * 60)
        
        try:
            choice = input("> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None
        
        if check_q_input(choice):
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                return projects[idx]
    
    return None


def select_decompile_mode():
    clear_screen()
    print("=" * 60)
    print("选择反编译方式")
    print("=" * 60)
    print()
    print("  [1] 仅 dex（跳过资源，快速）")
    print("  [2] 完整反编译（暂不可用）")
    print()
    print("直接回车 = 仅 dex")
    print("-" * 60)
    
    try:
        choice = input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        return "dex_only"
    
    if choice == "2":
        print(f"\n⚠️ 完整反编译暂不可用")
        print(f"  原因：Android 15 (API 35+) 的 private 资源导致回编译失败")
        print(f"  已自动切换到仅 dex 模式")
        input("\n按回车继续...")
        return "dex_only"
    return "dex_only"


# ==================== 工程保存 ====================

def save_project(work_subdir, apk_name, apk_path=None, is_from_project=False):
    clear_screen()
    print("=" * 60)
    print("保存工程")
    print("=" * 60)
    print()
    
    project_name = input("输入工程名（Q 返回）: ").strip()
    if check_q_input(project_name):
        return
    if not project_name:
        project_name = apk_name
    
    os.makedirs(SAVE_DIR, exist_ok=True)
    dst = os.path.join(SAVE_DIR, project_name)
    
    if os.path.exists(dst):
        overwrite = input(f"工程 {project_name} 已存在，覆盖？(y/n): ").strip().lower() == 'y'
        if not overwrite:
            return
        shutil.rmtree(dst)
    
    shutil.copytree(work_subdir, dst)
    
    if apk_path and os.path.exists(apk_path):
        apk_basename = os.path.basename(apk_path)
        shutil.copy2(apk_path, os.path.join(dst, apk_basename))
        print(f"  ✅ APK 已保存到工程: {apk_basename}")
    
    print(f"  ✅ 工程已保存: {dst}")
    return


# ==================== 主菜单 ====================

def unified_main_menu(decompiled_dirs, has_arsc, is_batch, is_from_project=False):
    global modification_records
    
    patch_data_list = []
    arsc_rules_list = []
    added_dex_count = 0
    
    total_apks = len(decompiled_dirs)
    simple_dirs = [(d[0], d[1], d[2]) for d in decompiled_dirs]
    
    while True:
        clear_screen()
        
        print("╔" + "═" * 58 + "╗")
        
        if total_apks == 1:
            apk_name, work_subdir, apk_path = decompiled_dirs[0][:3]
            print(f"║  📱 APK: {apk_name}")
            print(f"║  📂 目录: {os.path.basename(work_subdir)}")
        else:
            print(f"║  📱 批量模式")
            print(f"║  📦 共 {total_apks} 个 APK")
            print(f"║  ⚠️  部分功能受限")
        
        print("╠" + "═" * 58 + "╣")
        
        status_items = []
        
        if added_dex_count:
            status_items.append(f"💊 dex:{added_dex_count}")
        if patch_data_list:
            status_items.append(f"🔧 smali:{len(patch_data_list)}")
        if modification_records:
            status_items.append(f"📝 记录:{len(modification_records)}")
        
        if status_items:
            status_line = " │ ".join(status_items)
            print(f"║  {status_line}")
        else:
            print(f"║  💤 暂无修改")
        
        print("╠" + "═" * 58 + "╣")
        
        menu_items = []
        menu_items.append(("1", "💊 添加 dex"))
        
        if not is_batch:
            menu_items.append(("2", "🔧 手动修改 dex"))
        else:
            menu_items.append(("2", "🔧 手动修改 dex（批量不可用）"))
        
        menu_items.append(("3", "📋 从 INI 加载补丁"))
        menu_items.append(("4", "🚫 手动修改 arsc（暂不可用）"))
        
        if modification_records:
            menu_items.append(("5", "💾 保存修改到 INI"))
        
        if not is_batch and not is_from_project:
            menu_items.append(("6", "📦 保存工程"))
        
        menu_items.append(("7", "🏗️  回编译 APK"))
        
        for key, label in menu_items:
            print(f"║  [{key}] {label}")
        
        print(f"║  [Q] 退出")
        print("╚" + "═" * 58 + "╝")
        print()
        
        try:
            choice = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "quit"
        
        if check_q_input(choice):
            return "quit"
        
        if choice == "1":
            selected_dex = select_dex_files()
            if selected_dex:
                total_added, total_skipped = add_dex_files(decompiled_dirs, selected_dex)
                
                if total_added > 0 or total_skipped > 0:
                    print(f"\n📊 总计: 添加 {total_added} 个，跳过 {total_skipped} 个重复")
                
                if total_added > 0:
                    added_dex_count += total_added
                
                input("\n按回车继续...")
        
        elif choice == "2" and not is_batch:
            _, work_subdir, _ = decompiled_dirs[0][:3]
            manual_edit_dex(work_subdir)
        
        elif choice == "2" and is_batch:
            print(f"\n⚠️ 批量模式下无法手动修改 dex")
            print(f"  请使用 INI 加载补丁代替")
            input("\n按回车返回...")
        
        elif choice == "3":
            selected_ini = select_ini_files()
            if selected_ini:
                new_patch_data, new_arsc_rules = load_unified_ini(selected_ini)
                
                if len(decompiled_dirs) > 1:
                    issues = check_patch_compatibility(simple_dirs, new_patch_data, [])
                    if issues:
                        print(f"\n⚠️ 发现 {len(issues)} 个兼容性问题:")
                        for issue in issues:
                            print(f"  {issue}")
                        confirm = input(f"\n是否继续应用？(y/n): ").strip().lower()
                        if confirm != 'y':
                            continue
                
                apply_all_patches(simple_dirs, new_patch_data, [], False)
                
                if new_patch_data:
                    patch_data_list.extend(new_patch_data)
                
                input("\n按回车继续...")
        
        elif choice == "4":
            print(f"\n⚠️ arsc 修改功能暂不可用")
            print(f"  原因：Android 15 (API 35+) 的 private 资源导致回编译失败")
            print(f"  替代方案：使用mt管理器直接修改 resources.arsc")
            input("\n按回车返回...")
        
        elif choice == "5" and modification_records:
            save_modifications_to_ini()
        
        elif choice == "6" and not is_batch and not is_from_project:
            apk_name, work_subdir, apk_path = decompiled_dirs[0][:3]
            save_project(work_subdir, apk_name, apk_path, False)
        
        elif choice == "7":
            recompile_all_dirs(simple_dirs)
            input("\n按回车返回...")
    
    return "quit"


# ==================== 主函数 ====================

def main():
    os.chdir(WORK_DIR)
    
    for d in [INPUT_DIR, PATCH_CLASSES_DIR, PATCH_INI_DIR]:
        os.makedirs(d, exist_ok=True)
    check_update()
    check_dependencies()
    
    while True:
        has_projects = False
        if os.path.exists(SAVE_DIR):
            projects = glob.glob(os.path.join(SAVE_DIR, "*"))
            if projects:
                has_projects = True
        
        apk_path = None
        apk_name = None
        work_subdir = None
        is_from_project = False
        decompile_mode = "dex_only"
        selected_apks = []
        is_batch = False
        
        if has_projects:
            while True:
                clear_screen()
                print("=" * 60)
                print("APK 反编译修改 工具")
                print("=" * 60)
                print()
                print("  [1] 选择 APK 反编译")
                print("  [2] 从工程加载")
                print("  [Q] 退出")
                print()
                print("-" * 60)
                
                try:
                    choice = input("> ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("已退出")
                    sys.exit(0)
                
                if choice == "1":
                    selected_apks = select_apks()
                    if selected_apks:
                        is_batch = len(selected_apks) > 1
                        decompile_mode = select_decompile_mode()
                    else:
                        continue
                    break
                
                elif choice == "2":
                    project_dir = select_saved_project()
                    if project_dir:
                        apk_name = os.path.basename(project_dir)
                        work_subdir = project_dir
                        
                        apk_in_project = find_apk_in_project(work_subdir)
                        if apk_in_project:
                            apk_path = apk_in_project
                        else:
                            apk_path = None
                        
                        is_from_project = True
                        
                        unified_main_menu(
                            [(apk_name, work_subdir, apk_path, 0, 0)],
                            has_arsc=False,
                            is_batch=False,
                            is_from_project=True,
                        )
                    continue
                
                elif check_q_input(choice):
                    print("已退出")
                    sys.exit(0)
                else:
                    continue
        else:
            selected_apks = select_apks()
            if selected_apks:
                is_batch = len(selected_apks) > 1
                decompile_mode = select_decompile_mode()
            else:
                print("已退出")
                sys.exit(0)
        
        if not is_from_project:
            total = len(selected_apks)
            decompiled_dirs = []
            all_success = True
            
            progress_dict = {}
            progress_lock = print_lock
            result_holders = {}
            threads = []
            
            for apk_path in selected_apks:
                apk_name = os.path.splitext(os.path.basename(apk_path))[0]
                work_subdir = os.path.join(BUILD_DIR, apk_name)
                os.makedirs(work_subdir, exist_ok=True)
                
                apk_size = os.path.getsize(apk_path)
                result_holder = {"success": False, "error": None, "done": False}
                
                with progress_lock:
                    progress_dict[apk_name] = {"percent": 0, "size_str": "", "speed_str": ""}
                
                result_holders[apk_name] = result_holder
                
                t = threading.Thread(
                    target=decompile_apk_parallel,
                    args=(apk_path, work_subdir, apk_size, result_holder, decompile_mode, progress_dict, progress_lock),
                )
                t.daemon = True
                threads.append((apk_name, apk_path, work_subdir, t))
                t.start()
            
            all_done = False
            while not all_done:
                all_done = True
                for apk_name, apk_path, work_subdir, t in threads:
                    if not result_holders[apk_name].get("done", False):
                        all_done = False
                        break
                
                with print_lock:
                    sys.stdout.write("\033[s")
                    
                    lines_to_clear = len(progress_dict)
                    for _ in range(lines_to_clear):
                        sys.stdout.write("\033[2K")
                        sys.stdout.write("\033[1B")
                    
                    sys.stdout.write(f"\033[{lines_to_clear}F")
                    
                    for apk_name, info in progress_dict.items():
                        percent = info.get("percent", 0)
                        size_str = info.get("size_str", "")
                        speed_str = info.get("speed_str", "")
                        
                        bar_length = 20
                        filled = int(bar_length * percent / 100) if percent > 0 else 0
                        bar = "█" * filled + "░" * (bar_length - filled)
                        
                        if size_str and speed_str:
                            sys.stdout.write(f"\r\033[2K  {apk_name} [{bar}] {percent:3d}%  {size_str} ({speed_str}/s)\n")
                        else:
                            sys.stdout.write(f"\r\033[2K  {apk_name} [{bar}] {percent:3d}%\n")
                    
                    sys.stdout.write("\033[u")
                    sys.stdout.flush()
                
                time.sleep(0.5)
            
            for apk_name, apk_path, work_subdir, t in threads:
                t.join()
                if result_holders[apk_name].get("success", False):
                    print(f"✅ 反编译完成: {apk_name}")
                    decompiled_dirs.append((apk_name, work_subdir, apk_path, 0, 0))
                else:
                    print(f"❌ 反编译失败: {apk_name}")
                    if result_holders[apk_name].get("error"):
                        print(f"  {result_holders[apk_name]['error'][:500]}")
                    all_success = False
            
            if all_success and len(decompiled_dirs) == total:
                unified_main_menu(
                    decompiled_dirs,
                    has_arsc=False,
                    is_batch=is_batch,
                    is_from_project=False,
                )
            
            cleanup_temp()
    
    print("\n已退出")


if __name__ == "__main__":
    main()