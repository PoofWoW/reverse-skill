# ZXTouch Rootless：iOS 16.1.1 真实／模拟触摸兼容性初步报告

报告时间：2026-11-19。**本报告先于修复代码提交。结论是源码可修改，但尚无真机证据证明能合并物理与模拟触摸。**

## 1. 范围与证据

目标设备由用户提供：iPhone 12 Pro、iOS 16.1.1、Dopamine Rootless、Python 3.9.9；TCP 6000 和纯模拟点击、滑动、双指缩放已由用户验证。用户允许注入系统进程，禁止注入单个 App；不涉及游戏反作弊。

分析基线：`Epic0001/zxtouchrootless` 的 `a602da112ef1a688fb2601424443abb1ccc28c63`（main 与 v1.0.1 tag）。本地为 Linux，没有连接目标 iPhone；以下源码／包结构结论可复核，UIKit 接收行为和系统限制仍须真机验证。

已下载并解包官方 [v1.0.1 rootless deb](https://github.com/Epic0001/zxtouchrootless/releases/download/v1.0.1/com.zjx.ioscontrol_1.0.1_rootless.deb)：

- 大小 1,033,660 字节。
- SHA-256：`6c4b53b035b3ed0a4c5c808e02d18ca12f1610241323c74c5f9365ad306095ec`。
- control：`com.zjx.ioscontrol`、1.0.1、`iphoneos-arm64`，依赖 `mobilesubstrate | ellekit, firmware (>= 15.0)`。

## 2. 安装包与源码完整性

| 包内位置（均在 /var/jb 下） | 对应源码／作用 |
| --- | --- |
| Library/MobileSubstrate/DynamicLibraries/pccontrol.dylib + plist | pccontrol/；Filter 仅 `com.apple.springboard`，实际触摸生成与 TCP 服务在这里 |
| Library/MobileSubstrate/DynamicLibraries/appdelegate.dylib + plist | appdelegate/；Filter 为 `com.apple.UIKit`，包含 UIKeyboardImpl hook；违反本次“禁止 App 注入”的范围，测试包必须排除 |
| Applications/zxtouch.app/zxtouch | zxtouch/zxtouch/；管理 UI，不是底层触摸生成器 |
| Applications/zxtouch.app/PlugIns/shortcutext.appex/shortcutext | zxtouch/shortcutext/；快捷指令扩展 |
| usr/bin/zxtouchb | zxtouch-binary/main.mm；命令／socket 客户端，不是独立触摸驱动 |
| usr/libexec/zxtouch-runner | zxtouch-runner/main.m；launchd 脚本执行助手，不负责 HID 触摸 |
| usr/share/zxtouch/python/zxtouch | Python 客户端源码；兼容性排查应保持 3.9 可用 |

上述六个 Mach-O 均为 arm64 / arm64e fat binary。解包 pccontrol.dylib 的 arm64 load commands 和 symbol table，可见 `_IOHIDEventCreateDigitizerEvent`、`_IOHIDEventCreateDigitizerFingerEvent`、`_IOHIDEventSystemClientDispatchEvent`、`__Z23performTouchFromRawDataPh` 和 `_MSHookMessageEx`，依赖包括系统 IOKit 与 CydiaSubstrate。

**项目自己的事件构造、发送、sender 捕获、socket 和显示代码有源码，未发现该触摸路径依赖独立闭源 ZXTouch 生成器。** 这不等于整个栈开源：Apple IOKit 的 iOS 用户态实现、backboardd 路由／UIKit 触点归并策略不在仓库中。没有复现构建前也不能声称官方二进制与源码逐字节一致。

原包 postinst 注册 UI、配置 Python、签名 App、创建 runner launchd plist；不会建立独立触摸服务。仅关闭 App 的触点显示不能停止 SpringBoard 的模拟触摸逻辑。卸载／替换包后需由用户安排 respring，已加载的旧 dylib 才会退出。

## 3. 系统分发与生命周期

源码路径：

`Python touch/touch_with_list → TCP 6000 CRLF 行 → SocketServer.xm 各客户端 serial queue → Task.xm TASK_PERFORM_TOUCH(10) → Touch.xm → IOHIDEventSystemClientDispatchEvent → 系统私有 HID／backboardd 分发 → 目标 UIKit / WebKit 应用`

关键位置（基线行号）：

- `pccontrol/Tweak.xm:373–407` hook `SBHomeScreenViewController viewDidLoad`，设置物理像素尺寸、启动 sender 监听与 socket。
- `pccontrol/Touch.xm:90–126` 构造 FingerEvent。index 来自协议，**identity 对所有手指固定为 3**；down mask=3，move=4，up=2。
- `Touch.xm:154–215` parent index=99、identity=1，维护 `eventsToAppend[20][4]`，补发未变化的模拟手指。未变化手指若上次是 down，会再次携带 down mask；坐标被截为整数。
- `Touch.xm:210–212` 每帧无条件设置 parent mask=0x23、range=1、touch=1，包括最后一指抬起帧。
- `Touch.xm:221–234` 用物理触屏 sender ID 发送**仅含模拟手指的独立帧**。sender 为 0 时静默丢弃，调用方状态却已前进。
- `Touch.xm:240–321` 抓取第一个 digitizer 的 sender，按重启时间缓存到 plist；缺少 display-integrated／finger／非零 sender 过滤；捕获后异步线程使用另一个 run loop 做 unschedule，生命周期不正确。
- `SocketServer.xm:129–171` 不同客户端队列可同时访问同一份静态模拟触点表，没有全局串行化、触点所有者或断开释放机制。

触点状态表下标来自外部数据，没有完整长度、数字、范围与状态迁移校验：无效 index 可越界；重复 down、无 down 的 move/up、同帧重复 index 未定义。子事件 Create 后 Append 未 release，有泄漏。以上都是可独立修正的问题，但并不能单独证明混合输入的根因。

## 4. “两个标记，只有一个触点”的可能原因

| 假设 | 现有证据 | 必要验证 |
| --- | --- | --- |
| 第二个标记只是 ZXTouch overlay | TouchIndicatorWindow.xm:489 起直接订阅系统 HID 并画 SpringBoard 窗口，不依赖目标 App 收到 UITouch | 关闭 ZXTouch 触点显示，测试页仅根据 TouchEvent.touches 绘图并导出事件日志 |
| index / identity 与物理触点冲突 | 复用同一 sender；模拟 index 可与物理 index 相同；identity 固定 3 | 保持坐标相同，分别测模拟 slot 1/7/19；记录 HID 元数据；可选对模拟 HID index 做小范围偏移实验 |
| 同 sender 独立帧被当成设备完整触点快照，互相替换 | 程序只补齐模拟触点；完全不知道物理触点状态 | 对照 physical→virtual 与 virtual→physical；看是否收到 cancel/end/restart；原生 allTouches 与网页同时验证 |
| 错误的 down／up／parent mask 干扰触点追踪 | 未变化手指重复 down，最后 up 时 parent touch 仍为 1 | 修正为 stationary mask=0、parent 从本帧 children 聚合；回归纯模拟双指 |
| 目标应用/WebKit/手势控制本身限制 | 未知测试网页实现；仅看到一个计数 | 基于 Touch Events 而非只看 pointer/isPrimary、原生 UIView multipleTouchEnabled=YES 对照 |
| iOS 私有路由只接受某种设备／流 | Apple 路由实现不在源码中；更换任意 sender 可能直接丢弃事件 | 仅在前述对照完成后判断；不可把随机 sender、加权限或换 ID 当成已证实的修复 |

纯模拟双指成功说明“ZXTouch 只能生成单指”不成立；也说明 identity 固定 3 不一定是唯一根因。**当前不能断言 iOS 16.1.1 绝对不支持共存，也不能断言修改 identity 就能合并。**

本次不 hook 单个 App、不 hook backboardd 事件分发、不拦截／丢弃／重放物理事件。HID observer 看到两个 child 也不是目标应用收到两个有效触点的证据。若必须拦截完整物理帧才能可靠归并，超出这次最小修复，应明确记录限制，不在观察回调中盲目重放物理触摸（会造成双发、延迟与反馈环）。

## 5. 先做最小接收测试

第一阶段在**未修改的官方包**上建立基线：

1. 关闭 ZXTouch touch indicator 和系统触点辅助显示，在 Safari 打开同一个无滚动测试区域。页面用 `touch-action:none`、非 passive Touch Events；记录每个事件的 `touches`、`targetTouches`、`changedTouches`、identifier、坐标、时间与 cancel；只按 `event.touches` 重画。Pointer Events 单独记录，不能把其 ID 与 Touch.identifier 合并计数。
2. 两根真实手指、两根模拟手指各自必须稳定达到 2。若真实双指也只有 1，先处理页面／系统手势问题。
3. 真实手指先按住左侧，再让脚本 down/move/up 右侧；交换起始顺序；分别抬起任一方并确认另一方仍可移动；最后计数归零。左右位置应固定，不能只看峰值 2。
4. 用 native 测试 App 的公开 `touchesBegan/Moved/Ended/Cancelled:withEvent:` 和 `UIEvent.allTouches` 复核；多个手指落在同一个 `multipleTouchEnabled=YES` 的 UIView。只计 began/moved/stationary；ended/cancelled 单独保留。不注入任何第三方 App。
5. 验收要求：两个不同 identifier 同时保持、可独立移动／抬起、无非预期 cancel/re-began、全部抬起归零，两个顺序重复至少 20 轮；普通触控测试应用结果也须通过。网页只能证明 WebKit DOM 层，不能替代 native 或普通应用验收。

计划提供可导出 JSON 的网页、Python 3.9 标准库脚本（finally 发 up）、原生接收器源码及明确测试矩阵。当前无真机，所有设备结果留空，不编造 PASS。

## 6. 最小修改计划（报告提交后执行）

- 保留 TCP 任务 10、13 字节手指格式、0…19 逻辑 slot 与原有点击／滑动／纯模拟多指入口。
- 把解析和触点迁移提成可在 Linux/macOS 测试的纯 C 模块：整帧校验后提交；保留 0.1 像素；稳定且不同的模拟 identity；严格 begin/move/end；未变化触点 mask=0；最后 up 后 parent touch/range=0；释放 CF 子事件。
- 所有模拟状态与发送在同一队列串行；为每个 TCP 连接管理 owner；断开只释放该 owner；可配置超时释放与显式 release-all。sender 未就绪／创建失败时不先提交状态。
- 修正 sender client 注册／注销 run loop，验证 display-integrated hand/finger、非零 sender；提供有限、可关闭的 HID 与 TX 日志，标注它不是接收确认。
- 可选 HID index 偏移仅作为诊断 A/B，默认保留原逻辑 index；不宣称偏移能解决系统快照替换。
- Rootless 测试构建仅注入 SpringBoard，排除 `appdelegate` 和任何面向普通应用的 filter；不改动正式版的 App 注入组件源码。包内检查必须拒绝其他 tweak filter。
- 添加独立 Actions 测试包流程，目标最低 iOS 15（覆盖 16.1.1）、arm64/arm64e、iphoneos-arm64、Rootless；标明 experimental / NOT DEVICE VALIDATED，上传 deb、测试工具和构建／审计信息，不自动发布为稳定 Release。

保留原版显示／管理功能；测试包因为排除 appdelegate，第三方 App 文本注入与键盘 hook 不可用。该限制与触摸点击、滑动、多指生成无关，应明确写入使用说明。

## 7. 判定边界

代码级缺陷可以修正并跑自动化测试；目标设备上触摸合并是否成立，必须依赖阶段 5 的接收端证据。如果唯一 sender 下仍互相替换，不能靠补齐模拟表宣称完成合并。届时交付应标为“生命周期／标识修正与诊断测试包，混合输入仍未解决”，并记录 Apple 私有分发边界。当前没有可从本环境代替的硬件验证。

后续代码修改、实测范围和构建阻塞见 [实现与验证结果](touch-implementation-results.zh-CN.md)。
