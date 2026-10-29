import Foundation

public struct RunRecord: Codable, Equatable {
    public enum Trigger: String, Codable, Equatable { case schedule, manual }
    public enum Result: String, Codable, Equatable { case succeeded, failed, skipped }

    // run.sh writes this reason when a day it wrote carries warnings (Slack failed, for example).
    public static let warningsReason = "Completed with warnings"
    public static let stoppedOnQuitReason = "Stopped on quit"

    public var startedAt: Date
    public var endedAt: Date
    public var trigger: Trigger
    public var provider: AppSettings.Provider
    public var result: Result
    public var reason: String?
    public var costUsd: Double?
    public var tokens: Int?
    // The first line of the provider's report; run.sh asks the skill to make it a one-sentence summary.
    public var summary: String?
    public var logPath: String?

    public init(startedAt: Date, endedAt: Date, trigger: Trigger, provider: AppSettings.Provider, result: Result,
                reason: String? = nil, costUsd: Double? = nil, tokens: Int? = nil, summary: String? = nil, logPath: String? = nil) {
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.trigger = trigger
        self.provider = provider
        self.result = result
        self.reason = reason
        self.costUsd = costUsd
        self.tokens = tokens
        self.summary = summary
        self.logPath = logPath
    }

    public var hasWarnings: Bool { result == .succeeded && reason == Self.warningsReason }

    // A run the app ended or could not start; run.sh never wrote a line for it, and there is no provider output.
    public static func appFailure(trigger: Trigger, provider: AppSettings.Provider, startedAt: Date, endedAt: Date,
                                  reason: String) -> RunRecord {
        RunRecord(startedAt: startedAt, endedAt: endedAt, trigger: trigger, provider: provider, result: .failed, reason: reason)
    }

    enum CodingKeys: String, CodingKey {
        case startedAt, endedAt, trigger, provider, result, reason, costUsd, tokens, summary, logPath
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        startedAt = try Self.date(c, .startedAt)
        endedAt = try Self.date(c, .endedAt)
        trigger = try c.decode(Trigger.self, forKey: .trigger)
        provider = try c.decode(AppSettings.Provider.self, forKey: .provider)
        result = try c.decode(Result.self, forKey: .result)
        reason = try c.decodeIfPresent(String.self, forKey: .reason)
        costUsd = try c.decodeIfPresent(Double.self, forKey: .costUsd)
        tokens = try c.decodeIfPresent(Int.self, forKey: .tokens)
        summary = try c.decodeIfPresent(String.self, forKey: .summary)
        logPath = try c.decodeIfPresent(String.self, forKey: .logPath)
    }

    // Nulls are written explicitly: every line carries all ten keys, like the Python writer.
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(ISODate.format(startedAt), forKey: .startedAt)
        try c.encode(ISODate.format(endedAt), forKey: .endedAt)
        try c.encode(trigger, forKey: .trigger)
        try c.encode(provider, forKey: .provider)
        try c.encode(result, forKey: .result)
        try Self.encodeOrNull(&c, reason, .reason)
        try Self.encodeOrNull(&c, costUsd, .costUsd)
        try Self.encodeOrNull(&c, tokens, .tokens)
        try Self.encodeOrNull(&c, summary, .summary)
        try Self.encodeOrNull(&c, logPath, .logPath)
    }

    private static func date(_ c: KeyedDecodingContainer<CodingKeys>, _ key: CodingKeys) throws -> Date {
        let raw = try c.decode(String.self, forKey: key)
        guard let date = ISODate.parse(raw) else {
            throw DecodingError.dataCorruptedError(forKey: key, in: c, debugDescription: "Invalid ISO-8601: \(raw)")
        }
        return date
    }

    private static func encodeOrNull<T: Encodable>(_ c: inout KeyedEncodingContainer<CodingKeys>, _ value: T?, _ key: CodingKeys) throws {
        if let value { try c.encode(value, forKey: key) } else { try c.encodeNil(forKey: key) }
    }
}

public enum RunLog {
    // Bad lines are skipped so one corrupt write never hides the rest of the history.
    public static func load(_ url: URL) -> [RunRecord] {
        guard let data = try? Data(contentsOf: url) else { return [] }
        let decoder = JSONDecoder()
        return data.split(separator: UInt8(ascii: "\n")).compactMap { try? decoder.decode(RunRecord.self, from: Data($0)) }
    }

    // A single O_APPEND write keeps concurrent writers (including the Python side) from interleaving partial lines.
    public static func append(_ url: URL, _ record: RunRecord) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        var line = try encoder.encode(record)
        line.append(UInt8(ascii: "\n"))
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let fd = open(url.path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, AtomicFile.fileMode)
        guard fd >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        defer { close(fd) }
        let written = line.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard written == line.count else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    }

    // Only runs where the provider ran (run.sh then records its output path) spent anything.
    // runsWithoutCost counts only `provider`'s runs: Codex never reports a cost, so its runs are not missing data.
    public static func monthTotals(_ runs: [RunRecord], month: DateComponents, provider: AppSettings.Provider,
                                   calendar: Calendar = .current) -> MonthTotals {
        let ran = runs.filter {
            let parts = calendar.dateComponents([.year, .month], from: $0.startedAt)
            return $0.logPath != nil && parts.year == month.year && parts.month == month.month
        }
        return MonthTotals(
            runs: ran.count,
            costUsd: ran.reduce(0) { $0 + ($1.costUsd ?? 0) },
            tokens: ran.reduce(0) { $0 + ($1.tokens ?? 0) },
            runsWithoutCost: ran.filter { $0.provider == provider && $0.costUsd == nil }.count
        )
    }
}

public struct MonthTotals: Equatable {
    public var runs: Int
    public var costUsd: Double
    public var tokens: Int
    public var runsWithoutCost: Int
}
