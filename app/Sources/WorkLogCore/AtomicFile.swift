import Foundation

enum AtomicFile {
    // Data files hold the Slack identity and the run history, so only the user may read them.
    static let fileMode: mode_t = 0o600

    // Readers (including the Python side) only ever see the old or the new file, never a partial one.
    static func write(_ data: Data, to url: URL) throws {
        let temp = url.deletingLastPathComponent().appendingPathComponent(".\(url.lastPathComponent).\(UUID().uuidString).tmp")
        guard FileManager.default.createFile(atPath: temp.path, contents: data, attributes: [.posixPermissions: fileMode]) else {
            throw POSIXError(.EIO)
        }
        if rename(temp.path, url.path) != 0 {
            let code = errno
            try? FileManager.default.removeItem(at: temp)
            throw POSIXError(POSIXErrorCode(rawValue: code) ?? .EIO)
        }
    }
}

public enum BrokenFile {
    // Moves an unreadable data file aside so the next load starts from defaults, while keeping it for inspection.
    @discardableResult
    public static func backUp(_ url: URL, now: Date, timeZone: TimeZone = .current) throws -> URL {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let target = url.deletingLastPathComponent()
            .appendingPathComponent("\(url.lastPathComponent).broken-\(formatter.string(from: now))")
        try FileManager.default.moveItem(at: url, to: target)
        return target
    }
}
