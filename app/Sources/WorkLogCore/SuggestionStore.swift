import Foundation

public struct Suggestion: Codable, Identifiable {
    public struct Evidence: Codable, Equatable {
        public var date: String
        public var source: String
        public var line: String
    }

    public struct PendingAnswer: Codable, Equatable {
        public var answer: String
        public var answeredAt: Date
        public var description: String?

        enum CodingKeys: String, CodingKey { case answer, answeredAt, description }

        public init(answer: String, answeredAt: Date, description: String?) {
            self.answer = answer
            self.answeredAt = answeredAt
            self.description = description
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            answer = try c.decode(String.self, forKey: .answer)
            let raw = try c.decode(String.self, forKey: .answeredAt)
            guard let parsed = ISODate.parse(raw) else {
                throw DecodingError.dataCorruptedError(forKey: .answeredAt, in: c, debugDescription: "Invalid ISO-8601: \(raw)")
            }
            answeredAt = parsed
            description = try c.decodeIfPresent(String.self, forKey: .description)
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(answer, forKey: .answer)
            try c.encode(ISODate.format(answeredAt), forKey: .answeredAt)
            try c.encodeIfPresent(description, forKey: .description)
        }
    }

    public struct HistoryEntry: Codable, Equatable {
        public var answer: String
        public var answeredAt: String
        public var appliedAt: String?
        public var result: String?
    }

    public enum Status: String, Codable, Equatable {
        case pending, answered, applied
    }

    public var id: String
    public var type: String
    public var name: String
    public var description: String
    public var evidence: [Evidence]
    public var status: Status
    public var neverSuggest: Bool
    public var createdAt: String
    public var updatedAt: String
    public var pendingAnswer: PendingAnswer?
    public var history: [HistoryEntry]

    public var isPending: Bool { status == .pending }
}

public enum Answer { case accept, reject, never }

public struct SuggestionStoreError: LocalizedError, Equatable, CustomStringConvertible {
    public let message: String
    public var description: String { message }
    public var errorDescription: String? { message }
}

public enum SuggestionStore {
    // One record the app cannot read (hand-edited, or written by a newer collector) must not hide the others.
    private struct LenientRecord: Decodable {
        let value: Suggestion?
        init(from decoder: Decoder) throws { value = try? Suggestion(from: decoder) }
    }

    private struct Root: Decodable {
        var suggestions: [LenientRecord]
    }

    // Python locks "<name>.lock" next to the data file.
    private static func lockURL(for url: URL) -> URL {
        url.deletingLastPathComponent().appendingPathComponent(url.lastPathComponent + ".lock")
    }

    public static func load(_ url: URL) throws -> [Suggestion] {
        guard let data = try? Data(contentsOf: url) else { return [] }
        let records = try JSONDecoder().decode(Root.self, from: data).suggestions
        let loaded = records.compactMap(\.value)
        if loaded.count < records.count {
            NSLog("WorkLog: skipped %d unreadable record(s) in %@", records.count - loaded.count, url.lastPathComponent)
        }
        return loaded
    }

    public static func answer(_ url: URL, id: String, answer: Answer, description: String?, now: Date) throws {
        try patch(url, id: id) { record in
            let status = record["status"] as? String
            guard status == Suggestion.Status.pending.rawValue else {
                throw SuggestionStoreError(message: "Suggestion \(id) is \(status ?? "unknown"), only pending suggestions can be answered")
            }
            var pending: [String: Any] = [
                "answer": answer == .accept ? "accept" : "reject",
                "answeredAt": ISODate.format(now),
            ]
            if let text = description ?? record["description"] as? String { pending["description"] = text }
            record["status"] = Suggestion.Status.answered.rawValue
            record["pendingAnswer"] = pending
            if answer == .never { record["neverSuggest"] = true }
        }
    }

    public static func setNeverSuggest(_ url: URL, id: String, _ value: Bool) throws {
        try patch(url, id: id) { $0["neverSuggest"] = value }
    }

    // Patches the raw JSON so keys owned by the Python side survive untouched.
    private static func patch(_ url: URL, id: String, _ change: (inout [String: Any]) throws -> Void) throws {
        try FileLock.withLock(at: lockURL(for: url)) {
            let data = try Data(contentsOf: url)
            guard var root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  var records = root["suggestions"] as? [[String: Any]] else {
                throw SuggestionStoreError(message: "\(url.lastPathComponent) is not a suggestions file")
            }
            guard let index = records.firstIndex(where: { $0["id"] as? String == id }) else {
                throw SuggestionStoreError(message: "Suggestion \(id) not found")
            }
            try change(&records[index])
            root["suggestions"] = records
            let output = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
            try AtomicFile.write(output, to: url)
        }
    }
}
