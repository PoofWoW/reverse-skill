# 用自己的 GitHub 仓库构建完整测试包，并完成前台触摸验证

目标：iPhone 12 Pro、iOS 16.1.1、Dopamine Rootless、Python 3.9.9。允许 SpringBoard 系统进程注入，不向目标 App 注入。

**当前设备结果：NOT RUN。没有连接真机，本文件不声称混合触摸已修复。** Actions 生成的是完整 ZXTouch 实验候选包，构建和包审计通过后才能开始设备测试；不能把候选包称为最终修复版。

## 1. 准备自己的仓库

不需要给本会话 GitHub 写入权限，也不需要向原作者仓库推送。以下操作由您使用自己的 GitHub 账号完成。公开仓库通常可使用 GitHub 托管 macOS runner；私有仓库先检查 Actions 额度和组织策略。

### 方式 A：上传修改后的完整源码（推荐）

1. 下载本次 `ZXTouch-ios16-build-ready-source.zip` 并解压。不要把 zip 文件本身作为仓库源码上传。
2. 在 GitHub 点击 **New repository**，创建您自己的空仓库，例如 `zxtouch-ios16-test`；先不要添加 README 或许可证，以免与源码初始化冲突。
3. 在解压目录打开终端，确认有 `Makefile`、`control`、`pccontrol/TouchState.c` 和 `.github/workflows/touch-diagnostics.yml`。macOS Finder 默认隐藏 `.github`，不要漏传它。
4. 将下面 URL 中的 `YOUR_ACCOUNT` 换成您自己的账号，然后运行：

```sh
cd /path/to/unpacked-source
git init
git switch -c main
git add .
git commit -m "Import ZXTouch iOS 16 experimental build source"
git remote add origin https://github.com/YOUR_ACCOUNT/zxtouch-ios16-test.git
git push -u origin main
```

GitHub HTTPS 登录请使用您自己的正常认证方式；不要把 token 写进仓库或发给本会话。若不使用终端，也可通过 GitHub **Add file → Upload files** 上传解压后的目录内容；另外确认 `.github/workflows/touch-diagnostics.yml` 实际存在。网页上传遗漏隐藏目录时，用 **Create new file** 创建该完整路径并复制源码中的工作流内容。

### 方式 B：已有自己的 fork，应用本次补丁

先在 GitHub 页面用自己的账号 fork 原仓库，然后在电脑克隆自己的 fork。使用本次提供的 build-ready 补丁，而不是上一阶段旧源码补丁：

```sh
git clone https://github.com/YOUR_ACCOUNT/zxtouchrootless.git
cd zxtouchrootless
git switch -c fix/ios16-mixed-touch a602da112ef1a688fb2601424443abb1ccc28c63
git am /path/to/ZXTouch-ios16-build-ready.patch
git push -u origin fix/ios16-mixed-touch
```

若您的工作区已有未提交修改，先保存它们；不要用 reset 或强推覆盖已有工作。补丁冲突时用 `git am --abort` 回到应用前状态，再改用方式 A。首次在 fork 启用 Actions 时，GitHub 可能显示 **I understand my workflows, go ahead and enable them**。

手动 **Run workflow** 按钮通常要求工作流文件先存在于默认分支。方式 B 的分支 push 会触发本工作流；如需手动运行，可先将该分支设为自己的仓库默认分支，或通过自己仓库内的 PR 合入默认分支。不要向原作者提交或合并这些构建准备操作。

## 2. 运行正确的 macOS Actions

1. 打开您自己的仓库 → **Actions** → **iOS 16.1.1 Rootless Touch Test**。
2. 如使用网页手动运行，点击 **Run workflow**，选包含本次修改的分支，再运行。
3. 使用工作流指定的 **macos-15 / Xcode 16.4**；不要切换到旧 Linux arm64e 工具链，也不要通过改 Mach-O 标记绕过 ABI 检查。
4. 等待 Python 测试和完整包构建／审计任务完成。失败时下载构建日志，定位第一个 error；不要取失败任务中残留的半成品上机。
5. 下载名称明确包含 **full** 的完整 ZXTouch 实验 artifact，解压后确认主文件为：

```
ZXTouch-ios16.1.1-rootless-touch-test.deb
```

这个 `.deb` 必须包含本次编译的 `pccontrol.dylib`、管理 App、`zxtouchb`、runner 和 Python 模块。可选的接收器 artifact 是单独工具，不是 ZXTouch 修复包。两个包不应共同拥有同一个 App 路径。

完整包不包含原生接收器；上一阶段的独立接收器包可继续用于验证，或在 macOS 使用 `THEOS=/path/to/theos make -C diagnostics/TouchProbe package FINALPACKAGE=1` 单独构建。

