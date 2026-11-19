> 构建、完整包安装和回滚以新版 [Actions 与前台真机验证指南](actions-build-and-device-validation.zh-CN.md) 为准。完整测试包不再捆绑接收器；下文保留触摸测试矩阵。

# iOS 16.1.1 真机测试步骤（实验版，未宣称混合输入已修复）

允许注入系统 SpringBoard；禁止向目标 App 注入。生成包只有 `pccontrol.plist → com.apple.springboard`，不包含 appdelegate.dylib。Touch Receiver 是独立的普通 UIKit 测试 App，没有 hook。仓库中保留的旧 appdelegate 源码不再参与默认构建。

## 先记录官方包基线

在电脑中进入 diagnostics 目录运行 `python3 -m http.server 8080`，iPhone Safari 打开 `http://电脑局域网IP:8080/touch-probe.html`。先关闭 ZXTouch 的 Touch Indicator；也关闭其他系统触点可视化。所有手指都放在蓝色区域内，避开屏幕边缘与系统手势。在 ZXTouch 设置中关闭触点显示。

网页只根据 `TouchEvent.touches` 绘制圆点，分别保留 `targetTouches/changedTouches` 和 Pointer Events，导出的 JSON 才是接收层证据。**ZXTouch overlay、HID 日志、TCP 发送成功均不能代替此证据。** 测试页出现两个标记但 touches=1，先看标记是否都确实在本页 canvas 内、导出 changedTouches/cancel；不要自行增加计数。

需要更接近 UIKit 的对照时，先安装单独的 `ZXTouchReceiverProbe-rootless.deb`（仅测试 App，不改 ZXTouch），或自行构建：

```
THEOS=/path/to/theos make -C diagnostics/TouchProbe package FINALPACKAGE=1
```

它在同一个 multipleTouchEnabled UIView 内记录每次 `UIEvent.allTouches`、changedTouches、UITouch.phase、接收器分配的稳定 id、时间与坐标；ended/cancelled 不计入 active。这里的 id 是本 App 给 UITouch 对象分配的编号，不是 HID index/identity，也不能直接等同于 WebKit identifier。

## 测试矩阵

| 项目 | 操作 | 必须观察到 | 官方包 | 测试包 |
| --- | --- | --- | --- | --- |
| 物理双指 | 两根真实手指按下／移动／分别抬起 | 2 个稳定 id，最后 0 | 待真机 | 待真机 |
| 虚拟点击 | `--mode tap` | begin → end，最后 0 | 待真机 | 待真机 |
| 虚拟滑动 | `--mode swipe` | 同一 id 连续移动，最后 0 | 待真机 | 待真机 |
| 虚拟双指 | `--mode two` | 2 个稳定 id，双指距离改变，最后 0 | 待真机 | 待真机 |
| 真实先按 | `--mode physical-first` | 真实先保持，虚拟加入／移动／抬起；真实仍能移动 | 用户反馈计数 1，须此工具复核 | 待真机 |
| 虚拟先按 | `--mode virtual-first` | 虚拟保持时加入真实，分别抬起／移动 | 待真机 | 待真机 |
| 真实先抬 | 手动在脚本 UP 前抬起真实手指 | 虚拟仍然存在，不能被取消或重新 begin | 待真机 | 待真机 |
| 断开 | 虚拟 down 后关闭 TCP，不发 up | 虚拟释放，物理手指不应被项目主动释放 | 原实现无连接清理 | 待真机 |
| 超时 | 虚拟 down 后保持 TCP 打开、不再发送 | 默认约 30–31 秒释放虚拟触点 | 原实现无 watchdog | 待真机 |
| 所有权 | 两 TCP 客户端同 slot，再不同 slot | 同 slot 冲突拒绝；断开 A 不释放 B | 原实现全局共享、无 owner | 待真机 |
| 异常帧 | 非数字、短帧、slot20、重复slot、move-before-down | 整帧拒绝、无半个 begin、状态不变、无崩溃 | 原实现校验不足 | 待真机 |

网页和原生接收器分别做；最终还要在普通触控测试 App 复核。混合测试两种起始顺序各重复 20 轮，导出 JSON，记录现象、App、包 SHA-256、iOS 版本、slot、indexBase 与显示开关。只有 peak=2 不足以通过，要求同时保持、两个位置可独立变化、一方抬起后另一方继续、没有非预期 cancel / 重新 begin，最后全部归零。

## Python 3.9 测试脚本

不需要 pip 或第三方库。iPhone 12 Pro 竖屏物理分辨率为 1170×2532，参数单位是**竖屏物理像素**，不是 Safari CSS px（通常存在 3 倍缩放和浏览器工具栏偏移）。先用单点确认蓝色区域的实际位置，必要时修改 x/y，避免点到工具栏、Export/Reset 或屏幕边缘。

```
python3 diagnostics/mixed_touch.py PHONE_IP --mode physical-first --slot 7 --x 800 --y 1200 --output physical-first-sent.json
python3 diagnostics/mixed_touch.py PHONE_IP --mode virtual-first --slot 7 --x 800 --y 1200 --output virtual-first-sent.json
python3 diagnostics/mixed_touch.py PHONE_IP --mode two --slot 7 --second-slot 9 --x 400 --y 1400 --spacing 400 --distance 80
```

默认倒数 5 秒、保持 6 秒，finally 尝试发 UP。保持期间每 0.1 秒发 MOVE，因此不会被 watchdog 当作断流。脚本发送日志不作为接收确认。若断网使 UP 发送失败，新版服务器还有连接断开／超时清理；原版没有该保障。不要同时让两个脚本使用同一 slot。

