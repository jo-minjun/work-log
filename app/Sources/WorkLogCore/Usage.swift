import Foundation

public struct UsageWindow: Equatable {
    public var usedPercent: Double
    public var resetsAt: Date

    public init(usedPercent: Double, resetsAt: Date) {
        self.usedPercent = usedPercent
        self.resetsAt = resetsAt
    }
}

public typealias UsageSnapshot = (fiveHour: UsageWindow?, weekly: UsageWindow?, updatedAt: Date?)

public enum Usage {
    public static func claude(_ url: URL) -> UsageSnapshot? {
        guard let data = try? Data(contentsOf: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return (
            fiveHour: window(root["five_hour"], timestamp: nil),
            weekly: window(root["seven_day"], timestamp: nil),
            updatedAt: (root["updatedAt"] as? String).flatMap(ISODate.parse)
        )
    }

    // Codex session files are not a public API, so every field is read defensively and any surprise yields nil.
    public static func codex(sessionsRoot: URL) -> UsageSnapshot? {
        guard let newest = newestSessionFile(sessionsRoot), let data = try? Data(contentsOf: newest) else { return nil }
        let marker = Data("rate_limits".utf8)
        for line in data.split(separator: UInt8(ascii: "\n")).reversed() {
            let bytes = Data(line)
            guard bytes.range(of: marker) != nil,
                  let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { continue }
            let payload = object["payload"] as? [String: Any]
            guard let limits = (payload?["rate_limits"] ?? object["rate_limits"]) as? [String: Any] else { continue }
            let timestamp = (object["timestamp"] as? String).flatMap(ISODate.parse)
            let fiveHour = window(limits["primary"], timestamp: timestamp)
            let weekly = window(limits["secondary"], timestamp: timestamp)
            if fiveHour != nil || weekly != nil { return (fiveHour, weekly, timestamp) }
        }
        return nil
    }

    private static func newestSessionFile(_ root: URL) -> URL? {
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        guard let walker = FileManager.default.enumerator(at: root, includingPropertiesForKeys: keys) else { return nil }
        var best: (url: URL, modified: Date)?
        for case let file as URL in walker where file.pathExtension == "jsonl" {
            guard let modified = try? file.resourceValues(forKeys: Set(keys)).contentModificationDate else { continue }
            if best == nil || modified > best!.modified { best = (file, modified) }
        }
        return best?.url
    }

    // `timestamp` anchors a relative reset; Claude's file always carries an absolute epoch.
    private static func window(_ value: Any?, timestamp: Date?) -> UsageWindow? {
        guard let dict = value as? [String: Any],
              let used = (dict["used_percent"] ?? dict["used_percentage"]) as? Double else { return nil }
        if let epoch = dict["resets_at"] as? Double {
            return UsageWindow(usedPercent: used, resetsAt: Date(timeIntervalSince1970: epoch))
        }
        if let relative = dict["resets_in_seconds"] as? Double, let timestamp {
            return UsageWindow(usedPercent: used, resetsAt: timestamp.addingTimeInterval(relative))
        }
        return nil
    }
}