本次具体修订和本地检查范围见 [构建复核结果](build-readiness-results.zh-CN.md)。

同时保存 artifact 内的源码提交号、工具版本、package audit、SHA256SUMS 和构建日志。核对提交号对应本次源码，而不是原作者稳定版。旧的默认发布流程已改为手动调用实验构建的入口；本次直接使用 **iOS 16.1.1 Rootless Touch Test** 即可。无需创建 Release、无需推送任何 tag，也不要选用旧提交中的发布流程。

本次工作流的目标是 iOS device arm64/当前 arm64e ABI，最低部署版本不高于16.1.1；包架构为 `iphoneos-arm64`，安装前缀为 `/var/jb`。SDK 版本高于设备系统版本本身不等于不兼容，须同时检查部署版本、使用的 API、依赖和设备运行结果。

## 3. 上机前核对依赖、冲突和回滚材料

先保证能通过 SSH 访问手机，再进行 SpringBoard tweak 测试；保持一条已登录的 SSH 会话。以下手机命令在具有相应权限的 root shell 中执行。不要把设备密码写进脚本。

```sh
export PATH=/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin:/usr/sbin:/sbin
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' com.zjx.ioscontrol
dpkg --print-architecture
dpkg -S /var/jb/Library/MobileSubstrate/DynamicLibraries/pccontrol.dylib
dpkg -S /var/jb/Applications/zxtouch.app/zxtouch
```

- 在手机设置中再次确认机型和 iOS 16.1.1，在 Dopamine 中确认当前使用 Rootless。这个包不用于 Roothide 或 rootful 环境。
- 从 Sileo 检查 ElleKit 和包 control 声明的依赖已安装；本次使用设备现有 Python3.9.9，不应替换全局 Python 可执行文件或软链接。
- `dpkg -S` 的所有者应与计划替换的 `com.zjx.ioscontrol` 一致。若文件属于其他 fork／不同包名，先查明包冲突；不要用 `--force-overwrite`、`--force-depends` 强装。
- TCP6000 只能有预期的服务监听。若设备已装 lsof，可用 `lsof -nP -iTCP:6000 -sTCP:LISTEN` 查看进程；本实现通常由 SpringBoard 提供服务。若是其他 daemon／其他自动化工具占用，先查清来源。
- 新 Makefile 已将 `ZXTouchProbe.app` 从完整测试包移出；单独的接收器包可以保留，两者没有接收器路径所有权冲突。若拿到旧阶段捆绑接收器的完整包，停止安装，重新运行本次工作流。
- 保存当前稳定版 `.deb` 到手机和电脑。仅有已安装文件而没有可重装的原包，不足以准备回滚。

在手机建立独立备份目录，保存 ZXTouch 用户数据和每个 Python 环境中的 zxtouch 模块：

```sh
BACKUP="/var/mobile/ZXTouch-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/python"
printf '%s\n' "$BACKUP" > /var/mobile/ZXTouch-last-backup-path.txt
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' com.zjx.ioscontrol > "$BACKUP/package.txt"
if [ -d /var/mobile/Library/ZXTouch ]; then
    tar -cpf "$BACKUP/mobile-ZXTouch.tar" -C /var/mobile/Library ZXTouch
fi
for SP in /var/jb/usr/lib/python3*/site-packages /var/jb/usr/lib/python3*/dist-packages; do
    [ -d "$SP" ] || continue
    NAME=$(printf '%s' "$SP" | tr / _)
    printf '%s\n' "$SP" > "$BACKUP/python/$NAME.path"
    if [ -d "$SP/zxtouch" ]; then
        tar -cpf "$BACKUP/python/$NAME.tar" -C "$SP" zxtouch
    else
        : > "$BACKUP/python/$NAME.absent"
    fi
done
ls -l /var/jb/usr/bin/python3 /var/jb/bin/python3 > "$BACKUP/python-links.txt" 2>&1
printf 'Backup: %s\n' "$BACKUP"
```

将备份目录和稳定版 `.deb` 再复制一份到电脑。若要测试官方发送器基线，完成备份后只参照第6节的 `APP_HOOK` 定向备份／禁用段处理 appdelegate，然后正常 respring／重启目标 App；这一步不重装包、不还原数据，保留原触摸发送器以建立 system-only 基线。备份用户数据是必要的：安装脚本会更新示例、registry 和 Python 模块；仅重装旧 `.deb` 不能自动撤销这些目录中的全部变化。

## 4. 安装完整实验包

先在电脑验证 artifact 校验和，保留完整构建记录。把完整 `.deb` 和已保存的稳定版 `.deb` 复制到手机 `/var/mobile/`。确认手机上的文件与校验和一致后安装：

