# XKSpeed APK 修改工具 v1.1

---

## 安装

```bash
pkg install apktool unzip zip aapt2 python -y
```

---

## 快速开始

```bash
cd ~/apk && python xkspeed.py
```

---

## 使用流程

### 1. 反编译

将 APK 放入 `input/`，运行程序，选择 APK，选择仅 dex 模式

### 2. 修改

- 手动修改：输入类名 → 选择方法 → 输入 anchor → 选择修改方式
- INI 加载：选择 INI 文件自动应用
- 添加 dex：放入 `patch_classes/` 后选择

### 3. 回编译

输出到 `output/`，文件名：`原名_patched.apk`

---

## 手动修改详解

### 输入类名

支持简单类名、完整类名、路径格式、模糊搜索

### 选择方法

- `0` = 整个类
- 数字 = 对应方法
- 方法名 = 搜索匹配

### 输入 anchor

程序搜索所有包含 anchor 的行

### 匹配处理

- 唯一匹配：直接显示相对位置
- 多个匹配：选第 N 处 / 输入 A 全部替换
- 自动查找辅助定位值（可调范围）

### 修改位置

- 1 个编号 = 替换
- 2 个编号 = 插入（before/after/replace range）

### 替换方式

- 替换指定字符
- 替换整行

### 保存到 INI

修改后自动记录，主菜单 [5] 导出

---

## INI 配置完整参考

### 元信息 Section

```ini
[元信息]
author = 作者名
tutorial_url = intent://www.coolapk.com/feed/123#Intent;scheme=coolmarket;package=com.coolapk.market;end
auto_open_tutorial = true
```

| 字段 | 必填 | 说明 | 可选值 |
|---|---|---|---|
| author | 否 | 作者署名 | 任意文本 |
| tutorial_url | 否 | 教程链接 | 网页/APP scheme/intent:// |
| auto_open_tutorial | 否 | 自动打开 | true / ask / false |

### 补丁 Section（1.1）

```ini
[补丁名称]
ver = 1.1
type = smali
method = apply
check = const p0, 0x7f0300ce
description = 可选描述

anchor1 = FocusNotificationBlurEffect
content1 = NotificationRowBlurEffect
position1 = replace
replace_all1 = true

anchor2 = const p0, 0x7f03
content2 = const p0, 0x7f0300ce
position2 = replace
replace_line2 = true
replace_target2 = 0x7f03
assist2 = 3
assist_content2 = getResources
match_index2 = 1
exclude_content2 = debug

step1_file = com.example.ClassA
step2_file = com.example.ClassB
```

### 所有字段说明

| 字段 | 必填 | 说明 | 示例 |
|---|---|---|---|
| ver | 是 | 版本号 | 1.1 |
| type | 否 | 补丁类型 | smali |
| method | 否 | 限制方法范围 | apply |
| check | 否 | 已打补丁则跳过 | const p0, 0x7f0300ce |
| description | 否 | 补丁描述 | 修改模糊效果 |
| anchor{n} | 是 | 第 n 处定位内容 | FocusNotificationBlurEffect |
| content{n} | 是 | 第 n 处新内容 | NotificationRowBlurEffect |
| position{n} | 是 | 修改位置 | replace / before / after |
| replace_all{n} | 否 | 替换所有匹配 | true / false |
| match_index{n} | 否 | 指定第 N 处匹配 | 2 |
| replace_line{n} | 否 | 整行替换 | true / false |
| replace_target{n} | 否 | 替换指定字符 | Lcom/A; |
| assist{n} | 否 | 辅助定位范围 | 3 |
| assist_content{n} | 否 | 辅助定位值 | getResources |
| exclude_content{n} | 否 | 排除包含此内容的行 | debug |
| step{n}_file | 是 | 目标类文件 | com.example.Class |
| file | 是* | 单文件目标（无 step 时） | com.example.Class |

*file 和 step{n}_file 二选一

### 完整示例

```ini
[元信息]
author = Mari0us
tutorial_url = intent://www.coolapk.com/feed/73302580#Intent;scheme=coolmarket;package=com.coolapk.market;end
auto_open_tutorial = true

[修改apply方法]
ver = 1.1
type = smali
method = apply
check = const p0, 0x7f0300ce

anchor1 = FocusNotificationBlurEffect
content1 = NotificationRowBlurEffect
position1 = replace
replace_all1 = true

anchor2 = const p0, 0x7f03
content2 = const p0, 0x7f0300ce
position2 = replace
replace_line2 = true
assist2 = 3
assist_content2 = getResources

step1_file = com.android.systemui.statusbar.notification.style.vieweffect.FocusNotificationGlassEffect
step2_file = com.android.systemui.statusbar.notification.style.vieweffect.FocusNotificationGlassFullAodEffect
step3_file = com.android.systemui.statusbar.notification.style.vieweffect.FocusNotificationGlassOnKeyguardEffect
step4_file = com.android.systemui.statusbar.notification.style.vieweffect.FocusNotificationGlassOnKeyguardLightWallPaperEffect
```

### 1.0 兼容

支持加载 1.0 版本 INI（显示过时警告）。1.0 使用 `nearby`/`nearby_content` 代替 `assist`/`assist_content`。

---

## 目录结构

```
apk/
├── xkspeed.py
├── input/          # APK
├── output/         # 回编译输出
├── patch_ini/      # INI 补丁
├── patch_classes/  # 添加 dex
├── save/           # 工程
└── temp_build/     # 临时
```

---

## 常见问题

**定位不唯一？** 用更精确 anchor / assist_content / match_index

**回编译失败？** 完整反编译暂不可用，用仅 dex 模式

**退出？** 小写 q
