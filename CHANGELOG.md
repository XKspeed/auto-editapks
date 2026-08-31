# 更新日志

## v1.3（2026-08-31）

### 新增功能

- 新增全局日志系统
  - 新增 LOG_DIR、LOG_FILE 常量
  - 新增 LogRedirector 类，自动拦截 stdout/stderr 并写入日志
  - 新增后台日志线程、debug_log、debug_debug_log、log_init
  - 日志自动轮转，最多保留 3 个历史日志
- 新增 ARSC 同资源去重
  - 新增 _append_arsc_record 函数
  - 按 file + origin + res_name 识别同一资源
  - 同一资源多次修改只保留最后一次
- 新增反编译完成后的原始 APK 副本
  - 反编译完成后、进入主菜单前，复制 original.apk 到工程目录
  - find_apk_in_project 优先返回 original.apk
- 新增快速反编译后现场解码 ARSC
  - _arsc_ensure_decoded 在缺少 arsc_res_dir 时自动现场解码
  - 解码成功后自动重新生成 config.json

### 功能改进

- 依赖检查调整
  - 移除 aapt2 强制依赖
  - 新增 APKEditor 独立检测
- 更新检查支持按 Enter 跳过
- print_progress 进度条显示改进
  - 进度条长度从 20 调整为 30
  - 改为两行显示，不写入日志
- read_project_config 增强
  - 返回 info.is_from_project 字段
  - 加载工程时读取并同步该状态
- _arsc_get_dir 兼容相对路径
  - 非绝对路径自动按 work_subdir 拼接

### 问题修复

- 修复保存工程后 config.json 的 apk.name 字段规范化问题
- 修复保存工程后 decompiled_dirs 和 simple_dirs 同步问题
- 修复 ARSC 同资源多次修改导致 INI section 重名问题
- 修复快速反编译后进入手动 ARSC 报错问题
- 修复反编译时复制 original.apk 被 apktool 清空问题

### 版本变化

- VERSION 从 1.2 升级为 1.3
- 代码行数从约 3307 行增加到约 3789 行
