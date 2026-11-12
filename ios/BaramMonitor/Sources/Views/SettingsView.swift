import SwiftUI
import UIKit
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject private var store: MonitorStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var host = ""
    @State private var port = "8765"
    @State private var token = ""
    @State private var testResult: String?
    @State private var testing = false

    private var draft: Connection {
        var connection = Connection()
        connection.name = name.trimmingCharacters(in: .whitespaces)
        connection.host = host.trimmingCharacters(in: .whitespaces)
        connection.port = Int(port) ?? 8765
        connection.token = token.trimmingCharacters(in: .whitespaces)
        return connection
    }

    private var notificationText: String {
        switch store.notificationStatus {
        case .authorized, .provisional, .ephemeral: return "Allowed"
        case .denied: return "Blocked in iOS Settings"
        default: return "Not requested yet"
        }
    }

    var body: some View {
        Form {
            Section {
                TextField("Name (optional)", text: $name)
                TextField("Host or Tailscale address", text: $host)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Port", text: $port)
                    .keyboardType(.numberPad)
                SecureField("Access token", text: $token)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                Button {
                    Task { await runTest() }
                } label: {
                    HStack {
                        Text("Test connection")
                        if testing { ProgressView() }
                    }
                }
                .disabled(!draft.isComplete || testing)

                if let testResult {
                    Text(testResult).font(.footnote).foregroundStyle(.secondary)
                }
            } header: {
                Text("PC")
            } footer: {
                Text("In BaramMesh open Resources > Settings > Pair a phone, then scan the code with the Camera app. The PC and this device must be on the same Tailscale network.")
            }

            Section("Alerts") {
                Toggle("Notify me of alerts", isOn: $store.notificationsEnabled)
                LabeledContent("Notifications", value: notificationText)

                if store.notificationStatus == .denied {
                    Button("Open iOS Settings") {
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            UIApplication.shared.open(url)
                        }
                    }
                } else if store.notificationStatus == .notDetermined {
                    Button("Allow notifications") {
                        Task { await store.requestNotifications() }
                    }
                }

                Button("Send test notification") {
                    Task { await store.sendTestNotification() }
                }
            }

            Section {
                Toggle("Keep screen on while open", isOn: $store.keepScreenOn)
            } header: {
                Text("Display")
            } footer: {
                Text("iOS suspends apps that are not on screen, so live alerts arrive only while this app is open. When it is closed, iOS checks for new alerts every so often at its own discretion. For continuous monitoring, leave the app open on a charger with this option on.")
            }

            Section {
                Button("Forget this PC", role: .destructive) {
                    store.forget()
                    load()
                }
            }
        }
        .navigationTitle("Settings")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    store.save(draft)
                    Task { await store.requestNotifications() }
                    dismiss()
                }
                .disabled(!draft.isComplete)
            }
        }
        .onAppear(perform: load)
    }

    private func load() {
        let connection = store.connection
        name = connection.name
        host = connection.host
        port = String(connection.port)
        token = connection.token
        testResult = nil
    }

    private func runTest() async {
        testing = true
        defer { testing = false }

        do {
            let response = try await MonitorClient(connection: draft).ping()
            testResult = "Connected to \(response.host)."
        } catch {
            testResult = error.localizedDescription
        }
    }
}
