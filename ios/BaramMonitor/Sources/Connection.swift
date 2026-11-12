import Foundation
import Security

struct Connection: Equatable {
    var name: String = ""
    var host: String = ""
    var port: Int = 8765
    var token: String = ""

    var isComplete: Bool {
        !host.isEmpty && !token.isEmpty && (1...65535).contains(port)
    }

    var displayName: String {
        name.isEmpty ? host : name
    }

    func url(path: String, query: [URLQueryItem] = []) -> URL? {
        var components = URLComponents()
        components.scheme = "http"
        components.host = host
        components.port = port
        components.path = path
        components.queryItems = query.isEmpty ? nil : query
        return components.url
    }

    init() {}

    init?(pairing url: URL) {
        guard url.scheme == "baramonitor", url.host == "pair",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else {
            return nil
        }

        func value(_ key: String) -> String? {
            items.first(where: { $0.name == key })?.value
        }

        guard let host = value("host"), let token = value("token"), !host.isEmpty, !token.isEmpty else {
            return nil
        }

        self.host = host
        self.token = token
        self.port = value("port").flatMap(Int.init) ?? 8765
        self.name = value("name") ?? ""
    }
}

enum ConnectionStorage {
    private static let defaults = UserDefaults.standard
    private static let tokenAccount = "access-token"

    static func load() -> Connection {
        var connection = Connection()
        connection.name = defaults.string(forKey: "connection.name") ?? ""
        connection.host = defaults.string(forKey: "connection.host") ?? ""
        let port = defaults.integer(forKey: "connection.port")
        connection.port = port == 0 ? 8765 : port
        connection.token = Keychain.read(tokenAccount) ?? ""
        return connection
    }

    static func save(_ connection: Connection) {
        defaults.set(connection.name, forKey: "connection.name")
        defaults.set(connection.host, forKey: "connection.host")
        defaults.set(connection.port, forKey: "connection.port")
        Keychain.write(connection.token, account: tokenAccount)
    }
}

enum Keychain {
    private static let service = "BaramMonitor"

    private static func base(_ account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }

    static func read(_ account: String) -> String? {
        var query = base(account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else {
            return nil
        }

        return String(data: data, encoding: .utf8)
    }

    static func write(_ value: String, account: String) {
        SecItemDelete(base(account) as CFDictionary)
        guard !value.isEmpty else { return }

        var attributes = base(account)
        attributes[kSecValueData as String] = Data(value.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(attributes as CFDictionary, nil)
    }
}
