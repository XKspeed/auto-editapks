# 更新日志

## 1.1 (2026-08-27)

### 新增功能

- **INI 版本 1.1**
  - 配置项改为编号格式：`anchor1`、`content1`、`position1`
  - 新增 `replace_all{n}`：替换所有匹配
  - 新增 `match_index{n}`：指定第 N 处匹配
  - 新增 `replace_target{n}`：替换指定字符
  - 新增 `assist{n}` / `assist_content{n}`：辅助定位约束
  - 新增 `[元信息]` section：作者、教程链接、自动打开

- **手动修改 DEX**
  - 方法选择支持 `0`：整个类中搜索
  - 多匹配时自动查找唯一辅助定位值
  - 辅助定位值搜索范围可调（默认 5 行）
  - 找不到唯一标识时：扩大范围重试 / 手动输入 / 跳过
  - 输入 `A`：替换所有匹配
  - 相对位置视图：🟡 辅助定位值 / 🟢 原 anchor
  - 单位置替换：替换指定字符 / 替换整行
  - 双位置插入：before / after / replace range
  - 修改记录包含完整字段（match_index、replace_all 等）

- **教程链接**
  - 支持网页链接、APP scheme、intent:// 链接
  - `auto_open_tutorial` 三态：true（自动打开后变 ask）、ask（询问）、false（不询问）
  - 询问时选 `n` 保持 ask 状态

- **INI 兼容性**
  - 支持加载 1.0 版本 INI（显示过时警告）
  - 无 ver 标签默认为 1.0
  - `check` 已打补丁检测

### 修复

- `rel` 变量未定义错误
- 重复 section 名称导致保存失败
- `replace_all` 流程错误（else 分支干扰）
- `replace_all` 执行后误入 position 检查
- `anchor2=const` 宽泛匹配问题（改用 `0x7f03` 前缀 + assist）
- Q 退出统一为小写 `q`

### 版本文件

- `xkspeed.py`：主程序
- `xkspeed_1.1.py`：1.1 版本备份
