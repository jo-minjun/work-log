import Foundation

// A stand-up draft saved by daily.py as dailies/YYYY-MM-DD.json.
public struct Daily: Codable, Equatable {
    public struct Group: Codable, Equatable {
        public var project: String
        public var items: [String]
    }

    public struct Evidence: Codable, Equatable {
        public var task: String
        public var reason: String
        public var sources: [String]
        public var weak: Bool
        public var links: [String]
    }

    public var date: String
    public var doneRange: [String]?
    public var done: [Group]
    public var todo: [Group]
    public var evidence: [Evidence]
    public var notes: [String]
    public var sources: [String: String]
    public var generatedAt: String
    public var trigger: String
    // The copy text, rendered by daily.py in the log language
    public var text: String

    public static let okStatus = "ok"

    // Sources that did not answer, in a stable order for display
    public var sourceProblems: [(source: String, status: String)] {
        sources.filter { $0.value != Self.okStatus }.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }
    }
}

// The last headless run, written by run_daily.sh as dailies/last-run.json.
public struct DailyRun: Codable, Equatable {
    public enum Result: String, Codable, Equatable {
        case ok, noOutput, failed, timeout, busy
    }

    public var startedAt: String
    public var endedAt: String
    public var trigger: String
    public var result: Result
    public var reason: String?

    public var succeeded: Bool { result == .ok }
}

public enum DailyStore {
    public static let lastRunName = "last-run.json"
    private static let namePattern = #"^\d{4}-\d{2}-\d{2}\.json$"#

    // The newest daily that decodes. A broken file is skipped so an older daily still shows.
    public static func latest(_ dir: URL) -> Daily? {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        for name in names.filter({ $0.range(of: namePattern, options: .regularExpression) != nil }).sorted(by: >) {
            if let daily = decode(Daily.self, dir.appendingPathComponent(name)) { return daily }
        }
        return nil
    }

    public static func lastRun(_ dir: URL) -> DailyRun? {
        decode(DailyRun.self, dir.appendingPathComponent(lastRunName))
    }

    private static func decode<T: Decodable>(_ type: T.Type, _ url: URL) -> T? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}

public enum DailyFormat {
    // "11/2 (Mon)": the daily's own date, so a draft from an earlier day is visible as such.
    public static func day(_ isoDate: String, strings: UIStrings) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let parts = isoDate.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3,
              let date = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2])) else { return isoDate }
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.timeZone = calendar.timeZone
        formatter.locale = strings.locale
        formatter.dateFormat = "EEE"
        return "\(parts[1])/\(parts[2]) (\(formatter.string(from: date)))"
    }

    public static func title(_ daily: Daily, strings: UIStrings) -> String {
        strings.dailyTitle(day(daily.date, strings: strings))
    }

    public static func time(_ iso: String, timeZone: TimeZone = .current) -> String? {
        guard let date = ISODate.parse(iso) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_GB")
        formatter.timeZone = timeZone
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }
}
