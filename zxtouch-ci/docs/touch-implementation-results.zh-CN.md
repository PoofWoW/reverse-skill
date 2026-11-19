> 本文件记录上一阶段的18项测试与接收器构建结果。本阶段的构建准备、完整包门禁和真机流程见 [新指南](actions-build-and-device-validation.zh-CN.md)；真机结果仍为 NOT RUN。

# 本次实现与验证结果

状态：**已完成源码修正和接收端工具；未证明真实与模拟触点共存，尚未完成最终真机目标。** 初步报告先在提交 `5e33162` 中交付；随后才修改代码。

## 已完成

- `TouchState.c/.h`：事务式整帧解析，0…19 逻辑 slot，0.1 像素坐标；不同且稳定的模拟 identity；begin/move/end 迁移；未变化触点 mask=0；UP 保留本次结束触点，下一帧移除。
- `Touch.xm`：触点、sender 与 IOKit 发送在统一 serial queue；parent 按真实本帧的模拟活动状态设置 touch/range，begin/end 附加 identity mask；子事件 CFRelease；创建失败不先提交状态。
- TCP 会话使用不重复 owner token，断开释放对应模拟触点，关闭后延迟触摸命令不能重新激活；默认30秒的会话触摸不活动 watchdog。任务31释放本连接，任务32导出提交／拒绝／清理计数，明确不是 App ACK。
- sender 从真实 display-integrated finger 事件现场捕获，拒绝旧缓存与0；在同一 main run loop 注册／注销观察器；默认捕获后注销，详细日志开启时保留；每秒限20条日志。
- 保持 task10 和 touch / touch_with_list 接口；Python sendall、长度和数字范围校验、小数双指坐标；`mixed_touch.py` 不依赖第三方库，兼容Python3.9语法，finally 尝试 UP。
- 增加可导出 JSON 的 DOM Touch Events 接收器、原生 UIKit allTouches 接收器和完整真机矩阵；不同接收层的 id 不混用。
- 默认构建排除 appdelegate，测试构建也只有 SpringBoard filter；overlay 修复 slot0 负下标，数组更新置于 main queue。
- 单独的 macOS Actions 测试工作流；固定 Theos commit 与 SDK SHA-256，构建管理 App、tweak 与接收器，上传实验包；包审计拒绝非 SpringBoard filter、额外 dylib、旧 arm64e ABI、rootless 前缀外文件与不安全目录权限。

## 补充发现：SPI 声明

仓库旧头文件 `IOHIDEventAppendEvent` 只声明两个参数，而 [WebKit iOS SPI 声明](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/PAL/pal/spi/ios/IOKitSPIIOS.h) 和 [HIDEventGenerator](https://github.com/WebKit/WebKit/blob/main/Tools/WebKitTestRunner/ios/HIDEventGenerator.mm) 均使用三个参数 `(parent, child, options)`。已补上明确的 options=0。旧头的 transducer type 是 desktop 0x20 开头的值，已改为 iOS stylus=0 / finger=2 / hand=3。这些是 ABI 声明修正，仍不能证明解决了同 sender 下的物理／虚拟归并问题。

## 实际完成的验证

| 检查 | 实际结果与边界 |
| --- | --- |
| Python 3.12.14 | 18 项测试通过；生产 C 状态模块以 AddressSanitizer + UndefinedBehaviorSanitizer 运行 |
| Python 3.9.25 | 同18项测试通过；不是用户设备的3.9.9实测 |
| C 状态测试 | begin/move/up、stationary、slot0/19、最后一指释放、无效帧原子拒绝、owner 隔离、超时／断开清理状态、20,000次随机迁移 |
| Web 接收器测试 | Node 合成 DOM 环境确认 Touch 计数不会累加 Pointer id，日志与cancel归零；不代表 WebKit 真机输入测试 |
| 包门禁测试 | 禁止 UIKit/App filter、额外 appdelegate dylib、旧 arm64e ABI、umask077目录权限；均有拒绝用例 |
| Actions 静态检查 | actionlint 1.7.12 通过；不代表远程 Actions 已执行 |
| Objective-C/C++ 编译 | 修改后的源码与原生接收器已用 Theos/iPhoneOS16.5 SDK 在 Linux 交叉编译；无目标设备运行验证 |
| UIKit 接收器 deb | arm64 普通应用；最低iOS15.0、SDK16.5、/var/jb 前缀，目录0755、文件0644、可执行文件0755、root/wheel；只有普通 App payload，没有 tweak／注入 filter |
| 完整 ZXTouch 测试 deb | **没有交付**。Linux工具链产生旧arm64e subtype=0x2，目标SpringBoard需要当前ABI；不能用已编译这一事实把不合格包当成可安装修复版 |
| GitHub Actions 运行 | **未执行**。连接对 Epic0001/zxtouchrootless 为 push=false，fork API 返回403；未写入远程仓库，未创建虚假run链接 |
| iPhone 12 Pro / iOS16.1.1 | 无设备连接，所有混合触摸验收均待用户真机执行 |

## 已提供的安装包

`ZXTouchReceiverProbe-rootless.deb` 是**接收器基线测试 App**，不会替换官方 ZXTouch，不能当作 ZXTouch 修复包。

- Package：com.zjx.zxtouch.receiver-probe，Version：0.1，Architecture：iphoneos-arm64。
- 本地生成的普通 arm64 应用，无系统／App 注入，不涉及 arm64e tweak ABI。
- SHA-256：`b4b73e9483c751c4176e081889b22116c20b67232fa363cd1fe82a7b5298e94b`。
- 已检查 payload 和伪签名；iPhone 安装／运行与触摸行为仍未实测。

完整 ZXTouch 测试包应在有写权限的 fork 中运行 `.github/workflows/touch-diagnostics.yml` 生成，并通过 package-audit.json 后再上机。不得修改二进制 ABI 标记强行通过审计。本地工具链的失败日志保留在交付附件中供复核。

## 尚未解决的核心问题

目前仍复用物理 sender，并发送只有模拟触点的独立帧。没有维护／拦截／重放物理帧，也未 hook backboardd 或任一目标 App。indexBase=64 只是可选 A/B 实验，默认0；不能保证高 index 被iOS接受，也不是可靠的设备命名空间。

因此，生命周期与身份修正之后仍有可能出现物理帧和模拟帧互相替换、取消或重新开始。需要先用官方包和接收器建立基线，再在 macOS Actions 生成的实验包上比较：两种起始顺序、各20轮、稳定并存、独立移动／释放、最后归零。如果没有这些接收端证据，本次交付只能称为“生命周期修正与诊断工具”，不能称为“混合触摸兼容性已修复”。
