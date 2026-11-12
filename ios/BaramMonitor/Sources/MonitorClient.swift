import Foundation

enum MonitorError: LocalizedError {
    case notConfigured
    case unauthorized
    case unreachable(String)
    case badResponse

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "No PC is paired yet."
        case .unauthorized:
            return "The access token was rejected. Pair again from BaramMesh."
        case .unreachable(let reason):
            return "Cannot reach the PC: \(reason)"
        case .badResponse:
            return "The PC sent an unexpected response."
        }
    }
}

struct MonitorClient {
    let connection: Connection
    private let session: URLSession

    init(connection: Connection) {
        self.connection = connection
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForResource = 120
        self.session = URLSession(configuration: configuration)
    }

    func ping() async throws -> PingResponse {
        try await get("/api/ping")
    }

    func state() async throws -> MonitorState {
        try await get("/api/state")
    }

    func history(seconds: Int = 300) async throws -> HistoryResponse {
        try await get("/api/history", query: [URLQueryItem(name: "seconds", value: String(seconds))])
    }

    func events(since: Int, wait: Int) async throws -> EventsResponse {
        try await get(
            "/api/events",
            query: [URLQueryItem(name: "since", value: String(since)), URLQueryItem(name: "wait", value: String(wait))],
            timeout: TimeInterval(wait + 10))
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], timeout: TimeInterval = 8) async throws -> T {
        guard connection.isComplete, let url = connection.url(path: path, query: query) else {
            throw MonitorError.notConfigured
        }

        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        request.setValue("Bearer \(connection.token)", forHTTPHeaderField: "Authorization")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            throw MonitorError.unreachable(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else { throw MonitorError.badResponse }
        if http.statusCode == 401 { throw MonitorError.unauthorized }
        guard http.statusCode == 200 else { throw MonitorError.badResponse }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw MonitorError.badResponse
        }
    }
}
