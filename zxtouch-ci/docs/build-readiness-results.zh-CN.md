# 构建准备复核结果（2026-11-19）

本阶段只处理完整 ZXTouch 测试包构建、安装兼容性与前台验收准备，未新增触摸合并策略。当前状态：**macOS Actions 未实际执行，目标 iPhone 未连接，前台接收与混合触摸均为 NOT RUN。没有新的完整 .deb 被当作最终修复版交付。**

## 修正的构建阻塞

- 将已退役的 macos-14 切换为 macos-15，并显式选择 Xcode16.4。依据：[runner退役公告](https://github.com/actions/runner-images/issues/13518)、[macOS15镜像软件清单](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-Readme.md)。若该 Xcode 路径以后从镜像移除，流程会失败，不能悄悄回退到 Linux 编译器。
- 使用 Apple Clang 先编译 arm64e object，检查实际 subtype=0x80000002；Theos 固定提交在非macOS上会选择 libroot_oldabi，已确认不能靠升级普通 Linux clang 绕过。
- 移除全局 PRODUCT_BUNDLE_IDENTIFIER 覆盖，分别修正管理App与shortcutext的目标标识，与各自签名entitlements一致。旧官方包实物也存在二者ID相同的问题，当前包门禁将拒绝它。
- 完整包只包含主项目，不再打包 ZXTouchProbe.app，避免与独立接收器包发生文件所有权冲突。仍提供网页与发送脚本；原生接收器源码保持独立构建。
- 原来的稳定发布入口改为手动调用同一实验构建，不在此分支按tag自动发布未经真机验证的Release。

## 完整包门禁

流程从源码重建管理App、扩展、pccontrol、zxtouchb和runner；必须五个Mach-O与Python模块齐全。逐个检查fat与内部slice的一致性、切片边界、iOS device平台、最低系统版本≤16.1.1、现代arm64e ABI、系统／Rootless动态依赖、rpath和CodeDirectory结构。签名结构检查不等于密码学验证、Dopamine信任验证或功能验证。

包身份保持com.zjx.ioscontrol，架构iphoneos-arm64，版本~touchtest，前缀/var/jb，仅SpringBoard filter。源提交号编入发送器，task32返回buildCommit用于排除旧dylib残留，仍明确appReceiptVerified=false。

复核官方包时发现Theos归档可同时含root/wheel名称与构建用户数值UID/GID。新流程在审计前仅规范化归档所有权为数值0/0，保持所有Mach-O文件字节不变；随后检查权限和实际UID/GID。此操作不改写ABI标记。

安装脚本不再重写设备全局Python3软链接；仍会更新ZXTouch数据中的示例／registry及Python模块，指南要求先备份，回滚时恢复。官方稳定包回滚也必须在respring前定向禁用其appdelegate，继续满足不向普通App注入的要求。

## 本地完成的检查

- Python3.12.14：46项通过，生产C模块使用ASan+UBSan；Python3.9.25：同46项通过。这不是用户Python3.9.9与iPhone的运行结果。
- actionlint1.7.12检查两个工作流通过；安装shell脚本语法检查通过。
- 新buildCommit字符串宏已用现有工具链完成arm64编译／链接；该检查不是现代arm64e候选包验证。
- Mach-O解析器已在实际官方包五个二进制上验证结构读取；仅在内存规范化官方归档后核验数值所有权，没有修改或分发官方包。
- 对Linux环境运行Apple工具链预检，按预期拒绝；不提供绕过开关，不把旧ABI产物标记为可安装测试包。

## 下一步与验收

使用 [自己的仓库构建与真机验证指南](actions-build-and-device-validation.zh-CN.md)，运行iOS 16.1.1 Rootless Touch Test。成功后主artifact为 `ZXTouch-ios16.1.1-rootless-full-UNVALIDATED`，内部应有完整ZXTouch测试.deb、源码提交号、工具链信息、package-audit.json、SHA256SUMS与日志。它是实验候选，不是最终修复版。

真机阶段必须让测试App保持前台，从电脑发送；导出WebKit与UIKit的接收日志，验证不同稳定ID、独立移动／释放、无非预期cancel或重新begin、最终归零，两种起始顺序各20轮。SpringBoard TX计数、task32、HID回显、单个峰值2均不代替前台证据。

| 阶段 | 当前结果 |
| --- | --- |
| 本地源码／状态机／包检查测试 | PASS，限上述环境与检查范围 |
| 用户仓库macOS完整包构建 | NOT RUN |
| iPhone安装与Dopamine加载 | NOT RUN |
| 前台App收到模拟事件 | NOT RUN |
| 真实与模拟触点独立共存 | NOT RUN |
