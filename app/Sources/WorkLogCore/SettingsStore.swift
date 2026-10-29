import Foundation

public struct SettingsStoreError: LocalizedError, Equatable, CustomStringConvertible {
    public let message: String
    public var description: String { message }
    public var errorDescription: String? { message }
}

public enum SettingsStore {
    // The collector owns `slack` and writes it without a lock, so the app replaces only these keys.
    static let appOwnedKeys = [
        "schedule", "provider", "logFolder", "logLanguage", "appLanguage", "sessionFolders", "launchAtLogin", "notifyOnSuccess", "scheduleEnabled",
        "version",
    ]

    public static func load(_ url: URL) throws -> AppSettings {
        guard FileManager.default.fileExists(atPath: url.path) else { return .defaults }
        return try JSONDecoder().decode(AppSettings.self, from: Data(contentsOf: url))
    }

    public static func save(_ settings: AppSettings, to url: URL) throws {
        var root: [String: Any] = [:]
        if FileManager.default.fileExists(atPath: url.path) {
            guard let existing = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any] else {
                throw SettingsStoreError(message: "\(url.lastPathComponent) is not a JSON object")
            }
            root = existing
        }
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(settings)) as? [String: Any] ?? [:]
        for key in appOwnedKeys {
            root[key] = encoded[key]
        }
        let output = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try AtomicFile.write(output, to: url)
    }
}
