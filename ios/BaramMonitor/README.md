# BaramMonitor for iPhone and iPad

A native SwiftUI companion for the BaramMesh Resources and Progress views. It connects straight to your PC over Tailscale, shows the same ring gauges and meshing progress, and raises iOS notifications for alerts such as stalled layer addition, a meshing run that stopped without finishing, high CPU temperature, memory nearly full or power over the PSU limit.

There is no cloud service and no Apple push entitlement. The app talks directly to a small read-only server inside BaramMesh.

## What you need

- A Mac with Xcode 15 or later (iOS apps cannot be built on Windows or Linux)
- [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`)
- An Apple ID. A free account works, but the app must be reinstalled every 7 days. A paid developer account removes that limit.
- Tailscale on both the PC and the iPhone or iPad, signed in to the same tailnet

## Build and install

1. `cd ios/BaramMonitor`
2. `xcodegen generate`
3. `open BaramMonitor.xcodeproj`
4. Select the BaramMonitor target, then Signing & Capabilities. Choose your team and change the bundle identifier to something unique, for example `com.yourname.baramonitor`.
5. Connect the device, select it, and press Run. On first launch trust the developer under Settings > General > VPN & Device Management.
6. In iOS Settings > General > Background App Refresh, make sure it is on for BaramMonitor.

## Set up the PC

1. `pip install -r requirements.txt` installs `segno`, which draws the pairing QR code. (`pythonnet` is only used for the optional OpenHardwareMonitorLib.dll reading.)
2. In BaramMesh open the Resources tab, choose Settings, switch on "Share live status with the phone app", keep the network on "Tailscale only", and press OK.
3. Allow the port through Windows Firewall. From an administrator PowerShell:

   `New-NetFirewallRule -DisplayName "BaramMonitor phone app" -Direction Inbound -Protocol TCP -LocalPort 8765 -RemoteAddress 100.64.0.0/10 -Action Allow`

   This allows connections from Tailscale addresses only.
4. Open Settings again and press "Pair a phone". Scan the code with the iPhone Camera app and tap the banner to open BaramMonitor. If the Camera does not offer to open the app, press "Copy link", send it to the phone and open it there, or enter the address and token under Settings in the app.

The server listens on the PC's Tailscale address only. Every request needs the access token, and the server cannot start, stop or change a mesh. Press "New access token" in the PC settings to cut off a paired device.

## Alerts and what iOS allows

Alerts are produced on the PC. The app collects them in two ways:

- **While the app is open:** it holds a long-poll connection and notifies immediately. Turn on "Keep screen on while open" and leave the device on a charger for continuous monitoring.
- **While the app is closed or the device is locked:** iOS suspends the app within seconds and does not let it keep a connection. iOS wakes it for a short background refresh every so often, at its own discretion and usually no more than every 15 to 60 minutes. Each refresh fetches any alerts raised since the last check and notifies for them, up to 12 hours back.

If you need delivery within seconds while the device is locked, the app would need Apple's push service, which requires a paid developer account and a relay server. That is not part of this app.

## Alerts the PC raises

- Layer addition stalled
- Meshing stopped before finishing (processes ended without a completion message)
- A meshing step finished, or finished with illegal faces
- CPU temperature at the yellow or red threshold
- Memory above 85% or 95%
- CPU at its package power limit
- System power at 80% or above 100% of the PSU capacity

Phase changes and recoveries appear in the Events list without a notification.

## Layout

- `Sources/Models.swift`: Codable types matching the server JSON
- `Sources/MonitorClient.swift`: HTTP client for `/api/state`, `/api/events`, `/api/history`, `/api/ping`
- `Sources/MonitorStore.swift`: polling, event cursor, notifications
- `Sources/BackgroundRefresh.swift`: iOS background app refresh
- `Sources/Views`: dashboard, ring gauges, progress card, events, settings

This code was written without a Swift toolchain available, so expect to fix a small compile error or two on the first build.
