# XKspeed

一个在 Termux 中运行的 APK 自动化处理工具，支持反编译、smali 修改、ARSC 资源修改、INI 补丁应用、工程保存、回编译以及多 APK 批处理。

当前版本：**1.3**

## 功能

- 检查并安装必要依赖：apktool、unzip、zip、apkeditor
- 支持从 APK 或已保存工程反编译
- 支持快速反编译（仅 dex）和完整反编译（dex + ARSC）
- 手动修改 smali，提供唯一锚点定位与辅助定位
- 支持 ARSC XML 资源文件手动修改
- ARSC 同资源多次修改自动去重，只保留最后一次
- 快速反编译后进入手动 ARSC 时自动现场解码
- 读取并应用 INI 补丁配置
- 添加额外 dex 文件
- 保存工程为独立目录，工程自包含原始 APK
- 回编译生成补丁后的 APK
- 支持多 APK 批量处理
- 全局日志记录，自动保存运行日志
- 启动时检查 GitHub 云更新，可按 Enter 跳过

## 使用方法

### 环境准备

在 Termux 中安装 Python：

```bash
pkg update -y
pkg install python -y
```

其它依赖（apktool、zip、unzip、apkeditor）脚本运行时会自动检查并提示安装。

### 下载脚本

从 GitHub Releases 下载最新版：

https://github.com/XKspeed/auto-editapks/releases/

下载 `xkspeed.py` 文件到 Termux 中即可运行。

### 运行

```bash
python xkspeed.py
```

启动后按菜单提示操作。

## 目录结构

```
.
├── xkspeed.py          # 主程序
├── input/              # 放入待处理 APK
├── output/             # 输出目录
├── patch_ini/          # 存放 INI 补丁配置
├── patch_classes/      # 可选，额外 dex 或 class
├── save/               # 保存的工程目录
├── temp_build/         # 反编译临时目录
└── log/                # 运行日志
```

## 工作流程

1. 将 APK 放入 `input/` 目录
2. 运行脚本，选择 APK
3. 选择反编译模式：
   - 仅 dex：快速，跳过资源
   - 完整反编译：apktool 反编译 dex + APKEditor 解码 ARSC
4. 在主菜单选择操作：
   - 添加 dex
   - 手动修改 dex
   - 从 INI 加载补丁
   - 手动修改 arsc
   - 保存修改到 INI
   - 保存工程
   - 回编译 APK
5. 回编译结果输出到 `output/`

## ARSC 修改

- 手动修改 ARSC 前会读取 `config.json` 中的 `arsc_res_dir`
- 快速反编译模式下进入手动 ARSC 修改时，会自动现场解码 ARSC
- 同一资源多次修改时，自动按 `file + origin + res_name` 去重，只保留最后一次修改
- 支持导出 ARSC 修改为 INI

## 工程保存

保存工程时：

- 移动反编译目录到 `save/` 下
- 复制原始 APK 为工程内 `original.apk`
- 更新工程内 `config.json`
- `input/` 中原始 APK 保持不变

从主菜单选择“从工程加载”即可继续之前的工作。

## INI 配置

INI 补丁文件放在 `patch_ini/` 目录下，脚本会自动读取。

### 基本结构

```ini
[元信息]
author = 作者
tutorial_url = https://example.com

[补丁名称]
ver = 1.1
type = smali
name = 补丁说明
description = 补丁描述
file = 目标类名
method = 目标方法
anchor = 定位内容
content = 要写入的内容
position = before
```

### 字段说明

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `ver` | 是 | INI 配置版本，支持 `1.0` 和 `1.1` |
| `type` | 否 | 补丁类型，默认 `smali`，ARSC 为 `arsc` |
| `name` | 否 | 补丁名称，默认使用 section 名 |
| `description` | 否 | 补丁描述 |
| `file` | 是 | 目标 smali 类，如 `com.example.MainActivity` |
| `method` | 否 | 目标方法名，留空则在整个类中定位 |
| `anchor` | 是 | 定位锚点内容 |
| `content` | 是 | 要插入或替换的内容 |
| `position` | 否 | `before`、`after` 或 `replace`，默认 `before` |

### ARSC 修改示例

```ini
[修改字符串]
ver = 2.0
type = arsc
file = strings
name = app_name
origin = values
new_values = 新应用名称
```

字段说明：

- `type`：必须为 `arsc`
- `file`：资源类型，如 `strings`、`arrays`、`styles` 等
- `name`：资源名称
- `origin`：资源所在配置目录，如 `values`、`values-zh` 等
- `new_values`：新的资源值；多个值用换行分隔
- `index`：可选，同一资源有多个子项时指定修改第几个

### 1.1 版本额外字段

```ini
[补丁名称]
ver = 1.1
file = com.example.MainActivity
method = onCreate
anchor = const-string
assist = 5
assist_content = 辅助定位值
exclude_content = 排除内容
replace_line = false
replace_target = 被替换内容
replace_all = false
match_index = 1
```

- `assist`：辅助定位搜索范围，默认 5 行
- `assist_content`：辅助定位值
- `exclude_content`：命中后排除的内容
- `replace_line`：是否替换整行
- `replace_target`：替换指定字符
- `replace_all`：是否替换所有匹配
- `match_index`：多个匹配时选择第几个

### 元信息

```ini
[元信息]
author = XKspeed
tutorial_url = https://example.com
auto_open_tutorial = ask
```

- `auto_open_tutorial`：`true` 自动打开、`false` 不打开、`ask` 询问

## 更新

脚本支持自动更新，启动时会检查 GitHub 上 `update.json` 是否有新版本，并询问是否下载更新。

## 许可证

本项目使用 GPL-3.0 许可证。