```sh
shasum -a 256 /var/mobile/ZXTouch-ios16.1.1-rootless-touch-test.deb
dpkg-deb -I /var/mobile/ZXTouch-ios16.1.1-rootless-touch-test.deb
dpkg -i /var/mobile/ZXTouch-ios16.1.1-rootless-touch-test.deb
```

如果设备没有 shasum，使用现有的 `sha256sum`；不要跳过校验。依赖未满足时先处理原因，不要强制继续。安装完成后检查 `dpkg-query` 显示 `~touchtest` 版本，通过 Sileo 正常执行 **Restart SpringBoard／Respring**；不要在 dpkg 事务中杀 SpringBoard。

测试版本 `1.0.1~touchtest...` 在 Debian 版本顺序中低于稳定1.0.1。为防止测试期间自动升级回稳定包，可在 Sileo 对该包设置忽略更新，或在已安装 apt-mark 的设备上执行：

```sh
apt-mark hold com.zjx.ioscontrol
```

记下这个操作，回滚时按第6节处理hold和后续更新。重启测试 App，确保原版 appdelegate 的旧代码不再残留于现有 App 进程；必要时按 Dopamine 正常流程重启设备、重新启用越狱。不要在残留注入会话中验证“无目标 App 注入”。

## 5. 验证前台 App 接收，而不是只看 SpringBoard

先关闭 ZXTouch Touch Indicator 和其他触点显示。完成配置后退出 ZXTouch 管理界面，让 Safari 测试页或普通 UIKit Touch Receiver **保持前台**。从电脑向手机TCP6000运行脚本，避免在手机上切回脚本界面改变前台应用。

1. 用真实手指触摸一次，让 senderReady 变为 true。
2. 使用新版 task32读取状态，核对 `buildCommit` 与 artifact 源码提交相符。它仅证明当前 SpringBoard 加载了对应发送器，**不证明事件进入前台 App**；task32中的发送／拒绝计数也不是接收 ACK。
3. 先测真实双指，再测虚拟点击、滑动和纯虚拟双指。两种纯输入各自成功后，才做混合输入。
4. 电脑启动网页：`python3 -m http.server 8080 --directory diagnostics`；手机 Safari 打开 `http://电脑局域网IP:8080/touch-probe.html`。所有手指都放在蓝色区域，避开工具栏、屏幕边缘和系统手势。
5. 另外打开独立 UIKit 接收器复核。原生导出 `UIEvent.allTouches`／phase，网页导出 Touch Events identifier／touches／changedTouches／cancel，分别留存；不要混合两个层的 id。

在电脑可直接查询 task32，无需先安装 Python 客户端（将命令中的 PHONE_IP 换成设备地址）：

```sh
python3 - PHONE_IP <<'PY'
import json, socket, sys
with socket.create_connection((sys.argv[1], 6000), timeout=5) as s:
    s.settimeout(5)
    s.sendall(b"32\r\n")
    result = bytearray()
    while not result.endswith(b"\r\n"):
        part = s.recv(4096)
        if not part:
            raise RuntimeError("connection closed before response")
        result.extend(part)
        if len(result) > 65536:
            raise RuntimeError("unexpected response size")
    header, data = bytes(result).strip().split(b";;", 1)
    if header != b"0":
        raise RuntimeError(result)
    print(json.dumps(json.loads(data), indent=2))
PY
```

旧版不支持任务32，可能超时；不要因此认为前台 App 已收到或未收到触摸。先核对安装版本、respring 和新发送器是否加载，再重复查询。

在源码目录运行；PHONE_IP替换为手机地址，x/y为竖屏物理像素，先确认落点确实在前台应用测试区域：

```sh
python3 diagnostics/mixed_touch.py PHONE_IP --mode physical-first --slot 7 --x 800 --y 1200 --output physical-first-sent.json
python3 diagnostics/mixed_touch.py PHONE_IP --mode virtual-first --slot 7 --x 800 --y 1200 --output virtual-first-sent.json
python3 diagnostics/mixed_touch.py PHONE_IP --mode two --slot 7 --second-slot 9 --x 400 --y 1400 --spacing 400 --distance 80 --output virtual-two-sent.json
```

每轮导出接收端 JSON 并记录包 SHA、buildCommit、iOS版本、App、前后台状态、indexBase和显示开关。发送日志只用于时间／位置对照，不能自动标注某个接收 id 是物理还是虚拟。用受控的按下顺序和位置关联两者。

混合输入两种起始顺序各测20轮：必须两个稳定 id 同时保持、两个位置能独立移动、任一方抬起后另一方仍能移动、无意外cancel或重新begin、全部抬起后归零。原生接收器与Safari都测，最后在普通触控测试App复核；只有peak=2或看到两个圆点不算通过。