新版 Python 客户端保持 touch/touch_with_list 接口与原任务10格式，改为 sendall；支持小数坐标并校验 slot、帧数和坐标。新增两个**仅实验版支持**的诊断命令：

- TCP `31\r\n`：释放当前 TCP 会话自己的所有虚拟触点，返回 `0\r\n`，不释放其他客户端或主动释放物理触点。
- TCP `32\r\n`：返回 `0;;JSON\r\n`，包含 senderReady / activeVirtual / submittedFrames / rejectedFrames / releaseFrames / timeoutMs / indexBase，`appReceiptVerified` 始终为 false。

任务10沿用不回 ACK 的协议。需要确认本连接先前命令已处理时，在同一连接发送32并读到回复后再关闭；服务器关闭会话后拒绝仍未执行的触摸任务，以免延迟任务重新按下。旧客户端与旧包不要调用31/32，否则可能等不到回复。

## 安装实验版与恢复

先保存原 `.deb` 和配置，完成官方包基线。测试包沿用 `com.zjx.ioscontrol`，版本为 `1.0.1~touchtest.<build>`，在 Debian 版本顺序中低于稳定1.0.1，方便明确区分。先核验 SHA256SUMS 与 package-audit.json，再通过 Sileo/Filza 或 SSH 安装 `.deb`。安装后由用户正常 respring；包的安装脚本不在 dpkg 事务中强杀 SpringBoard。

旧版本曾加载的 appdelegate 代码不会因为磁盘文件被替换而从现存进程中消失，需 respring 并重新启动测试 App（必要时重启设备／重新启用越狱）；不能在旧注入残留的会话里宣称已满足无 App 注入条件。包审计只能证明包内容，不保证设备上其他 tweak 的行为。无 appdelegate 后，原版第三方 App 文本输入／键盘 hook 功能不再提供；触摸点击、滑动和纯模拟多指入口保留。

本地构建可使用仓库随附的管理 App 二进制（build-info 会标注）；Actions 流程则重新使用 Xcode 编译管理 App。新增 UIKit 接收器、pccontrol、zxtouchb 和 runner 都应从本次源码编译。恢复原版时按新版指南安装保存的官方包，并在 respring 前定向禁用其中的 appdelegate，以继续满足禁止 App 注入的限制；再验证单指与双指；如果有残留触点，先断开所有测试客户端并等候超时，必要时 respring。

## 开启限量日志和 index A/B

`/var/mobile/Library/ZXTouch/config/tweak/touch-diagnostics.plist` 为可选配置，缺省关闭详细日志、indexBase=0、timeoutSeconds=30。修改后需 respring，只在初始化时读取。例如：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>enabled</key><true/>
  <key>indexBase</key><integer>0</integer>
  <key>timeoutSeconds</key><integer>30</integer>
</dict></plist>
```

筛选系统日志中 `ZXTouchTouch:`（可用设备 Console／系统日志工具；若安装了 log CLI，可尝试 `log stream --level debug --predicate 'eventMessage CONTAINS "ZXTouchTouch:"'`）。每秒共限20条详细／错误消息，多余抑制，状态计数仍继续；记录 sender、HID index/identity/mask/touch/range、发送帧时间与序号，无常驻无限增长日志文件。发送时间戳回显仅用于诊断标注，不能证明事件来源／App 接收。

sender 不读旧缓存，respring 后先在屏幕上做一次真实触摸，等待32中 senderReady=true 再发测试序列；否则 down 被拒绝，不会提交半完成状态。若始终不 ready，收集 integrated、child type 与 sender 日志，不放宽为任意来源。

在两种起始顺序均有基线后，可把 indexBase 改为64做 A/B（只接受0或64）。逻辑 slot 7 此时映射为 HID index71，identity72；0模式仍用 index7、identity8。**64只是实验偏移，不能保证不与硬件冲突，也不能保证 iOS 接受高 index。** 该模式不会画出新版虚拟 index 的 ZXTouch overlay，须始终用接收器计数。若高 index 无输入，立即恢复0。原始录制器不支持高 index 回放；本次不改变录制格式，不要录制64模式的模拟事件。

## 已知边界

- 本版不把物理触点补入模拟帧，不修改系统分发函数；仍使用捕获的真实触屏 sender。若系统按同 sender 的完整帧替换活动触点，本版不能保证混合输入共存。
- 同一会话30秒没有有效触摸命令，会释放该会话的虚拟手指；长按应用需定期发送 MOVE 或将 timeoutSeconds 改为1…300秒。超时清理按会话活动计算，不会因另一会话活跃而永不释放。
- SIGKILL／SpringBoard 崩溃／重启无法执行应用层清理。watchdog运行于同一进程，也不能对该进程自身死亡提供保证；不能宣称杜绝系统崩溃或硬件触点残留。
- IOKit DispatchEvent 无投递 ACK；“提交成功”仅代表完成本地构造并调用发送 API。唯有目标 App 的 receiver 日志可以证明它实际接收了哪些触点。
- Actions 文件已配置，但当前 GitHub 集成不能创建 fork（HTTP403），因此不伪造远程工作流运行链接。在有权限的 fork 上传分支后，手动运行 **iOS 16.1.1 Rootless Touch Test**，下载 EXPERIMENTAL artifact；不会自动发布稳定 Release。
