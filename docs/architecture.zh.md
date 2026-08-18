# 初始架构

[English](architecture.md) | 中文

## 产品约定

模拟器执行与真机使用相同的 merged ESP32-S3 flash image，不替换固件 runtime 或 application API。可以单独选择匹配 ELF，只在浏览器中提供符号；它不会被视为可启动 flash image，也不会上传到服务端。

Web 界面应提供虚拟设备外壳、framebuffer、控制、serial console、debugger、电源控制和 deterministic event recording。

## 运行时边界

初始部署方向为服务端模拟：

```text
Browser client
  device UI, input, serial, bounded hosted-access UI
  optional Supabase browser session using publishable project configuration
             |
        documented WebSocket/API protocol
             |
Private hosted gateway (production)
  account or hashed anonymous capability, origin policy, atomic quotas
             |
Simulation session service
  validation, quotas, recording; no Docker authority
             |
Peer-credential-gated worker broker
  fixed policy only; owns dedicated rootless Docker endpoint
             |
One reserved capacity slot per active session
  at most one digest-pinned OCI + QEMU worker; ESP32-S3 and board device models
```

浏览器协议应保持 engine-neutral，使未来开源 client-side WebAssembly engine 能实现同一约定。

Hosted-access extension 是可选且 same-origin 的。缺少 `/anonymous/config` route 表示 standalone mode。Response 可以声明 Supabase account flow、anonymous access 或两者。在 account mode 中，浏览器只使用配置的 project URL 与 publishable key，然后把短期 access token 交换为 opaque gateway cookie。生产 token verification 与 user-to-owner mapping 属于私有 gateway；token 和 Supabase dependency 都不进入 simulator core。

Anonymous mode 中，Turnstile verification 通过受保护 Unix socket 委托给最小进程。该进程持有 Turnstile secret 和固定 Cloudflare egress，但没有 database、Docker、core、worker 或 firmware authority。Account verifier 采用相同的独立 UID 模式，只持有 publishable key 与固定 Supabase user-validation request。这样 gateway process 不获得 internet egress，也不承担任一 verifier 责任。

同一 optional response 可以声明 account-only saved apps。只有 `access_kind=account` 且 `saved_apps_enabled=true` 时，公共 workbench 才显示十槽 library。保存与启动 session 是两个独立的明确 action；选择的 image 不会因运行而持久化。浏览器只把 raw firmware 发送给 owner-scoped hosted storage route，绝不会收到 storage key、object ID、ciphertext 或其他账户 metadata。运行 slot 时，gateway 创建普通的新 core session，因此公共 core 不感知 account 或 retention。匿名 capability 永远看不到该 library。

## 初始设备模型

### Cardputer ADV

- ESP32-S3FN8，8 MB flash，无 PSRAM
- ST7789-compatible 240 x 135 display path
- TCA8418 keyboard controller 与 key event
- deterministic virtual BMI270 input
- GPIO10 ADC1 battery-divider voltage input
- NVS-backed preference 与 simulated reset/power cycle
- serial output、FreeRTOS behavior 与 debugger integration

### StickS3

- ESP32-S3-PICO-1-N8R8，8 MB flash 与 8 MB PSRAM
- ST7789-compatible 135 x 240 display path
- GPIO 11/12 上的 active-low physical button input
- M5PM1 logical power/battery state 与 NVS
- deterministic virtual BMI270 input

## 应用兼容里程碑

Cardputer Chess 是第一个 compatibility 与 stress application。模拟器应启动其未修改的 merged firmware、显示真实 UI、接受 keyboard control、跨重启保留 preference，并支持完成整局棋。因为该应用仍在开发，它不能替代 simulator-owned conformance firmware 作为 release gate。

未修改的应用 revision 已完成该里程碑。Revision `20da6c9` 会渲染 setup 和 game screen、接受真实 TCA8418 input，并在 simulated reset 后保留所选 level。更早 revision 也已完成 checkmate 并返回 setup。更新的应用 revision 仍是 compatibility input，而不是隐含 release claim。精确当前与历史证据保留在 `docs/conformance.md`；owned firmware 继续负责 release gate。

现有 StickS3 companion 是第二个 acceptance application，用于 display、button、NVS、overlay，以及 BLE 不可用时的 graceful behavior。

## 调试约定

产品目前暴露：

- bidirectional UART，以及 pause、resume、reset、cold power-off 与 power-on；
- breakpoint、CPU register 与 memory inspection；
- 通过 private GDB integration 实现 single-step 与 synchronized debugger stop state；
- 浏览器专用 Xtensa ELF function symbol，用于 pasted panic/backtrace address、paused program counter 与 bounded live UART tail 中的 address；ELF 永不上传或保存；
- bounded typed event recording 与 privacy-preserving diagnostic；
- native SPI、I2C、GPIO、display、input、IMU、power 与 ADC trace；
- 从最初 uploaded flash/NVS baseline 进行 deterministic external-input replay。

面向浏览器的 debugger 刻意比 GDB 更窄。它允许 register read、最多 4096 bytes 的 memory read、最多 32 个 hardware breakpoint，并且只在 paused 时允许 single-step。它不允许 memory 或 register write，也绝不暴露 raw GDB 或 QMP。

后续调试工作应增加：

- DWARF source file/line decoding，以及超出当前 bounded function-symbol resolver 的 C++ demangling；
- instruction/timing trace 与 back-in-time CPU-state replay。

## 电源保真度

初始模型是 behavioral model，而不是 electrical circuit simulator。Power off 会终止 worker 并关闭 framebuffer、UART、input 与 debug stream，同时活动 session 保留其私有 flash/NVS。Power on 从同一 image 启动全新 QEMU process，清除 RAM-adjacent output/debug state，并恢复已配置的 virtual IMU 与 power environment。这是 cold boot，与 reset 不同，并继续受原 session TTL 与 capacity limit 约束。Cardputer ADV 通过 GPIO10 ADC1 divider 暴露 battery voltage；其 hardware API 不提供 charging status 或 charge current。StickS3 通过 M5PM1 暴露 logical battery、VIN 与 charging value。后续工作应表示 sleep/deep sleep、wake source 与 injected brownout。精确 current consumption、ADC noise、per-device calibration 与 thermal estimate 需要真机测量。

## 许可边界

QEMU 与 QEMU-derived device model 必须保留其要求的 copyleft 条款。Web client 与 orchestration service 应通过有文档的 process/network protocol 与 emulator worker 通信，而不是假设所有 component 可作为一个整体重新许可。

在 Espressif ROM binary 的 redistribution 条款确认前，不得捆绑。不要复制官方 M5Stack product artwork；应创建原创 device visual，并把 profile 标识为 compatible device，而不暗示 endorsement。

私有部署可以从经过独立审查的 ROM file 和 expected digest 构建 operator-only image。公共仓库与默认 build context 不包含该 ROM；在 redistribution review 完成前，不得发布生成的 image。