再验证断开TCP、30秒触摸不活动超时、两个客户端不同slot、重复／非法帧。任何残留、失效、前台App崩溃或SpringBoard异常都要保留时间与日志，不把该轮算成功。详细日志仍按 `ZXTouchTouch:` 筛选，配置方法见原真机测试指南。

失败分类：senderReady=false先检查现场sender捕获；TX计数增加但前台无begin则检查落点、前台焦点和系统路由；第二指加入时第一指cancel/end/re-begin，优先记录同sender帧替换证据；纯模拟双指失败先处理回归，不继续宣称混合输入成功。不要为得到计数而注入目标App，也不要在HID观察回调里重放真实触点。

## 6. 回滚与不稳定时的处理

正常回滚：停止所有测试脚本，关闭TCP连接，等待watchdog；恢复原包，再恢复用户数据和Python模块。**官方稳定包包含 appdelegate 普通 App 注入组件，不能原样重启后继续满足本次限制。** 下面提供的是“恢复稳定触摸发送器、继续禁用普通 App 注入”的 system-only 回滚变体，第三方 App 键盘 hook 仍不可用。以下示例假定稳定包已保存为 `/var/mobile/ZXTouch-stable.deb`：

```sh
BACKUP=$(cat /var/mobile/ZXTouch-last-backup-path.txt)
test -d "$BACKUP" || exit 1
dpkg -i /var/mobile/ZXTouch-stable.deb || exit 1
# 先确认重装成功。禁止在尚未禁用 appdelegate 时 respring／重开目标 App。
APP_HOOK=/var/jb/Library/MobileSubstrate/DynamicLibraries/appdelegate.dylib
if [ -f "$APP_HOOK" ]; then
    SAVED_HOOK="$BACKUP/appdelegate-from-rollback-$(date +%Y%m%d-%H%M%S).dylib"
    test ! -e "$SAVED_HOOK" && mv "$APP_HOOK" "$SAVED_HOOK"
fi
if [ -f "$BACKUP/mobile-ZXTouch.tar" ]; then
    mv /var/mobile/Library/ZXTouch "/var/mobile/Library/ZXTouch-test-saved-$(date +%Y%m%d-%H%M%S)"
    tar -xpf "$BACKUP/mobile-ZXTouch.tar" -C /var/mobile/Library
fi
for MARKER in "$BACKUP"/python/*.path; do
    [ -f "$MARKER" ] || continue
    SP=$(cat "$MARKER")
    BASE=${MARKER%.path}
    [ -d "$SP" ] || continue
    if [ -d "$SP/zxtouch" ]; then
        mv "$SP/zxtouch" "$SP/zxtouch-test-saved-$(date +%Y%m%d-%H%M%S)"
    fi
    if [ -f "$BASE.tar" ]; then tar -xpf "$BASE.tar" -C "$SP"; fi
done
```

确认重装、appdelegate 定向禁用和备份恢复均成功，再通过Sileo正常respring，重新打开测试App，复核稳定版触摸发送器的单指／双指。appdelegate 已移到备份目录，没有删除；无需移动其他 tweak，也不要对整个 `/var/jb` 改权限。以后任何官方稳定包重装／升级都可能恢复此文件，届时仍须在 respring 前重新检查。若之前hold了包，确认后续更新安排符合“无普通 App 注入”要求后执行 `apt-mark unhold com.zjx.ioscontrol` 或取消Sileo忽略更新；不要在不知情的自动升级中重新加载 appdelegate。备份目录和日志先保留。全局Python软链接原则上本测试包不应更改；若此前使用过旧阶段安装脚本，参照备份的 `python-links.txt` 人工恢复，不能猜测原目标。

如果安装后SpringBoard持续不稳定，而SSH仍可用，可只暂停本tweak，让ElleKit下次加载时忽略它：

```sh
mv /var/jb/Library/MobileSubstrate/DynamicLibraries/pccontrol.dylib /var/jb/Library/MobileSubstrate/DynamicLibraries/pccontrol.dylib.disabled
```

这是临时诊断操作；确认源文件存在、目标`.disabled`不存在后再执行，不要改名ElleKit本身或批量禁用其他tweak。改名不会卸载已经映射的代码，仍需通过Dopamine／Sileo支持的方式重启SpringBoard或进入无tweak模式；保持SSH连接，随后重装稳定包，确认旧`.disabled`文件后再移走，避免与新安装版本混淆。若SSH已不可达，按Dopamine正常重启／禁用tweak流程恢复，不要反复强装。

最终填写结果时，将“Actions构建通过”“包审计通过”“前台接收通过”“混合输入20轮通过”分别记录。当前最后两项均为 **NOT RUN**；没有真实接收日志之前，不能将此测试候选包发布或标记为最终修复版。
