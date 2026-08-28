# XKspeed

一个在 Termux 中运行的 APK 自动化处理工具，支持反编译、smali 修改、INI 补丁应用、回编译以及多 APK 批处理。

## 功能

- 检查并安装必要依赖：apktool、unzip、zip、aapt2
- 支持从 APK 或项目目录反编译
- 手动修改 smali，提供唯一锚点定位与辅助定位
- 支持 arsc XML 文件修改
- 读取并应用 INI 补丁配置
- 添加额外 dex 文件
- 回编译生成补丁后的 APK
- 支持多 APK 批量处理
- 启动时检查 GitHub 云更新，可选择是否自动更新并重启

## 使用方法

### 环境准备

在 Termux 中安装 Python 和 Git：

```bash
pkg update -y
pkg install python git -y
```

### 下载脚本

```bash
git clone https://github.com/XKspeed/auto-editapks.git
cd auto-editapks
```

### 运行

```bash
python xkspeed.py
```

启动后按菜单提示操作。

### 目录结构

```
.
├── xkspeed.py          # 主程序
├── input/              # 放入待处理 APK
├── output/             # 输出目录
├── patch_ini/          # 存放 INI 补丁配置
├── patch_classes/      # 可选，额外 dex 或 class
└── save/               # 保存目录
```

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
| `type` | 否 | 补丁类型，默认 `smali` |
| `name` | 否 | 补丁名称，默认使用 section 名 |
| `description` | 否 | 补丁描述 |
| `file` | 是 | 目标 smali 类，如 `com.example.MainActivity` |
| `method` | 否 | 目标方法名，留空则在整个类中定位 |
| `anchor` | 是 | 定位锚点内容 |
| `content` | 是 | 要插入或替换的内容 |
| `position` | 否 | `before`、`after` 或 `replace`，默认 `before` |

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
- `replace_line`：是否替换整行，`true` 或 `false`
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

脚本启动时会从 GitHub 读取 `update.json`，如果远程版本比本地新，会询问是否更新。

`update.json` 格式：

```json
{
  "version": "1.2",
  "download_url": "https://github.com/XKspeed/auto-editapks/releases/download/v1.2/xkspeed.py",
  "description": "更新说明"
}
```

## 许可证

本项目使用 GPL-3.0 许可证。
